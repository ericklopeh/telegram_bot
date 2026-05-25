import logging
import mimetypes
import os
from typing import Generator

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload
from starlette.responses import RedirectResponse

from app.config import get_settings
from app.db.session import get_db_session
from app.domain import constants as C
from app.domain.constants import doc_type_label
from app.models.case import Case
from app.models.user import UserRole
from app.services.action_guard_service import (
    build_case_action_state,
    can_generate_authorization,
    can_retry_sharepoint,
    can_upload_document,
)
from app.services.case_service import CaseService
from app.services.sharepoint_document_service import (
    SharePointDocumentService,
    SharePointUploadPayload,
)
from app.web.auth import (
    ROLES_ADMIN_SISTEMAS,
    get_current_user,
    require_login,
    require_roles,
    web_should_scope_vendedor_cases,
)
from app.web.paths import TEMPLATES_DIR

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)

log = logging.getLogger(__name__)


def get_web_db() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


def _can_upload_document_web(usuario: dict, caso: Case) -> bool:
    """Vendedor solo su caso; admin/sistemas cualquier caso."""
    if get_settings().web_rbac_relaxed:
        return True
    rol = usuario.get("rol")
    if rol in ROLES_ADMIN_SISTEMAS:
        return True
    if rol == UserRole.VENDEDOR.value:
        return caso.seller_name == usuario.get("nombre")
    return False


@router.get("/casos")
def listar_casos(
    request: Request,
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)

    query = db.query(Case)

    if web_should_scope_vendedor_cases(usuario):
        query = query.filter(Case.seller_name == usuario["nombre"])

    casos = query.order_by(Case.created_at.desc()).limit(50).all()

    return templates.TemplateResponse(
        request=request,
        name="cases.html",
        context={
            "usuario": usuario,
            "casos": casos,
        }
    )


