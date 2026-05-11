import logging
import re
import urllib.parse

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.db.session import get_db_session
from app.models.case import Case
from app.models.user import UserRole
from app.services.authorization_service import AuthorizationService, TemplateNotFoundError
from app.services.refinanciamiento_service import (
    RefinanciamientoService,
    TemplateNotFoundError as RefiTemplateNotFoundError,
)
from app.services.sharepoint_document_service import SharePointDocumentService, SharePointUploadPayload
from app.web.auth import get_current_user, require_roles

log = logging.getLogger(__name__)

router = APIRouter()

_ROLES_AUT = [UserRole.ADMIN.value, UserRole.SISTEMAS.value, UserRole.AUTORIZACION.value]


def get_web_db():
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


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


def _persist_generated_status(
    *,
    db: Session,
    case: Case,
    case_id: int,
    action_user: str,
    notes: str,
    log_message: str,
) -> None:
    from app.config import get_settings
    from app.domain import constants as C
    from app.services.case_service import CaseService

    case_svc = CaseService(get_settings())
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
    redirect = require_roles(request, db, _ROLES_AUT)
    if redirect:
        return redirect

    user = get_current_user(request, db)
    action_user = user.get("nombre", "web_user") if user else "web_user"

    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return RedirectResponse(url="/casos", status_code=302)

    form = await request.form()
    form_data = dict(form)

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

    try:
        _persist_generated_status(
            db=db,
            case=case,
            case_id=case_id,
            action_user=action_user,
            notes="Autorizacion SNTE generada",
            log_message="Estatus de caso persistido tras generar autorizacion SNTE",
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
    except Exception as e:
        log.exception(
            "Estatus SNTE persistido, pero fallo la programacion de tareas en segundo plano",
            extra={"case_id": case_id},
        )
        msg = urllib.parse.quote(
            f"Autorizacion generada y estatus actualizado, pero fallaron tareas en segundo plano: {str(e)}"
        )
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)

    msg = urllib.parse.quote(
        "Autorizacion generada. La subida a SharePoint se procesara en segundo plano."
    )
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
    redirect = require_roles(request, db, _ROLES_AUT)
    if redirect:
        return redirect

    user = get_current_user(request, db)
    action_user = user.get("nombre", "web_user") if user else "web_user"

    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return RedirectResponse(url="/casos", status_code=302)

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
        _persist_generated_status(
            db=db,
            case=case,
            case_id=case_id,
            action_user=action_user,
            notes="Refinanciamiento SNTE generado",
            log_message="Estatus de caso persistido tras generar refinanciamiento",
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
