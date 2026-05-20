"""Listado de pedidos con autorización SNTE generada/aprobada (vista web)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import exists, func, or_
from sqlalchemy.orm import Session

from app.domain import constants as C
from app.models.authorization_job import AuthorizationJob
from app.models.case import Case
from app.models.case_event import CaseEvent
from app.models.document import Document
from app.services.case_event_service import AUTH_GENERATED, AUTH_REGENERATED
from app.services.ocr_service import OCRService
from app.web.auth import web_should_scope_vendedor_cases

_AUTH_EVENT_TYPES = (AUTH_GENERATED, AUTH_REGENERATED)
_LIST_LIMIT = 300


def _order_type_label(order_type: str | None) -> str:
    if order_type == C.ORDER_TYPE_MUEBLE:
        return "Mueble"
    if order_type == C.ORDER_TYPE_PRESTAMO:
        return "Préstamo"
    return order_type or "—"


def _parse_date_param(raw: str | None) -> date | None:
    if not raw or not str(raw).strip():
        return None
    try:
        return date.fromisoformat(str(raw).strip()[:10])
    except ValueError:
        return None


def _eligible_cases_query(db: Session, usuario: dict | None):
    """Casos que cumplen al menos un criterio de autorización generada."""
    snte_exists = exists().where(
        Document.case_id == Case.id,
        Document.is_active.is_(True),
        Document.document_type == C.DOC_AUTORIZACION_SNTE,
    )
    auth_event_exists = exists().where(
        CaseEvent.case_id == Case.id,
        CaseEvent.event_type.in_(_AUTH_EVENT_TYPES),
    )
    q = db.query(Case).filter(
        Case.case_type == C.CASE_TYPE_PEDIDO,
        or_(
            Case.current_status == C.ST_PED_AUT_GENERADA,
            snte_exists,
            auth_event_exists,
        ),
    )
    if web_should_scope_vendedor_cases(usuario or {}):
        nombre = (usuario or {}).get("nombre")
        if nombre:
            q = q.filter(Case.seller_name == nombre)
    return q


def _auth_dates_by_case(db: Session, case_ids: list[int]) -> dict[int, datetime]:
    if not case_ids:
        return {}
    out: dict[int, datetime] = {}
    for case_id, dt in (
        db.query(CaseEvent.case_id, func.max(CaseEvent.created_at))
        .filter(
            CaseEvent.case_id.in_(case_ids),
            CaseEvent.event_type.in_(_AUTH_EVENT_TYPES),
        )
        .group_by(CaseEvent.case_id)
        .all()
    ):
        if dt:
            out[int(case_id)] = dt
    for case_id, dt in (
        db.query(AuthorizationJob.case_id, func.max(AuthorizationJob.created_at))
        .filter(
            AuthorizationJob.case_id.in_(case_ids),
            AuthorizationJob.generation_status == "success",
        )
        .group_by(AuthorizationJob.case_id)
        .all()
    ):
        if not dt:
            continue
        cid = int(case_id)
        prev = out.get(cid)
        if prev is None or dt > prev:
            out[cid] = dt
    return out


def _active_snte_docs_by_case(db: Session, case_ids: list[int]) -> dict[int, dict[str, Document]]:
    if not case_ids:
        return {}
    rows = (
        db.query(Document)
        .filter(
            Document.case_id.in_(case_ids),
            Document.is_active.is_(True),
            Document.document_type.in_(
                (C.DOC_AUTORIZACION_SNTE, C.DOC_ORDEN_SNTE_PDF)
            ),
        )
        .all()
    )
    by_case: dict[int, dict[str, Document]] = {}
    for doc in rows:
        bucket = by_case.setdefault(doc.case_id, {})
        bucket[doc.document_type] = doc
    return by_case


def _display_folio(case: Case) -> str:
    return case.official_folio or case.public_id


def _ocr_form_fields(db: Session, case_id: int) -> dict[str, Any]:
    prefill = OCRService.build_case_autorizacion_prefill(db, case_id)
    return prefill.get("form") or {}


def list_filter_options(db: Session, usuario: dict | None) -> dict[str, Any]:
    base = _eligible_cases_query(db, usuario)
    sellers = [
        r[0]
        for r in base.filter(
            Case.seller_name.isnot(None),
            Case.seller_name != "",
        )
        .with_entities(Case.seller_name)
        .distinct()
        .order_by(Case.seller_name)
        .all()
        if r[0]
    ]
    statuses = [
        r[0]
        for r in base.with_entities(Case.current_status)
        .distinct()
        .order_by(Case.current_status)
        .all()
        if r[0]
    ]
    return {
        "vendedores": sellers,
        "estados": statuses,
        "tipos_venta": [
            ("", "Todos"),
            (C.ORDER_TYPE_MUEBLE, "Mueble"),
            (C.ORDER_TYPE_PRESTAMO, "Préstamo"),
        ],
    }


def list_approved_authorizations(
    db: Session,
    usuario: dict | None,
    *,
    q: str | None = None,
    vendedor: str | None = None,
    qna: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    tipo_venta: str | None = None,
    estado: str | None = None,
) -> list[dict[str, Any]]:
    """Una fila por caso; fecha de autorización = más reciente entre evento y job."""
    query = _eligible_cases_query(db, usuario)

    if vendedor and vendedor.strip():
        query = query.filter(Case.seller_name == vendedor.strip())

    if tipo_venta and tipo_venta.strip() in (C.ORDER_TYPE_MUEBLE, C.ORDER_TYPE_PRESTAMO):
        query = query.filter(Case.order_type == tipo_venta.strip())

    if estado and estado.strip():
        query = query.filter(Case.current_status == estado.strip())

    search = (q or "").strip().lower()

    cases = query.order_by(Case.updated_at.desc()).limit(_LIST_LIMIT).all()
    if not cases:
        return []

    case_ids = [c.id for c in cases]
    auth_dates = _auth_dates_by_case(db, case_ids)
    docs_map = _active_snte_docs_by_case(db, case_ids)

    d_from = _parse_date_param(fecha_desde)
    d_to = _parse_date_param(fecha_hasta)
    qna_needle = (qna or "").strip().lower()

    rows: list[dict[str, Any]] = []
    for case in cases:
        ocr_form = _ocr_form_fields(db, case.id)
        rfc = str(ocr_form.get("rfc") or "").strip()
        seccion = str(ocr_form.get("categoria") or ocr_form.get("seccion") or "").strip()
        qna_val = str(ocr_form.get("qna_inicial") or "").strip()
        plazo = ocr_form.get("plazo_qnas")
        monto = ocr_form.get("monto_total")

        if qna_needle and qna_needle not in qna_val.lower():
            continue

        if search:
            haystack = " ".join(
                filter(
                    None,
                    [
                        case.client_name,
                        case.public_id,
                        case.official_folio,
                        case.temp_folio,
                        rfc,
                    ],
                )
            ).lower()
            if search not in haystack:
                continue

        auth_dt = auth_dates.get(case.id)
        if auth_dt and auth_dt.tzinfo is None:
            auth_dt = auth_dt.replace(tzinfo=timezone.utc)

        if d_from or d_to:
            if not auth_dt:
                continue
            auth_d = auth_dt.date()
            if d_from and auth_d < d_from:
                continue
            if d_to and auth_d > d_to:
                continue

        docs = docs_map.get(case.id, {})
        excel_doc = docs.get(C.DOC_AUTORIZACION_SNTE)
        pdf_doc = docs.get(C.DOC_ORDEN_SNTE_PDF)

        plazo_label = str(plazo) if plazo not in (None, "") else "—"
        try:
            monto_f = float(monto) if monto not in (None, "") else None
            monto_label = f"${monto_f:,.2f}" if monto_f is not None else "—"
        except (TypeError, ValueError):
            monto_label = str(monto) if monto else "—"

        rows.append(
            {
                "case_id": case.id,
                "folio": _display_folio(case),
                "public_id": case.public_id,
                "cliente": case.client_name,
                "rfc": rfc or "—",
                "vendedor": case.seller_name or "—",
                "seccion": seccion or "—",
                "qna": qna_val or "—",
                "tipo_venta": _order_type_label(case.order_type),
                "plazo": plazo_label,
                "monto": monto_label,
                "fecha_autorizacion": auth_dt,
                "fecha_autorizacion_label": (
                    auth_dt.strftime("%d/%m/%Y %H:%M") if auth_dt else "—"
                ),
                "estado": case.current_status,
                "tiene_excel": excel_doc is not None,
                "tiene_pdf": pdf_doc is not None,
                "excel_doc_id": excel_doc.id if excel_doc else None,
                "pdf_doc_id": pdf_doc.id if pdf_doc else None,
                "auth_sort": auth_dt or case.updated_at,
            }
        )

    rows.sort(key=lambda r: r["auth_sort"], reverse=True)
    return rows
