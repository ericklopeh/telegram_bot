from __future__ import annotations

from typing import Generator

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import exists, func, not_
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db_session
from app.domain import constants as C
from app.models.case import Case
from app.models.document import Document
from app.models.user import UserRole
from app.services.case_service import CaseService
from app.web.auth import get_current_user, require_login

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")

# Estados considerados "cerrados" para el conteo de casos abiertos (operativo).
_CERRADOS_OPERATIVOS = (
    C.ST_PED_CERRADO,
    C.ST_PED_RECHAZADO,
    C.ST_PED_COMPRA,
    C.ST_REV_CERRADO,
    C.ST_REV_RECHAZADO,
    C.ST_REV_SIN_LIQUIDEZ,
)

_MAX_CHECKLIST_SCAN = 150


def get_web_db() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


def _cases_query(db: Session, usuario: dict):
    q = db.query(Case)
    if usuario.get("rol") == UserRole.VENDEDOR.value:
        q = q.filter(Case.seller_name == usuario.get("nombre"))
    return q


def _count_pedidos_checklist_incompleto(db: Session, usuario: dict, case_svc: CaseService) -> tuple[int, bool]:
    """Cuenta pedidos en recibido/corrección sin checklist completo (tope _MAX_CHECKLIST_SCAN)."""
    q = (
        _cases_query(db, usuario)
        .filter(
            Case.case_type == C.CASE_TYPE_PEDIDO,
            Case.order_type.isnot(None),
            Case.current_status.in_((C.ST_PED_RECIBIDO, C.ST_PED_CORRECCION)),
        )
        .order_by(Case.updated_at.desc())
        .limit(_MAX_CHECKLIST_SCAN)
    )
    rows = q.all()
    incomplete = sum(1 for c in rows if not case_svc.pedido_has_all_documents(db, c))
    capped = len(rows) >= _MAX_CHECKLIST_SCAN
    return incomplete, capped


def _doc_status_count(db: Session, usuario: dict, upload_status: str) -> int:
    q = (
        db.query(func.count(Document.id))
        .select_from(Document)
        .join(Case, Document.case_id == Case.id)
        .filter(
            Document.is_active.is_(True),
            Document.upload_status == upload_status,
        )
    )
    if usuario.get("rol") == UserRole.VENDEDOR.value:
        q = q.filter(Case.seller_name == usuario.get("nombre"))
    return int(q.scalar() or 0)


def _build_metrics(db: Session, usuario: dict) -> dict:
    base = _cases_query(db, usuario)
    settings = get_settings()
    case_svc = CaseService(settings)

    total_abiertos = base.filter(not_(Case.current_status.in_(_CERRADOS_OPERATIVOS))).count()

    pendientes_autorizacion = base.filter(Case.current_status == C.ST_PED_PREP_AUT).count()
    autorizaciones_generadas = base.filter(Case.current_status == C.ST_PED_AUT_GENERADA).count()
    pendientes_compulsa = base.filter(Case.current_status == C.ST_PED_PEND_COMPULSA).count()
    compulsa_ok = base.filter(Case.current_status == C.ST_PED_COMPULSA_OK).count()

    sn_excel = exists().where(
        Document.case_id == Case.id,
        Document.is_active.is_(True),
        Document.document_type == C.DOC_AUTORIZACION_SNTE,
    )
    prep_sin_excel_snte = base.filter(
        Case.case_type == C.CASE_TYPE_PEDIDO,
        Case.current_status == C.ST_PED_PREP_AUT,
        not_(sn_excel),
    ).count()

    docs_upload_failed = _doc_status_count(db, usuario, "UPLOAD_FAILED")
    docs_pending_upload = _doc_status_count(db, usuario, "PENDING_UPLOAD")

    checklist_incompleto, checklist_capped = _count_pedidos_checklist_incompleto(db, usuario, case_svc)

    g = db.query(Case.current_status, func.count(Case.id))
    if usuario.get("rol") == UserRole.VENDEDOR.value:
        g = g.filter(Case.seller_name == usuario.get("nombre"))
    rows = g.group_by(Case.current_status).order_by(func.count(Case.id).desc()).all()

    por_estado = [{"estado": estado, "total": int(n)} for estado, n in rows]

    return {
        "total_abiertos": total_abiertos,
        "pendientes_autorizacion": pendientes_autorizacion,
        "autorizaciones_generadas": autorizaciones_generadas,
        "pendientes_compulsa": pendientes_compulsa,
        "compulsa_ok": compulsa_ok,
        "prep_sin_excel_snte": prep_sin_excel_snte,
        "docs_upload_failed": int(docs_upload_failed),
        "docs_pending_upload": int(docs_pending_upload),
        "pedidos_checklist_incompleto": checklist_incompleto,
        "pedidos_checklist_incompleto_capped": checklist_capped,
        "por_estado": por_estado,
    }


@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)
    metricas = _build_metrics(db, usuario or {})

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "usuario": usuario,
            "metricas": metricas,
        },
    )
