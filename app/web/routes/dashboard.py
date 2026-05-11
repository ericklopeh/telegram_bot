from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Generator

from fastapi import APIRouter, Depends, Query, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import exists, func, not_, select
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

_CORRECCION_RECHAZO_STATUSES = (
    C.ST_PED_RECHAZADO,
    C.ST_PED_CORRECCION,
    C.ST_REV_RECHAZADO,
    C.ST_REV_CORRECCION,
)

_RESUMEN_VENDEDORES_LIMIT = 25
_MAX_CHECKLIST_SCAN = 150
_PENDING_LIMIT_PER_SOURCE = 12
_PENDING_TABLE_LIMIT = 30

_PENDING_FILTERS = frozenset(
    {
        "all",
        "prep_aut",
        "compulsa",
        "sp_pending",
        "sp_failed",
        "correction",
        "missing_docs",
    }
)


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


def _normalize_pending_filter(raw: str | None) -> str:
    if not raw:
        return "all"
    k = raw.strip().lower()
    return k if k in _PENDING_FILTERS else "all"


def _track_pending(
    tracked: dict[int, tuple[Case, list[str]]],
    case: Case,
    problema: str,
) -> None:
    if case.id not in tracked:
        tracked[case.id] = (case, [])
    _, problems = tracked[case.id]
    if problema not in problems:
        problems.append(problema)


def _build_pending_table(
    db: Session,
    usuario: dict,
    *,
    filter_key: str = "all",
    limit: int = _PENDING_TABLE_LIMIT,
) -> list[dict]:
    """Casos con pendientes operativos (deduplicados), ordenados por última actualización."""
    fk = filter_key if filter_key in _PENDING_FILTERS else "all"
    settings = get_settings()
    case_svc = CaseService(settings)
    tracked: dict[int, tuple[Case, list[str]]] = {}
    base = _cases_query(db, usuario)
    cap = _PENDING_LIMIT_PER_SOURCE

    status_prep = ((C.ST_PED_PREP_AUT, "En preparación de autorización"),)
    status_compulsa = (
        (C.ST_PED_EN_COMPULSA, "En compulsa"),
        (C.ST_PED_PEND_COMPULSA, "Pendiente de compulsa"),
    )
    status_correction = (
        (C.ST_PED_RECHAZADO, "Pedido rechazado"),
        (C.ST_PED_CORRECCION, "Corrección de pedido solicitada"),
        (C.ST_REV_RECHAZADO, "Revisión rechazada"),
        (C.ST_REV_CORRECCION, "Corrección de revisión solicitada"),
    )

    if fk == "all":
        status_buckets: tuple[tuple[str, str], ...] = status_prep + status_compulsa + status_correction
    elif fk == "prep_aut":
        status_buckets = status_prep
    elif fk == "compulsa":
        status_buckets = status_compulsa
    elif fk == "correction":
        status_buckets = status_correction
    else:
        status_buckets = ()

    for status, label in status_buckets:
        for c in (
            base.filter(Case.current_status == status)
            .order_by(Case.updated_at.desc())
            .limit(cap)
            .all()
        ):
            _track_pending(tracked, c, label)

    if fk in ("all", "sp_pending", "sp_failed"):
        doc_specs: list[tuple[str, str]] = []
        if fk in ("all", "sp_pending"):
            doc_specs.append(
                ("PENDING_UPLOAD", "Documento con subida pendiente (SharePoint)"),
            )
        if fk in ("all", "sp_failed"):
            doc_specs.append(("UPLOAD_FAILED", "Documento con error de subida (SharePoint)"))
        for doc_status, label in doc_specs:
            stmt = (
                select(Document.case_id)
                .join(Case, Case.id == Document.case_id)
                .where(
                    Document.is_active.is_(True),
                    Document.upload_status == doc_status,
                )
            )
            if usuario.get("rol") == UserRole.VENDEDOR.value:
                stmt = stmt.where(Case.seller_name == usuario.get("nombre"))
            stmt = stmt.distinct().limit(cap)
            case_ids = list(db.execute(stmt).scalars().all())
            if not case_ids:
                continue
            for c in base.filter(Case.id.in_(case_ids)).all():
                _track_pending(tracked, c, label)

    if fk in ("all", "missing_docs"):
        for c in (
            base.filter(
                Case.case_type == C.CASE_TYPE_PEDIDO,
                Case.order_type.isnot(None),
                Case.current_status.in_((C.ST_PED_RECIBIDO, C.ST_PED_CORRECCION)),
            )
            .order_by(Case.updated_at.desc())
            .limit(40)
            .all()
        ):
            if not case_svc.pedido_has_all_documents(db, c):
                _track_pending(tracked, c, "Faltan documentos del checklist")

    sorted_items = sorted(
        tracked.items(),
        key=lambda it: it[1][0].updated_at,
        reverse=True,
    )[:limit]
    return [{"case": case, "problema": " · ".join(problems)} for _, (case, problems) in sorted_items]


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


def _case_counts_grouped_by_seller(db: Session, usuario: dict, *filters) -> dict[str, int]:
    q = db.query(Case.seller_name, func.count(Case.id)).filter(
        Case.seller_name.isnot(None),
        Case.seller_name != "",
    )
    for f in filters:
        q = q.filter(f)
    if usuario.get("rol") == UserRole.VENDEDOR.value:
        q = q.filter(Case.seller_name == usuario.get("nombre"))
    out: dict[str, int] = {}
    for name, n in q.group_by(Case.seller_name).all():
        if not name:
            continue
        key = str(name)
        if key.strip():
            out[key] = int(n)
    return out


