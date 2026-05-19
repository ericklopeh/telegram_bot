import logging
import re
import urllib.parse

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.config import get_settings
from app.db.session import get_db_session
from app.domain import constants as C
from app.models.case import Case
from app.repositories.document_repository import DocumentRepository
from app.services.authorization_service import AuthorizationService, TemplateNotFoundError
from app.services.case_service import CaseService
from app.services.refinanciamiento_service import (
    RefinanciamientoService,
    TemplateNotFoundError as RefiTemplateNotFoundError,
)
from app.services.case_event_service import (
    AUTH_GENERATED,
    DOCUMENT_CREATED,
    REFI_GENERATED,
    TELEGRAM_NOTIFIED,
    log_document_event,
    log_event,
    log_status_change,
)
from app.services.sharepoint_document_service import SharePointDocumentService, SharePointUploadPayload
from app.web.auth import get_current_user, require_roles, ROLES_AUTORIZACION_SNTE

log = logging.getLogger(__name__)

router = APIRouter()

_SNTE_ALLOWED_STATUSES = (C.ST_PED_PREP_AUT, C.ST_PED_AUT_GENERADA)


def get_web_db():
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


def _redirect_if_active_document_exists(
    *,
    db: Session,
    case_id: int,
    document_type: str,
    label: str,
    route: str,
) -> RedirectResponse | None:
    existing_doc = DocumentRepository.get_active_document(db, case_id, document_type)
    if not existing_doc:
        return None

    log.warning(
        "Generacion bloqueada por documento activo existente",
        extra={
            "case_id": case_id,
            "document_id": existing_doc.id,
            "document_type": document_type,
            "route": route,
        },
    )
    msg = urllib.parse.quote(
        f"Ya existe {label} activa para este caso. La regeneracion se habilitara en un flujo posterior."
    )
    return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)


def _build_snte_payload(form: dict) -> dict:
    """Normaliza campos del modal SNTE (misma convención que refinanciamiento)."""
    payload: dict = {}
    for campo in (
        "nombre",
        "rfc",
        "categoria",
        "domicilio",
        "tel_part",
        "tel_celular",
        "correo",
        "fecha_venta",
        "folio",
        "semana",
        "monto_total",
        "qna_inicial",
        "plazo_qnas",
        "descuento_qna",
        "observaciones",
    ):
        raw = form.get(campo, "")
        payload[campo] = raw.strip() if isinstance(raw, str) else str(raw).strip()

    for i in range(1, 6):
        for sub in ("nombre", "trans", "credito", "precio", "descuento", "tipo"):
            key = f"prod_{i}_{sub}"
            raw = form.get(key, "")
            payload[key] = raw.strip() if isinstance(raw, str) else str(raw).strip()

    return payload


def _validate_snte_payload(form_data: dict) -> list[str]:
    """Devuelve lista de errores de validación. Lista vacía significa OK."""
    errors: list[str] = []

    if not form_data.get("nombre"):
        errors.append("El nombre del cliente es obligatorio.")
    if not form_data.get("rfc"):
        errors.append("El RFC es obligatorio.")
    if not form_data.get("folio"):
        errors.append("El folio es obligatorio.")
    if not form_data.get("fecha_venta"):
        errors.append("La fecha de venta es obligatoria.")
    if not form_data.get("qna_inicial"):
        errors.append("La quincena inicial es obligatoria.")
    if not form_data.get("plazo_qnas"):
        errors.append("El plazo es obligatorio.")

    fecha = form_data.get("fecha_venta", "")
    if fecha and not re.fullmatch(r"\d{2}/\d{2}/\d{4}", fecha):
        errors.append("Fecha de venta inválida. Use formato DD/MM/AAAA (ej: 25/12/2026).")

    qna = form_data.get("qna_inicial", "")
    if qna and not re.fullmatch(r"\d{2}-\d{4}", qna):
        errors.append("Quincena inicial inválida. Use formato QQ-AAAA (ej: 10-2026).")

    plazo = form_data.get("plazo_qnas", "")
    if plazo:
        try:
            p = int(plazo)
            if p <= 0:
                errors.append("El plazo debe ser mayor a 0.")
        except ValueError:
            errors.append("El plazo debe ser un número entero.")

    tiene_producto = any(form_data.get(f"prod_{i}_nombre", "").strip() for i in range(1, 6))
    monto_raw = form_data.get("monto_total", "").strip()
    tiene_monto = bool(monto_raw)
    if tiene_monto:
        try:
            if float(monto_raw.replace(",", "")) <= 0:
                tiene_monto = False
        except ValueError:
            errors.append("El monto total debe ser numérico.")
            tiene_monto = False

    if not tiene_producto and not tiene_monto:
        errors.append("Debe capturar al menos 1 producto o indicar un monto total.")

    return errors