@router.get("/casos/{case_id}")
def detalle_caso(
    case_id: int,
    request: Request,
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)

    caso = db.query(Case).filter(Case.id == case_id).first()

    if not caso:
        return RedirectResponse(url="/casos", status_code=302)

    if web_should_scope_vendedor_cases(usuario) and caso.seller_name != usuario["nombre"]:
        return RedirectResponse(url="/casos", status_code=302)

    from app.models.talon_review import TalonReview
    from app.models.document import Document
    from app.models.case_event import CaseEvent

    ultima_revision = (
        db.query(TalonReview)
        .filter(TalonReview.case_id == caso.id)
        .order_by(TalonReview.created_at.desc())
        .first()
    )

    documentos = (
        db.query(Document)
        .options(joinedload(Document.ocr_results))
        .filter(Document.case_id == caso.id, Document.is_active == True)
        .order_by(Document.uploaded_at.desc())
        .all()
    )

    case_events = (
        db.query(CaseEvent)
        .options(joinedload(CaseEvent.actor))
        .filter(CaseEvent.case_id == caso.id)
        .order_by(CaseEvent.created_at.desc())
        .all()
    )

    has_snte_authorization = any(d.document_type == C.DOC_AUTORIZACION_SNTE for d in documentos)
    has_snte_order_pdf = any(d.document_type == C.DOC_ORDEN_SNTE_PDF for d in documentos)
    has_refi_authorization = any(d.document_type == C.DOC_AUTORIZACION_REFI for d in documentos)
    upload_document_types = [
        ("talon", "Talón"),
        (C.DOC_PEDIDO, doc_type_label(C.DOC_PEDIDO)),
        (C.DOC_ORDEN_DESCUENTO, doc_type_label(C.DOC_ORDEN_DESCUENTO)),
        (C.DOC_CARATULA_BANCARIA, doc_type_label(C.DOC_CARATULA_BANCARIA)),
        (C.DOC_REVISION_EVIDENCIA, doc_type_label(C.DOC_REVISION_EVIDENCIA)),
    ]

    from app.models.authorization_job import AuthorizationJob
    authorization_jobs = (
        db.query(AuthorizationJob)
        .filter(AuthorizationJob.case_id == caso.id)
        .order_by(AuthorizationJob.created_at.desc())
        .all()
    )

    case_svc = CaseService(get_settings())
    pedido_checklist_ok = (
        caso.case_type == C.CASE_TYPE_PEDIDO and case_svc.pedido_has_all_documents(db, caso)
    )
    pedido_checklist_text = (
        case_svc.get_pedido_checklist(db, caso)
        if caso.case_type == C.CASE_TYPE_PEDIDO and caso.order_type
        else ""
    )
    snte_status_ok = caso.current_status in (
        C.ST_PED_PREP_AUT,
        C.ST_PED_AUT_GENERADA,
    )

    from app.services.ocr_service import OCRService

    ocr_prefill = OCRService.build_case_autorizacion_prefill(db, caso.id)

    from app.web.services.case_timeline import build_case_timeline

    case_timeline = build_case_timeline(case_events)

    action_guard = build_case_action_state(db, caso, usuario)

    from app.web.services.workflow_visualization import build_workflow_pipeline
    from app.services.workflow_state_service import WORKFLOW_STATE_LABELS, normalize_workflow_state

    workflow_pipeline = (
        build_workflow_pipeline(db, caso) if caso.case_type == C.CASE_TYPE_PEDIDO else None
    )
    wf_state = normalize_workflow_state(
        getattr(caso, "workflow_state", None), legacy_status=caso.current_status
    )

    from app.services.case_document_service import CaseDocumentService

    doc_p24_summary = CaseDocumentService().summarize(db, caso)

    return templates.TemplateResponse(
        request=request,
        name="case_detail.html",
        context={
            "usuario": usuario,
            "web_rbac_relaxed": get_settings().web_rbac_relaxed,
            "caso": caso,
            "ultima_revision": ultima_revision,
            "documentos": documentos,
            "doc_type_label": doc_type_label,
            "has_snte_authorization": has_snte_authorization,
            "has_snte_order_pdf": has_snte_order_pdf,
            "has_refi_authorization": has_refi_authorization,
            "authorization_jobs": authorization_jobs,
            "upload_document_types": upload_document_types,
            "case_events": case_events,
            "case_timeline": case_timeline,
            "pedido_checklist_ok": pedido_checklist_ok,
            "pedido_checklist_text": pedido_checklist_text,
            "snte_status_ok": snte_status_ok,
            "ocr_prefill": ocr_prefill,
            "action_guard": action_guard,
            "workflow_pipeline": workflow_pipeline,
            "workflow_state": wf_state,
            "workflow_state_label": WORKFLOW_STATE_LABELS.get(wf_state, wf_state),
            "can_recalc_workflow": (usuario or {}).get("rol") in ROLES_ADMIN_SISTEMAS
            or get_settings().web_rbac_relaxed,
            "doc_p24_summary": doc_p24_summary,
        }
    )


@router.post("/casos/{case_id}/recalcular-estado")
async def recalcular_estado_caso(
    case_id: int,
    request: Request,
    db: Session = Depends(get_web_db),
):
    import urllib.parse

    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    from app.services.workflow_transition_service import recalculate_case_workflow_state

    try:
        _case, new_state, warning = recalculate_case_workflow_state(
            db, case_id, usuario or {}, apply=True
        )
        db.commit()
        msg = urllib.parse.quote(
            warning or f"Estado recalculado: {new_state}"
        )
        return RedirectResponse(url=f"/casos/{case_id}?success={msg}", status_code=302)
    except Exception as exc:
        db.rollback()
        err = urllib.parse.quote(str(exc))
        return RedirectResponse(url=f"/casos/{case_id}?error={err}", status_code=302)


@router.post("/casos/{case_id}/workflow/transition")
async def workflow_transition_caso(
    case_id: int,
    request: Request,
    db: Session = Depends(get_web_db),
    target_state: str = Form(...),
):
    import urllib.parse

    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    from app.services.workflow_transition_service import request_transition

    try:
        _case, err = request_transition(db, case_id, target_state.strip(), usuario or {})
        if err:
            db.rollback()
            return RedirectResponse(
                url=f"/casos/{case_id}?error={urllib.parse.quote(err)}", status_code=302
            )
        db.commit()
        msg = urllib.parse.quote(f"Transición aplicada: {target_state}")
        return RedirectResponse(url=f"/casos/{case_id}?success={msg}", status_code=302)
    except Exception as exc:
        db.rollback()
        return RedirectResponse(
            url=f"/casos/{case_id}?error={urllib.parse.quote(str(exc))}", status_code=302
        )