def _doc_upload_failed_by_seller(db: Session, usuario: dict) -> dict[str, int]:
    q = (
        db.query(Case.seller_name, func.count(Document.id))
        .select_from(Document)
        .join(Case, Case.id == Document.case_id)
        .filter(
            Case.seller_name.isnot(None),
            Case.seller_name != "",
            Document.is_active.is_(True),
            Document.upload_status == "UPLOAD_FAILED",
        )
    )
    if usuario.get("rol") == UserRole.VENDEDOR.value:
        q = q.filter(Case.seller_name == usuario.get("nombre"))
    out: dict[str, int] = {}
    for name, n in q.group_by(Case.seller_name).all():
        if not name:
            continue
        key = str(name)
        if key.strip():
            out[key] = int(n)
    return out


def _build_resumen_vendedores(db: Session, usuario: dict) -> list[dict]:
    """Agregados por vendedor: pocas consultas GROUP BY, sin escanear todos los documentos."""
    u = usuario or {}
    abiertos = _case_counts_grouped_by_seller(
        db, u, not_(Case.current_status.in_(_CERRADOS_OPERATIVOS))
    )
    prep = _case_counts_grouped_by_seller(db, u, Case.current_status == C.ST_PED_PREP_AUT)
    compulsa = _case_counts_grouped_by_seller(
        db,
        u,
        Case.current_status.in_((C.ST_PED_EN_COMPULSA, C.ST_PED_PEND_COMPULSA)),
    )
    corr = _case_counts_grouped_by_seller(db, u, Case.current_status.in_(_CORRECCION_RECHAZO_STATUSES))
    failed = _doc_upload_failed_by_seller(db, u)

    def _score(s: str) -> int:
        return (
            abiertos.get(s, 0)
            + prep.get(s, 0)
            + compulsa.get(s, 0)
            + corr.get(s, 0)
            + failed.get(s, 0)
        )

    if u.get("rol") == UserRole.VENDEDOR.value:
        nm = u.get("nombre")
        if nm is None or str(nm).strip() == "":
            return []
        sellers = [str(nm)]
    else:
        pool = set(abiertos) | set(prep) | set(compulsa) | set(corr) | set(failed)
        active = [s for s in pool if _score(s) > 0]
        active.sort(key=lambda s: (abiertos.get(s, 0), _score(s)), reverse=True)
        sellers = active[:_RESUMEN_VENDEDORES_LIMIT]

    return [
        {
            "vendedor": s,
            "abiertos": abiertos.get(s, 0),
            "prep_aut": prep.get(s, 0),
            "compulsa": compulsa.get(s, 0),
            "correccion_rechazo": corr.get(s, 0),
            "sharepoint_error": failed.get(s, 0),
        }
        for s in sellers
    ]


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

    # SLA / tiempo operativo (timestamps existentes; sin historial adicional).
    umbral_24h = datetime.now(timezone.utc) - timedelta(hours=24)
    filtro_abierto = not_(Case.current_status.in_(_CERRADOS_OPERATIVOS))
    sla_abiertos_sin_act_24h = base.filter(filtro_abierto, Case.updated_at < umbral_24h).count()
    sla_prep_aut_mas_24h = base.filter(
        Case.current_status == C.ST_PED_PREP_AUT,
        Case.updated_at < umbral_24h,
    ).count()
    sla_compulsa_mas_24h = base.filter(
        Case.current_status.in_((C.ST_PED_EN_COMPULSA, C.ST_PED_PEND_COMPULSA)),
        Case.updated_at < umbral_24h,
    ).count()
    avg_epoch = base.filter(filtro_abierto).with_entities(
        func.avg(func.extract("epoch", func.now() - Case.created_at)),
    ).scalar()
    sla_edad_media_abiertos_horas: float | None
    if avg_epoch is None:
        sla_edad_media_abiertos_horas = None
    else:
        sla_edad_media_abiertos_horas = float(avg_epoch) / 3600.0
    sla_caso_mas_antiguo_abierto = base.filter(filtro_abierto).with_entities(
        func.min(Case.created_at),
    ).scalar()

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
        "sla_abiertos_sin_act_24h": sla_abiertos_sin_act_24h,
        "sla_prep_aut_mas_24h": sla_prep_aut_mas_24h,
        "sla_compulsa_mas_24h": sla_compulsa_mas_24h,
        "sla_edad_media_abiertos_horas": sla_edad_media_abiertos_horas,
        "sla_caso_mas_antiguo_abierto": sla_caso_mas_antiguo_abierto,
    }


@router.get("/dashboard")
def dashboard(
    request: Request,
    db: Session = Depends(get_web_db),
    filtro_pendientes: str | None = Query(default=None, alias="filter"),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)
    pendiente_filter = _normalize_pending_filter(filtro_pendientes)
    metricas = _build_metrics(db, usuario or {})
    pendientes_tabla = _build_pending_table(db, usuario or {}, filter_key=pendiente_filter)
    resumen_vendedores = _build_resumen_vendedores(db, usuario or {})

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "usuario": usuario,
            "metricas": metricas,
            "pendientes_tabla": pendientes_tabla,
            "pendiente_filter": pendiente_filter,
            "resumen_vendedores": resumen_vendedores,
        },
    )
