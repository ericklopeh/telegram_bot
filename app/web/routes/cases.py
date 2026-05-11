import os
import shutil
import uuid
from typing import Generator

from fastapi import APIRouter, Request, Depends, File, UploadFile, Form
from fastapi.templating import Jinja2Templates
from starlette.responses import RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db_session
from app.domain import constants as C
from app.domain.constants import doc_type_label
from app.models.case import Case
from app.web.auth import get_current_user, require_login

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


def get_web_db() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


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

    if usuario["rol"] == "vendedor":
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

    if usuario["rol"] == "vendedor" and caso.seller_name != usuario["nombre"]:
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

    return templates.TemplateResponse(
        request=request,
        name="case_detail.html",
        context={
            "usuario": usuario,
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
        }
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

    # Validar que sea uno de los tipos permitidos
    allowed_types = {
        "talon",
        C.DOC_PEDIDO,
        C.DOC_ORDEN_DESCUENTO,
        C.DOC_CARATULA_BANCARIA,
        C.DOC_REVISION_EVIDENCIA,
    }
    if document_type not in allowed_types:
        return RedirectResponse(url=f"/casos/{case_id}", status_code=302)

    # Crear carpeta si no existe
    upload_dir = f"storage/uploads/{case_id}"
    os.makedirs(upload_dir, exist_ok=True)

    # Guardar archivo localmente
    file_extension = os.path.splitext(file.filename)[1] if file.filename else ""
    stored_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(upload_dir, stored_filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    from app.models.document import Document
    from app.models.case_history import CaseHistory

    # Crear Document
    new_doc = Document(
        case_id=case_id,
        document_type=document_type,
        original_filename=file.filename,
        stored_filename=stored_filename,
        file_path=file_path,
        mime_type=file.content_type,
        is_active=True,
        upload_status="LOCAL"
    )
    db.add(new_doc)

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

    usuario = get_current_user(request, db)
    
    caso = db.query(Case).filter(Case.id == case_id).first()
    if not caso:
        return RedirectResponse(url="/casos", status_code=302)
        
    from app.models.document import Document
    doc = db.query(Document).filter(Document.id == document_id, Document.case_id == case_id).first()
    
    if not doc:
        return RedirectResponse(url=f"/casos/{case_id}", status_code=302)
        
    from app.web.services.talon_ocr_service import process_ocr_document
    
    process_ocr_document(
        db=db,
        document_id=document_id,
        action_user=usuario.get("nombre", "web_user")
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

import os
import mimetypes
from fastapi import HTTPException
from fastapi.responses import FileResponse

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