def _verify_snte_documents_active(db: Session, case_id: int) -> tuple[bool, list[str]]:
    """Comprueba que Excel SNTE y PDF orden estén activos tras la generación."""
    missing: list[str] = []
    for doc_type in (C.DOC_AUTORIZACION_SNTE, C.DOC_ORDEN_SNTE_PDF):
        if not DocumentRepository.get_active_document(db, case_id, doc_type):
            missing.append(doc_type)
    return not missing, missing


def _schedule_generated_document_tasks(
    *,
    background_tasks: BackgroundTasks,
    case: Case,
    docs: list,
    case_id: int,
) -> None:
    from app.services.notification_service import notify_snte_generation_from_web

    background_tasks.add_task(notify_snte_generation_from_web, case_id)

    sp_service = SharePointDocumentService()
    for doc in docs:
        payload = SharePointUploadPayload(
            document_id=doc.id,
            file_path=doc.file_path,
            vendedor=case.seller_name or "SIN VENDEDOR",
            semana=case.week_code,
            cliente=case.client_name,
            folio=case.official_folio or case.temp_folio or case.public_id,
            tipo_documento=doc.document_type,
            filename=doc.stored_filename,
        )
        background_tasks.add_task(sp_service.upload_document, payload)


def _log_generation_events(
    *,
    db: Session,
    case: Case,
    docs: list,
    generation_event_type: str,
    generated_by: str,
    route: str,
    actor_user_id: int | None,
    actor_role: str | None,
) -> None:
    log_event(
        db,
        case_id=case.id,
        event_type=generation_event_type,
        message="Documentos SNTE generados",
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        source="web",
        metadata={
            "case_id": case.id,
            "generated_by": generated_by,
            "route": route,
            "document_ids": [doc.id for doc in docs],
        },
    )
    for doc in docs:
        log_document_event(
            db,
            case_id=case.id,
            event_type=DOCUMENT_CREATED,
            document_id=doc.id,
            document_type=doc.document_type,
            filename=doc.stored_filename,
            message="Documento generado desde web",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            source="web",
            metadata={
                "case_id": case.id,
                "generated_by": generated_by,
                "route": route,
                "upload_status": doc.upload_status,
            },
        )


