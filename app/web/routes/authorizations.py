import logging
import urllib.parse

from fastapi import APIRouter, Depends, Request, BackgroundTasks
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


@router.post("/casos/{case_id}/generar-autorizacion")
async def generar_autorizacion(
    case_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_web_db)
):
    # Proteger por roles
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
        
        # 1. Transicionar estatus del caso
        from app.services.case_service import CaseService
        from app.config import get_settings
        from app.domain import constants as C
        
        case_svc = CaseService(get_settings())
        case_svc.transition_case_status(
            db, 
            case, 
            C.ST_PED_AUT_GENERADA, 
            notes="Autorización SNTE generada", 
            action_user=action_user
        )

        # 2. Notificar por Telegram vía background_tasks
        from app.services.notification_service import notify_snte_generation_from_web
        background_tasks.add_task(notify_snte_generation_from_web, case_id)

        # 3. Subir a SharePoint vía background_tasks
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
                filename=doc.stored_filename
            )
            background_tasks.add_task(sp_service.upload_document, payload)

        msg = urllib.parse.quote("Autorización generada. La subida a SharePoint se procesará en segundo plano.")
        return RedirectResponse(url=f"/casos/{case_id}?success={msg}", status_code=302)

    except TemplateNotFoundError as e:
        db.rollback()
        msg = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)
    except Exception as e:
        db.rollback()
        log.exception("Error generando autorización SNTE", extra={"case_id": case_id})
        msg = urllib.parse.quote(f"Error generando autorización: {str(e)}")
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)


# ---------------------------------------------------------------------------
# Refinanciamiento
# ---------------------------------------------------------------------------

def _build_refi_payload(form: dict) -> dict:
    """Construye el payload normalizado para RefinanciamientoService.

    Acepta hasta 5 productos y 5 saldos a reestructurar.

    Campos esperados del formulario HTML:
      Datos agremiado:
        nombre, rfc, categoria, domicilio, tel_part, tel_celular, correo,
        fecha_venta (DD/MM/YYYY)
      Productos (N = 1..5):
        prod_{N}_nombre, prod_{N}_codigo, prod_{N}_trans, prod_{N}_precio
      Saldos a reestructurar (N = 1..5):
        refi_folio_{N}, refi_descuento_{N}, refi_saldo_{N}
      Datos de descuento:
        folio, semana, monto_total, monto_vta_nueva,
        qna_inicial (QQ-AAAA), plazo_qnas, descuento_qna
      Observaciones:
        observaciones
    """
    payload: dict = {}

    # ── Datos del agremiado ──────────────────────────────────────────────
    for campo in ("nombre", "rfc", "categoria", "domicilio",
                  "tel_part", "tel_celular", "correo", "fecha_venta"):
        payload[campo] = form.get(campo, "").strip()

    # ── Productos (hasta 5) ──────────────────────────────────────────────
    for i in range(1, 6):
        for sub in ("nombre", "codigo", "trans", "precio"):
            key = f"prod_{i}_{sub}"
            payload[key] = form.get(key, "").strip()

    # ── Saldos a reestructurar (hasta 5) ────────────────────────────────
    for i in range(1, 6):
        for sub in ("folio", "descuento", "saldo"):
            key = f"refi_{sub}_{i}"
            payload[key] = form.get(key, "").strip()

    # ── Datos de descuento / crédito ─────────────────────────────────────
    for campo in ("folio", "semana", "monto_total", "monto_vta_nueva",
                  "qna_inicial", "plazo_qnas", "descuento_qna"):
        payload[campo] = form.get(campo, "").strip()

    # ── Observaciones ─────────────────────────────────────────────────────
    payload["observaciones"] = form.get("observaciones", "").strip()

    return payload


@router.post("/casos/{case_id}/generar-refinanciamiento")
async def generar_refinanciamiento(
    case_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_web_db),
) -> RedirectResponse:
    """Genera el Excel de refinanciamiento y el PDF Orden SNTE para un caso."""

    # ── Autenticación y autorización ─────────────────────────────────────
    redirect = require_roles(request, db, _ROLES_AUT)
    if redirect:
        return redirect

    user = get_current_user(request, db)
    action_user = user.get("nombre", "web_user") if user else "web_user"

    # ── Verificar que el caso existe ─────────────────────────────────────
    case = db.query(Case).filter(Case.id == case_id).first()
    if not case:
        return RedirectResponse(url="/casos", status_code=302)

    # ── Leer y normalizar form data ───────────────────────────────────────
    raw_form = await request.form()
    form_data = _build_refi_payload(dict(raw_form))

    log.info(
        "Iniciando generación de refinanciamiento",
        extra={"case_id": case_id, "action_user": action_user},
    )

    try:
        # ── Generar documentos ────────────────────────────────────────────
        refi_service = RefinanciamientoService(db)
        docs = refi_service.generate_for_case(case_id, form_data, action_user)
        # El servicio ya hace db.commit() internamente.

        # ── Transicionar estatus del caso ─────────────────────────────────
        from app.config import get_settings
        from app.domain import constants as C
        from app.services.case_service import CaseService

        case_svc = CaseService(get_settings())
        case_svc.transition_case_status(
            db,
            case,
            C.ST_PED_AUT_GENERADA,
            notes="Refinanciamiento SNTE generado",
            action_user=action_user,
        )

        # ── Notificación Telegram (background) ───────────────────────────
        from app.services.notification_service import notify_snte_generation_from_web
        background_tasks.add_task(notify_snte_generation_from_web, case_id)

        # ── Subir a SharePoint vía background_tasks ───────────────────────
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

        log.info(
            "Refinanciamiento generado correctamente",
            extra={"case_id": case_id, "docs": [d.id for d in docs]},
        )

        msg = urllib.parse.quote(
            "Refinanciamiento generado. La subida a SharePoint se procesará en segundo plano."
        )
        return RedirectResponse(url=f"/casos/{case_id}?success={msg}", status_code=302)


    except (TemplateNotFoundError, RefiTemplateNotFoundError) as e:
        db.rollback()
        log.warning("Plantilla no encontrada al generar refinanciamiento", extra={"case_id": case_id, "error": str(e)})
        msg = urllib.parse.quote(str(e))
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)

    except ValueError as e:
        db.rollback()
        log.warning("Validación fallida al generar refinanciamiento", extra={"case_id": case_id, "error": str(e)})
        msg = urllib.parse.quote(f"Error de validación: {str(e)}")
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)

    except Exception as e:
        db.rollback()
        log.exception("Error inesperado generando refinanciamiento", extra={"case_id": case_id})
        msg = urllib.parse.quote(f"Error generando refinanciamiento: {str(e)}")
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)
