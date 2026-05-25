"""Rutas web gestión documental P24."""

from __future__ import annotations

import logging
import urllib.parse
from typing import Generator

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.db.session import get_db_session
from app.domain import constants as C
from app.domain.constants import doc_type_label
from app.models.case import Case
from app.models.user import UserRole
from app.services.beta_safe_mode_service import BetaSafeModeService
from app.services.case_document_service import CaseDocumentService
from app.web.auth import (
    ROLES_ADMIN_SISTEMAS,
    get_current_user,
    require_login,
    web_should_scope_vendedor_cases,
)
from app.web.paths import TEMPLATES_DIR

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)
log = logging.getLogger(__name__)
_doc_svc = CaseDocumentService()
_safe = BetaSafeModeService()


def get_web_db() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


def _can_manage_documents(usuario: dict, caso: Case) -> bool:
    rol = usuario.get("rol")
    if rol in ROLES_ADMIN_SISTEMAS:
        return True
    if rol == UserRole.VENDEDOR.value:
        return caso.seller_name == usuario.get("nombre")
    return rol in (UserRole.AUTORIZACION.value, UserRole.COMPRAS.value, UserRole.ADMIN.value)


def _can_validate_documents(usuario: dict) -> bool:
    return usuario.get("rol") in ROLES_ADMIN_SISTEMAS or usuario.get("rol") in (
        UserRole.COMPULSA.value,
        UserRole.AUTORIZACIONES.value,
    )


def _load_case(db: Session, case_id: int, usuario: dict) -> Case | None:
    caso = db.query(Case).filter(Case.id == case_id).first()
    if not caso:
        return None
    if web_should_scope_vendedor_cases(usuario) and caso.seller_name != usuario["nombre"]:
        return None
    return caso


def _redirect_case(case_id: int, *, error: str | None = None, success: str | None = None) -> RedirectResponse:
    url = f"/casos/{case_id}/documentos"
    if error:
        url += f"?error={urllib.parse.quote(error)}"
    elif success:
        url += f"?success={urllib.parse.quote(success)}"
    return RedirectResponse(url=url, status_code=302)


@router.get("/casos/{case_id}/documentos")
@router.get("/cases/{case_id}/documents")
def list_case_documents(
    case_id: int,
    request: Request,
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)
    caso = _load_case(db, case_id, usuario)
    if not caso:
        return RedirectResponse(url="/casos", status_code=302)

    checklist = _doc_svc.build_checklist(db, caso)
    documentos = _doc_svc.list_active_documents(db, caso.id)
    historial = _doc_svc.list_all_documents(db, caso.id)
    summary = _doc_svc.summarize(db, caso)
    missing = _doc_svc.missing_required_types(db, caso)

    upload_types = [
        (C.DOC_PEDIDO, doc_type_label(C.DOC_PEDIDO)),
        (C.DOC_ORDEN_DESCUENTO, doc_type_label(C.DOC_ORDEN_DESCUENTO)),
        (C.DOC_AUTORIZACION_SNTE, doc_type_label(C.DOC_AUTORIZACION_SNTE)),
        (C.DOC_ORDEN_SNTE_PDF, doc_type_label(C.DOC_ORDEN_SNTE_PDF)),
        (C.DOC_AUTORIZACION_REFI, doc_type_label(C.DOC_AUTORIZACION_REFI)),
        (C.DOC_CARATULA_BANCARIA, doc_type_label(C.DOC_CARATULA_BANCARIA)),
        (C.DOC_INE, doc_type_label(C.DOC_INE)),
        (C.DOC_ESTADO_CUENTA, doc_type_label(C.DOC_ESTADO_CUENTA)),
        (C.DOC_OTRO, doc_type_label(C.DOC_OTRO)),
    ]

    return templates.TemplateResponse(
        request=request,
        name="case_documents.html",
        context={
            "usuario": usuario,
            "caso": caso,
            "checklist": checklist,
            "documentos": documentos,
            "historial": historial,
            "summary": summary,
            "missing_labels": [doc_type_label(m) for m in missing],
            "upload_types": upload_types,
            "can_upload": _can_manage_documents(usuario, caso),
            "can_validate": _can_validate_documents(usuario),
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success"),
        },
    )