def _log_background_notification_enqueued(
    *,
    db: Session,
    case: Case,
    generated_by: str,
    route: str,
    actor_user_id: int | None,
    actor_role: str | None,
) -> None:
    try:
        log_event(
            db,
            case_id=case.id,
            event_type=TELEGRAM_NOTIFIED,
            message="Notificacion Telegram encolada en background",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            source="web",
            metadata={
                "case_id": case.id,
                "generated_by": generated_by,
                "route": route,
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        log.exception(
            "No se pudo persistir evento de notificacion Telegram encolada",
            extra={"case_id": case.id, "route": route},
        )


def _persist_generated_status(
    *,
    db: Session,
    case: Case,
    case_id: int,
    action_user: str,
    actor_user_id: int | None,
    actor_role: str | None,
    notes: str,
    log_message: str,
    route: str,
) -> None:
    from app.config import get_settings
    from app.domain import constants as C
    from app.services.case_service import CaseService

    old_status = case.current_status
    case_svc = CaseService(get_settings())
    case_svc.transition_case_status(
        db,
        case,
        C.ST_PED_AUT_GENERADA,
        notes=notes,
        action_user=action_user,
    )
    log_status_change(
        db,
        case_id=case_id,
        old_status=old_status,
        new_status=C.ST_PED_AUT_GENERADA,
        message=notes,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        source="web",
        metadata={
            "case_id": case_id,
            "generated_by": action_user,
            "route": route,
            "old_status": old_status,
            "new_status": C.ST_PED_AUT_GENERADA,
        },
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        log.exception(
            "Fallo commit con auditoria; se reintenta persistir estatus sin eventos",
            extra={"case_id": case_id, "route": route},
        )
        db.refresh(case)
        case_svc.transition_case_status(
            db,
            case,
            C.ST_PED_AUT_GENERADA,
            notes=notes,
            action_user=action_user,
        )
        db.commit()
    db.refresh(case)
    log.info(
        log_message,
        extra={"case_id": case_id, "new_status": C.ST_PED_AUT_GENERADA},
    )


@router.post("/casos/{case_id}/generar-autorizacion")
async def generar_autorizacion(
    case_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_web_db),
):
    redirect = require_roles(request, db, ROLES_AUTORIZACION_SNTE)
    if redirect:
        return redirect

    user = get_current_user(request, db)
    action_user = user.get("nombre", "web_user") if user else "web_user"
    actor_user_id = user.get("id") if user else None
    actor_role = user.get("rol") if user else None

    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return RedirectResponse(url="/casos", status_code=302)

    if case.current_status not in _SNTE_ALLOWED_STATUSES:
        msg = urllib.parse.quote(
            f"Solo se puede generar SNTE en «{C.ST_PED_PREP_AUT}» o «{C.ST_PED_AUT_GENERADA}» "
            f"(estado actual: {case.current_status})."
        )
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)

    case_svc = CaseService(get_settings())
    if not case_svc.pedido_has_all_documents(db, case):
        checklist = case_svc.get_pedido_checklist(db, case)
        msg = urllib.parse.quote(
            "Completa el checklist del pedido antes de generar la autorización SNTE:\n"
            + checklist.replace("\n", " · ")
        )
        log.warning(
            "Generación SNTE bloqueada: checklist incompleto",
            extra={"case_id": case_id},
        )
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)

    raw_form = await request.form()
    form_data = _build_snte_payload(dict(raw_form))

    validation_errors = _validate_snte_payload(form_data)
    if validation_errors:
        msg = urllib.parse.quote(" | ".join(validation_errors))
        log.warning(
            "Payload SNTE inválido",
            extra={"case_id": case_id, "errors": validation_errors},
        )
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)

    auth_service = AuthorizationService(db)

    try:
        docs = auth_service.generate_for_case(case_id, form_data, action_user)
        log.info(
            "Documentos de autorizacion SNTE generados",
            extra={"case_id": case_id, "docs": [doc.id for doc in docs]},
        )
    except TemplateNotFoundError as e:
        db.rollback()
        msg = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)
    except Exception as e:
        db.rollback()
        log.exception(
            "Error generando autorizacion SNTE antes de persistir estatus",
            extra={"case_id": case_id},
        )
        msg = urllib.parse.quote(f"Error generando autorizacion: {str(e)}")
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)

    returned_types = {doc.document_type for doc in docs}
    required_types = {C.DOC_AUTORIZACION_SNTE, C.DOC_ORDEN_SNTE_PDF}
    if not required_types.issubset(returned_types):
        labels = ", ".join(C.doc_type_label(dt) for dt in required_types - returned_types)
        msg = urllib.parse.quote(
            f"Generación incompleta: no se crearon todos los documentos ({labels}). "
            "El estatus del caso no se actualizó."
        )
        log.error(
            "SNTE: generate_for_case no devolvió par Excel+PDF",
            extra={"case_id": case_id, "returned": list(returned_types)},
        )
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)

    ok_pair, missing_types = _verify_snte_documents_active(db, case_id)
    if not ok_pair:
        labels = ", ".join(C.doc_type_label(dt) for dt in missing_types)
        msg = urllib.parse.quote(
            f"Generación incompleta: faltan documentos activos ({labels}). "
            "El estatus del caso no se actualizó."
        )
        log.error(
            "SNTE generado sin par Excel+PDF activo en BD",
            extra={"case_id": case_id, "missing": missing_types},
        )
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)

    is_regeneration = case.current_status == C.ST_PED_AUT_GENERADA
    status_notes = (
        "Autorizacion SNTE regenerada"
        if is_regeneration
        else "Autorizacion SNTE generada"
    )

    try:
        _log_generation_events(
            db=db,
            case=case,
            docs=docs,
            generation_event_type=AUTH_GENERATED,
            generated_by=action_user,
            route="generar_autorizacion",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
        )
        _persist_generated_status(
            db=db,
            case=case,
            case_id=case_id,
            action_user=action_user,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            notes=status_notes,
            log_message="Estatus de caso persistido tras generar autorizacion SNTE",
            route="generar_autorizacion",
        )
    except Exception as e:
        db.rollback()
        log.exception(
            "Documentos SNTE generados, pero fallo la persistencia del estatus",
            extra={"case_id": case_id},
        )
        msg = urllib.parse.quote(
            f"Documentos generados, pero no se pudo actualizar el estatus: {str(e)}"
        )
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)

    try:
        _schedule_generated_document_tasks(
            background_tasks=background_tasks,
            case=case,
            docs=docs,
            case_id=case_id,
        )
        _log_background_notification_enqueued(
            db=db,
            case=case,
            generated_by=action_user,
            route="generar_autorizacion",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
        )
    except Exception as e:
        log.exception(
            "Estatus SNTE persistido, pero fallo la programacion de tareas en segundo plano",
            extra={"case_id": case_id},
        )
        msg = urllib.parse.quote(
            f"Autorizacion generada y estatus actualizado, pero fallaron tareas en segundo plano: {str(e)}"
        )
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)

    if is_regeneration:
        success_text = (
            "Autorización SNTE regenerada. Las versiones anteriores quedaron archivadas; "
            "la subida a SharePoint se procesará en segundo plano."
        )
    else:
        success_text = (
            "Autorización SNTE generada (Excel + PDF). "
            "La subida a SharePoint se procesará en segundo plano."
        )
    msg = urllib.parse.quote(success_text)
    return RedirectResponse(url=f"/casos/{case_id}?success={msg}", status_code=302)