@router.post("/casos/{case_id}/upload-document")
def upload_document(
    case_id: int,
    request: Request,
    document_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)
    caso = db.query(Case).filter(Case.id == case_id).first()

    if not caso:
        return RedirectResponse(url="/casos", status_code=302)

    if not _can_upload_document_web(usuario, caso):
        log.warning(
            "Subida de documento rechazada: rol no autorizado o caso no propio del vendedor",
            extra={
                "case_id": case_id,
                "user_id": usuario.get("id"),
                "rol": usuario.get("rol"),
            },
        )
        return RedirectResponse(url=f"/casos/{case_id}", status_code=302)

    if caso.case_type == C.CASE_TYPE_PEDIDO and document_type in {
        C.DOC_PEDIDO,
        C.DOC_ORDEN_DESCUENTO,
        C.DOC_CARATULA_BANCARIA,
    }:
        ok_guard, guard_reason = can_upload_document(db, caso, document_type, usuario)
        if not ok_guard:
            import urllib.parse

            msg = urllib.parse.quote(guard_reason or "Acción no permitida para este caso.")
            return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)

    from app.services.case_document_service import (
        CaseDocumentService,
        LEGACY_WEB_UPLOAD_TYPES,
    )

    if document_type not in LEGACY_WEB_UPLOAD_TYPES:
        return RedirectResponse(url=f"/casos/{case_id}", status_code=302)

    content = file.file.read()
    if not content:
        import urllib.parse

        return RedirectResponse(
            url=f"/casos/{case_id}?error={urllib.parse.quote('Archivo vacío.')}",
            status_code=302,
        )

    from app.models.case_history import CaseHistory

    try:
        new_doc = CaseDocumentService().upload_document_legacy_web(
            db,
            caso,
            document_type,
            content,
            original_filename=file.filename,
            mime_type=file.content_type,
            uploaded_by=usuario.get("nombre"),
            actor_user_id=usuario.get("id"),
            actor_role=usuario.get("rol"),
        )
    except ValueError as exc:
        import urllib.parse

        db.rollback()
        return RedirectResponse(
            url=f"/casos/{case_id}?error={urllib.parse.quote(str(exc))}",
            status_code=302,
        )

    # Crear CaseHistory
    history_entry = CaseHistory(
        case_id=case_id,
        old_status=caso.current_status,
        new_status=caso.current_status,
        action_source="web",
        action_user=usuario.get("nombre", "web_user"),
        notes=f"Documento subido desde web (prueba): {document_type} ({file.filename})"
    )
    db.add(history_entry)

    db.commit()
    db.refresh(new_doc)

    from app.services.ocr_service import OCRService, OCR_ELIGIBLE_DOCUMENT_TYPES

    if document_type in OCR_ELIGIBLE_DOCUMENT_TYPES:
        try:
            OCRService(db).process_document(
                new_doc.id,
                action_user=usuario.get("nombre", "web_user"),
                source="web",
            )
        except Exception:
            log.exception("OCR automático falló tras subida doc=%s", new_doc.id)

    return RedirectResponse(url=f"/casos/{case_id}", status_code=302)