@router.post("/casos/{case_id}/documentos/upload")
@router.post("/cases/{case_id}/documents/upload")
async def upload_case_document(
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
    caso = _load_case(db, case_id, usuario)
    if not caso or not _can_manage_documents(usuario, caso):
        return _redirect_case(case_id, error="No autorizado para subir documentos.")

    content = await file.read()
    if not content:
        return _redirect_case(case_id, error="Archivo vacío.")

    try:
        _doc_svc.upload_document(
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
        db.commit()
        return _redirect_case(case_id, success="Documento subido correctamente.")
    except ValueError as exc:
        db.rollback()
        return _redirect_case(case_id, error=str(exc))


@router.post("/casos/{case_id}/documentos/{document_id}/validate")
@router.post("/cases/{case_id}/documents/{document_id}/validate")
def validate_case_document(
    case_id: int,
    document_id: int,
    request: Request,
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)
    if not _can_validate_documents(usuario):
        return _redirect_case(case_id, error="No autorizado para validar documentos.")

    caso = _load_case(db, case_id, usuario)
    if not caso:
        return RedirectResponse(url="/casos", status_code=302)

    try:
        _doc_svc.validate_document(
            db,
            caso,
            document_id,
            validated_by=usuario.get("nombre"),
            actor_user_id=usuario.get("id"),
            actor_role=usuario.get("rol"),
        )
        db.commit()
        return _redirect_case(case_id, success="Documento validado.")
    except ValueError as exc:
        db.rollback()
        return _redirect_case(case_id, error=str(exc))


@router.post("/casos/{case_id}/documentos/{document_id}/reject")
@router.post("/cases/{case_id}/documents/{document_id}/reject")
def reject_case_document(
    case_id: int,
    document_id: int,
    request: Request,
    rejection_reason: str = Form(...),
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)
    if not _can_validate_documents(usuario):
        return _redirect_case(case_id, error="No autorizado para rechazar documentos.")

    caso = _load_case(db, case_id, usuario)
    if not caso:
        return RedirectResponse(url="/casos", status_code=302)

    try:
        _doc_svc.reject_document(
            db,
            caso,
            document_id,
            rejection_reason,
            validated_by=usuario.get("nombre"),
            actor_user_id=usuario.get("id"),
            actor_role=usuario.get("rol"),
        )
        db.commit()
        return _redirect_case(case_id, success="Documento rechazado.")
    except ValueError as exc:
        db.rollback()
        return _redirect_case(case_id, error=str(exc))


@router.post("/casos/{case_id}/documentos/{document_id}/replace")
@router.post("/cases/{case_id}/documents/{document_id}/replace")
async def replace_case_document(
    case_id: int,
    document_id: int,
    request: Request,
    file: UploadFile = File(...),
    confirm_text: str = Form(""),
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)
    caso = _load_case(db, case_id, usuario)
    if not caso or not _can_manage_documents(usuario, caso):
        return _redirect_case(case_id, error="No autorizado.")

    content = await file.read()
    if not content:
        return _redirect_case(case_id, error="Archivo vacío.")

    ok, err = _safe.require_confirmation(
        "replace_document",
        _safe.phrase_replace_document(document_id),
        confirm_text,
        entity_type="document",
        entity_id=document_id,
        username=usuario.get("username"),
    )
    if not ok:
        return _redirect_case(case_id, error=err or "Confirmación requerida")

    try:
        _doc_svc.replace_document(
            db,
            caso,
            document_id,
            content,
            original_filename=file.filename,
            mime_type=file.content_type,
            uploaded_by=usuario.get("nombre"),
            actor_user_id=usuario.get("id"),
            actor_role=usuario.get("rol"),
        )
        db.commit()
        return _redirect_case(case_id, success="Documento reemplazado.")
    except ValueError as exc:
        db.rollback()
        return _redirect_case(case_id, error=str(exc))