def _build_refi_payload(form: dict) -> dict:
    """Construye el payload normalizado para RefinanciamientoService."""
    payload: dict = {}

    for campo in (
        "nombre",
        "rfc",
        "categoria",
        "domicilio",
        "tel_part",
        "tel_celular",
        "correo",
        "fecha_venta",
    ):
        payload[campo] = form.get(campo, "").strip()

    for i in range(1, 6):
        for sub in ("nombre", "codigo", "trans", "precio"):
            key = f"prod_{i}_{sub}"
            payload[key] = form.get(key, "").strip()

    for i in range(1, 6):
        for sub in ("folio", "descuento", "saldo"):
            key = f"refi_{sub}_{i}"
            payload[key] = form.get(key, "").strip()

    for campo in (
        "folio",
        "semana",
        "monto_total",
        "monto_vta_nueva",
        "qna_inicial",
        "plazo_qnas",
        "descuento_qna",
    ):
        payload[campo] = form.get(campo, "").strip()

    payload["observaciones"] = form.get("observaciones", "").strip()
    return payload


def _validate_refi_payload(form_data: dict) -> list[str]:
    """Devuelve lista de errores de validacion. Lista vacia significa OK."""
    errors: list[str] = []

    if not form_data.get("nombre"):
        errors.append("El nombre del cliente es obligatorio.")
    if not form_data.get("folio"):
        errors.append("El folio es obligatorio.")
    if not form_data.get("qna_inicial"):
        errors.append("La quincena inicial es obligatoria.")
    if not form_data.get("plazo_qnas"):
        errors.append("El plazo es obligatorio.")
    if not form_data.get("fecha_venta"):
        errors.append("La fecha de venta es obligatoria.")

    tiene_producto = any(
        form_data.get(f"prod_{i}_nombre", "").strip()
        for i in range(1, 6)
    )
    if not tiene_producto:
        errors.append("Debe capturar al menos 1 producto.")

    tiene_saldo = any(
        form_data.get(f"refi_folio_{i}", "").strip()
        for i in range(1, 6)
    )
    if not tiene_saldo:
        errors.append("Debe capturar al menos 1 folio a reestructurar.")

    qna = form_data.get("qna_inicial", "")
    if qna and not re.fullmatch(r"\d{2}-\d{4}", qna):
        errors.append("Quincena inicial invalida. Use formato QQ-AAAA (ej: 10-2026).")

    plazo = form_data.get("plazo_qnas", "")
    if plazo:
        try:
            p = int(plazo)
            if p <= 0:
                errors.append("El plazo debe ser mayor a 0.")
        except ValueError:
            errors.append("El plazo debe ser un numero entero.")

    return errors