@router.post("/casos/{case_id}/documentos/{document_id}/procesar-ocr")
def procesar_ocr_route(
    case_id: int,
    document_id: int,
    request: Request,
    return_to: str = Form(None),
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    redirect = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)
    caso = db.query(Case).filter(Case.id == case_id).first()
    if not caso:
        return RedirectResponse(url="/casos", status_code=302)

    from app.models.document import Document
    doc = db.query(Document).filter(Document.id == document_id, Document.case_id == case_id).first()
    
    if not doc:
        return RedirectResponse(url=f"/casos/{case_id}", status_code=302)
        
    from app.services.ocr_service import OCRService, OCR_ELIGIBLE_DOCUMENT_TYPES

    if doc.document_type not in OCR_ELIGIBLE_DOCUMENT_TYPES:
        return RedirectResponse(url=f"/casos/{case_id}", status_code=302)

    OCRService(db).process_document(
        document_id=document_id,
        action_user=usuario.get("nombre", "web_user"),
        source="web",
    )
    
    from app.models.case_history import CaseHistory
    
    history_entry = CaseHistory(
        case_id=case_id,
        old_status=caso.current_status,
        new_status=caso.current_status,
        action_source="web",
        action_user=usuario.get("nombre", "web_user"),
        notes=f"OCR solicitado para documento: {doc.document_type} ({doc.original_filename or doc.stored_filename})"
    )
    db.add(history_entry)
    db.commit()
    
    if return_to == "revision-talon":
        return RedirectResponse(url=f"/casos/{case_id}/revision-talon", status_code=302)
    
    return RedirectResponse(url=f"/casos/{case_id}", status_code=302)


@router.get("/documentos/{document_id}/ver")
def ver_documento_route(
    document_id: int,
    request: Request,
    db: Session = Depends(get_web_db)
):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    from app.models.document import Document
    doc = db.query(Document).filter(Document.id == document_id).first()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado en base de datos")
        
    if not doc.file_path or not os.path.exists(doc.file_path):
        raise HTTPException(status_code=404, detail="El archivo físico no existe en el servidor")

    usuario = get_current_user(request, db)
    caso = db.query(Case).filter(Case.id == doc.case_id).first()
    if not caso:
        raise HTTPException(status_code=404, detail="Caso no encontrado en base de datos")
    if web_should_scope_vendedor_cases(usuario) and caso.seller_name != usuario.get("nombre"):
        log.warning(
            "Vista de documento denegada: vendedor sin titularidad del caso",
            extra={"document_id": document_id, "case_id": caso.id, "user_id": usuario.get("id")},
        )
        raise HTTPException(status_code=403, detail="No autorizado")

    mime_type = doc.mime_type
    if not mime_type:
        mime_type, _ = mimetypes.guess_type(doc.file_path)
        if not mime_type:
            mime_type = "application/octet-stream"
            
    return FileResponse(
        path=doc.file_path,
        media_type=mime_type,
        filename=doc.original_filename or doc.stored_filename,
        content_disposition_type="inline"  # force inline to open in browser instead of downloading if possible
    )


@router.post("/casos/{case_id}/documentos/{document_id}/reintentar-sharepoint")
def reintentar_sharepoint_documento(
    case_id: int,
    document_id: int,
    request: Request,
    db: Session = Depends(get_web_db),
):
    import urllib.parse

    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)
    caso = db.query(Case).filter(Case.id == case_id).first()
    if not caso:
        return RedirectResponse(url="/casos", status_code=302)

    if web_should_scope_vendedor_cases(usuario) and caso.seller_name != usuario.get("nombre"):
        return RedirectResponse(url=f"/casos/{case_id}", status_code=302)

    doc = db.query(Document).filter(Document.id == document_id, Document.case_id == case_id).first()
    if not doc:
        return RedirectResponse(url=f"/casos/{case_id}", status_code=302)

    ok, reason = can_retry_sharepoint(db, caso, usuario, document_id=document_id)
    if not ok:
        msg = urllib.parse.quote(reason or "No se puede reintentar la subida.")
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)

    from app.services.sharepoint_sync_service import SharePointSyncService

    try:
        result = SharePointSyncService().sync_document(
            db,
            document_id,
            actor_user_id=usuario.get("id"),
            actor_role=usuario.get("rol"),
            is_retry=True,
        )
        db.commit()
        if result.ok:
            msg = urllib.parse.quote("Documento sincronizado en SharePoint correctamente.")
            return RedirectResponse(url=f"/casos/{case_id}?success={msg}", status_code=302)
        msg = urllib.parse.quote(result.error or "Error al subir a SharePoint.")
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)
    except Exception as exc:
        db.rollback()
        log.exception("Reintento SharePoint fallido", extra={"document_id": document_id})
        msg = urllib.parse.quote(f"Error al reintentar subida: {exc}")
        return RedirectResponse(url=f"/casos/{case_id}?error={msg}", status_code=302)
