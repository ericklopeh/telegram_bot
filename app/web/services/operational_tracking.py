"""Seguimiento operativo por caso para el dashboard (P14)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain import constants as C
from app.models.case import Case
from app.models.document import Document
from app.models.ocr_result import OcrResult
from app.services.case_service import CaseService
from app.services.ocr_service import OCR_ELIGIBLE_DOCUMENT_TYPES

# Acciones sugeridas (etiquetas visibles)
ACCION_FALTA_PEDIDO = "falta pedido"
ACCION_FALTA_ORDEN = "falta orden descuento"
ACCION_FALTA_CARATULA = "falta caratula"
ACCION_PENDIENTE_OCR = "pendiente OCR"
ACCION_LISTO_AUT = "listo para autorización"
ACCION_AUT_GENERADA = "autorización generada"
ACCION_PENDIENTE_COMPULSA = "pendiente compulsa"
ACCION_ERROR_SP = "error SharePoint"
ACCION_CERRADO = "cerrado"
ACCION_SEGUIMIENTO = "seguimiento"

_CERRADOS = (
    C.ST_PED_CERRADO,
    C.ST_PED_RECHAZADO,
    C.ST_PED_COMPRA,
    C.ST_REV_CERRADO,
    C.ST_REV_RECHAZADO,
    C.ST_REV_SIN_LIQUIDEZ,
)

_BADGE_BY_ACTION: dict[str, str] = {
    ACCION_CERRADO: "bg-secondary",
    ACCION_ERROR_SP: "bg-danger",
    ACCION_FALTA_PEDIDO: "bg-warning text-dark",
    ACCION_FALTA_ORDEN: "bg-warning text-dark",
    ACCION_FALTA_CARATULA: "bg-warning text-dark",
    ACCION_PENDIENTE_OCR: "bg-info text-dark",
    ACCION_LISTO_AUT: "bg-success",
    ACCION_AUT_GENERADA: "bg-success",
    ACCION_PENDIENTE_COMPULSA: "bg-primary",
    ACCION_SEGUIMIENTO: "bg-light text-dark border",
}


@dataclass
class CaseTrackingContext:
    present: set[str] = field(default_factory=set)
    checklist_ok: bool = False
    checklist_short: str = "—"
    has_ocr: bool = False
    needs_ocr: bool = False
    has_snte_auth: bool = False
    sharepoint_estado: str = "—"
    sp_failed: bool = False
    sp_pending: bool = False


def _order_type_label(order_type: str | None) -> str:
    if order_type == C.ORDER_TYPE_MUEBLE:
        return "Mueble"
    if order_type == C.ORDER_TYPE_PRESTAMO:
        return "Préstamo"
    return order_type or "—"


def _format_age(created_at: datetime | None, now: datetime) -> tuple[str, float | None]:
    if created_at is None:
        return "—", None
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    delta = now - created_at
    hours = delta.total_seconds() / 3600.0
    if hours < 24:
        label = f"{int(hours)} h"
    else:
        days = int(hours // 24)
        rem = int(hours % 24)
        label = f"{days} d {rem} h" if rem else f"{days} d"
    return label, hours


def _sharepoint_aggregate(statuses: list[str]) -> tuple[str, bool, bool]:
    if not statuses:
        return "—", False, False
    failed = any(s == "UPLOAD_FAILED" for s in statuses)
    pending = any(s in ("PENDING_UPLOAD", "LOCAL") for s in statuses)
    if failed:
        return "fallido", True, pending
    if pending:
        return "pendiente", False, True
    if all(s == "UPLOADED" for s in statuses):
        return "sincronizado", False, False
    return "pendiente", False, True


def _checklist_short(order_type: str | None, present: set[str]) -> str:
    if not order_type:
        return "—"
    required = C.required_doc_types_for_order(order_type)
    present_n = {C.normalize_doc_type(dt) for dt in present}
    ok = sum(1 for dt in required if dt in present_n)
    return f"{ok}/{len(required)}"


def suggest_next_action(case: Case, ctx: CaseTrackingContext) -> str:
    if case.current_status in _CERRADOS:
        return ACCION_CERRADO
    if ctx.sp_failed:
        return ACCION_ERROR_SP
    if case.case_type == C.CASE_TYPE_PEDIDO and case.order_type:
        present = {C.normalize_doc_type(dt) for dt in ctx.present}
        if C.DOC_PEDIDO not in present:
            return ACCION_FALTA_PEDIDO
        if C.DOC_ORDEN_DESCUENTO not in present:
            return ACCION_FALTA_ORDEN
        required = set(C.required_doc_types_for_order(case.order_type))
        if C.DOC_CARATULA_BANCARIA in required and C.DOC_CARATULA_BANCARIA not in present:
            return ACCION_FALTA_CARATULA
    if case.current_status in (C.ST_PED_EN_COMPULSA, C.ST_PED_PEND_COMPULSA):
        return ACCION_PENDIENTE_COMPULSA
    if case.current_status == C.ST_PED_AUT_GENERADA or ctx.has_snte_auth:
        return ACCION_AUT_GENERADA
    if case.current_status == C.ST_PED_PREP_AUT and ctx.checklist_ok:
        return ACCION_LISTO_AUT
    if ctx.needs_ocr and case.case_type == C.CASE_TYPE_PEDIDO:
        return ACCION_PENDIENTE_OCR
    return ACCION_SEGUIMIENTO


def badge_class_for_action(action: str) -> str:
    return _BADGE_BY_ACTION.get(action, "bg-secondary")


def build_tracking_contexts(
    db: Session,
    cases: list[Case],
    case_svc: CaseService,
) -> dict[int, CaseTrackingContext]:
    if not cases:
        return {}
    ids = [c.id for c in cases]
    ctx_map: dict[int, CaseTrackingContext] = {cid: CaseTrackingContext() for cid in ids}

    doc_rows = db.execute(
        select(
            Document.case_id,
            Document.id,
            Document.document_type,
            Document.upload_status,
        ).where(
            Document.case_id.in_(ids),
            Document.is_active.is_(True),
        )
    ).all()

    eligible_doc_ids: dict[int, set[int]] = {cid: set() for cid in ids}
    upload_statuses: dict[int, list[str]] = {cid: [] for cid in ids}
    present_types: dict[int, set[str]] = {cid: set() for cid in ids}
    has_snte: set[int] = set()

    for case_id, doc_id, doc_type, upload_status in doc_rows:
        present_types[case_id].add(doc_type)
        upload_statuses[case_id].append(upload_status or "")
        if doc_type == C.DOC_AUTORIZACION_SNTE:
            has_snte.add(case_id)
        norm = C.normalize_doc_type(doc_type)
        if norm in OCR_ELIGIBLE_DOCUMENT_TYPES or doc_type == "talon":
            eligible_doc_ids[case_id].add(doc_id)

    ocr_doc_ids: set[int] = set()
    if any(eligible_doc_ids.values()):
        all_eligible = {did for s in eligible_doc_ids.values() for did in s}
        if all_eligible:
            ocr_doc_ids = set(
                db.execute(
                    select(OcrResult.document_id).where(
                        OcrResult.document_id.in_(all_eligible),
                        OcrResult.review_status == "processed",
                    )
                )
                .scalars()
                .all()
            )

    for case in cases:
        cid = case.id
        ctx = ctx_map[cid]
        ctx.present = present_types.get(cid, set())
        ctx.has_snte_auth = cid in has_snte
        if case.case_type == C.CASE_TYPE_PEDIDO and case.order_type:
            ctx.checklist_ok = case_svc.pedido_has_all_documents(db, case)
            ctx.checklist_short = _checklist_short(case.order_type, ctx.present)
        sp_est, failed, pending = _sharepoint_aggregate(upload_statuses.get(cid, []))
        ctx.sharepoint_estado = sp_est
        ctx.sp_failed = failed
        ctx.sp_pending = pending
        elig = eligible_doc_ids.get(cid, set())
        if elig:
            with_ocr = [d for d in elig if d in ocr_doc_ids]
            ctx.has_ocr = len(with_ocr) > 0
            ctx.needs_ocr = any(d not in ocr_doc_ids for d in elig)
        else:
            ctx.has_ocr = False
            ctx.needs_ocr = False

    return ctx_map


def build_operational_row(
    case: Case,
    ctx: CaseTrackingContext,
    *,
    problema: str = "",
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    action = suggest_next_action(case, ctx)
    age_label, age_hours = _format_age(case.created_at, now)
    updated = case.updated_at
    sin_24h = False
    if updated is not None:
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        sin_24h = (now - updated) > timedelta(hours=24) and case.current_status not in _CERRADOS

    aut_gen = ctx.has_snte_auth or case.current_status == C.ST_PED_AUT_GENERADA

    return {
        "case": case,
        "needs_ocr": ctx.needs_ocr,
        "problema": problema,
        "tipo_pedido": _order_type_label(case.order_type) if case.case_type == C.CASE_TYPE_PEDIDO else case.case_type,
        "checklist_resumen": ctx.checklist_short,
        "checklist_ok": ctx.checklist_ok,
        "ocr_disponible": ctx.has_ocr,
        "autorizacion_generada": aut_gen,
        "sharepoint_estado": ctx.sharepoint_estado,
        "antiguedad_label": age_label,
        "antiguedad_horas": age_hours,
        "sin_avance_24h": sin_24h,
        "siguiente_accion": action,
        "accion_badge": badge_class_for_action(action),
    }


def row_matches_filter(row: dict[str, Any], filter_key: str, umbral_24h: datetime) -> bool:
    fk = filter_key
    action = row["siguiente_accion"]
    case: Case = row["case"]

    if fk == "ready_for_auth":
        return action == ACCION_LISTO_AUT
    if fk == "missing_docs":
        return action in (ACCION_FALTA_PEDIDO, ACCION_FALTA_ORDEN, ACCION_FALTA_CARATULA)
    if fk == "with_ocr":
        return row["ocr_disponible"]
    if fk == "without_ocr":
        return row.get("needs_ocr") or action == ACCION_PENDIENTE_OCR
    if fk == "stale_24h":
        updated = case.updated_at
        if updated is None or case.current_status in _CERRADOS:
            return False
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        return updated < umbral_24h
    return True