@router.post("/casos/{case_id}/generar-refinanciamiento")
async def generar_refinanciamiento(
    case_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_web_db),
) -> RedirectResponse:
    """Genera el Excel de refinanciamiento y el PDF Orden SNTE para un caso."""
    redirect = require_roles(request, db, ROLES_AUTORIZACION_SNTE)
    if redirect:
        return redirect

    user = get_current_user(request, db)
    action_user = user.get("nombre", "web_user") if user else "web_user"
    actor_user_id = user.get("id") if user else None
    actor_role = user.get("rol") if user else None

    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return RedirectResponse(url="/casos", status_code=302)

    duplicate_redirect = _redirect_if_active_document_exists(
        db=db,
        case_id=case_id,
        document_type=C.DOC_AUTORIZACION_REFI,
        label="una autorizacion de refinanciamiento",
        route="generar_refinanciamiento",
    )
    if duplicate_redirect:
        return duplicate_redirect

    raw_form = await request.form()
    form_data = _build_refi_payload(dict(raw_form))

    log.info(
        "Iniciando generacion de refinanciamiento",
        extra={"case_id": case_id, "action_user": action_user},
    )

    validation_errors = _validate_refi_payload(form_data)
    if validation_errors:
        msg = urllib.parse.quote(" | ".join(validation_errors))
        log.warning(
            "Payload de refinanciamiento invalido",
            extra={"case_id": case_id, "errors": validation_errors},
        )
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)

    try:
        refi_service = RefinanciamientoService(db)
        docs = refi_service.generate_for_case(case_id, form_data, action_user)
        log.info(
            "Documentos de refinanciamiento generados",
            extra={"case_id": case_id, "docs": [doc.id for doc in docs]},
        )
    except (TemplateNotFoundError, RefiTemplateNotFoundError) as e:
        db.rollback()
        log.warning(
            "Plantilla no encontrada al generar refinanciamiento",
            extra={"case_id": case_id, "error": str(e)},
        )
        msg = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)
    except ValueError as e:
        db.rollback()
        log.warning(
            "Validacion fallida al generar refinanciamiento",
            extra={"case_id": case_id, "error": str(e)},
        )
        msg = urllib.parse.quote(f"Error de validacion: {str(e)}")
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)
    except Exception as e:
        db.rollback()
        log.exception(
            "Error inesperado generando refinanciamiento antes de persistir estatus",
            extra={"case_id": case_id},
        )
        msg = urllib.parse.quote(f"Error generando refinanciamiento: {str(e)}")
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)

    try:
        _log_generation_events(
            db=db,
            case=case,
            docs=docs,
            generation_event_type=REFI_GENERATED,
            generated_by=action_user,
            route="generar_refinanciamiento",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
        )
        _persist_generated_status(
            db=db,
            case=case,
            case_id=case_id,
            action_user=action_user,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            notes="Refinanciamiento SNTE generado",
            log_message="Estatus de caso persistido tras generar refinanciamiento",
            route="generar_refinanciamiento",
        )
    except Exception as e:
        db.rollback()
        log.exception(
            "Documentos de refinanciamiento generados, pero fallo la persistencia del estatus",
            extra={"case_id": case_id},
        )
        msg = urllib.parse.quote(
            f"Refinanciamiento generado, pero no se pudo actualizar el estatus: {str(e)}"
        )
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)

    try:
        _schedule_generated_document_tasks(
            background_tasks=background_tasks,
            case=case,
            docs=docs,
            case_id=case_id,
        )
        _log_background_notification_enqueued(
            db=db,
            case=case,
            generated_by=action_user,
            route="generar_refinanciamiento",
            actor_user_id=actor_user_id,
            actor_role=actor_role,
        )
    except Exception as e:
        log.exception(
            "Estatus de refinanciamiento persistido, pero fallo la programacion de tareas en segundo plano",
            extra={"case_id": case_id},
        )
        msg = urllib.parse.quote(
            f"Refinanciamiento generado y estatus actualizado, pero fallaron tareas en segundo plano: {str(e)}"
        )
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)

    log.info(
        "Refinanciamiento generado correctamente",
        extra={"case_id": case_id, "docs": [doc.id for doc in docs]},
    )

    msg = urllib.parse.quote(
        "Refinanciamiento generado. La subida a SharePoint se procesara en segundo plano."
    )
    return RedirectResponse(url=f"/casos/{case_id}?success={msg}", status_code=302)
