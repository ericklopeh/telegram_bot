"""Motor de reglas para alertas operativas (P16)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, not_, select
from sqlalchemy.orm import Session, joinedload

from app.config import Settings, get_settings
from app.domain import constants as C
from app.models.authorization_job import AuthorizationJob
from app.models.case import Case
from app.models.case_event import CaseEvent
from app.models.document import Document
from app.models.ocr_result import OcrResult
from app.models.operational_alert import OperationalAlert
from app.services.case_event_service import AUTH_REGENERATED
from app.services.case_service import CaseService
from app.services.ocr_service import OCR_ELIGIBLE_DOCUMENT_TYPES
from app.web.services.operational_tracking import (
    ACCION_LISTO_AUT,
    _CERRADOS,
    build_tracking_contexts,
    suggest_next_action,
)

log = logging.getLogger(__name__)

ALERT_STALE_CASE = "stale_case"
ALERT_READY_FOR_AUTH = "ready_for_auth"
ALERT_LOW_OCR = "low_ocr_confidence"
ALERT_SHAREPOINT_FAILED = "sharepoint_failed"
ALERT_MULTIPLE_REGEN = "multiple_regenerations"
ALERT_DAILY_SUMMARY = "daily_summary"

MSG_STALE = "⚠ Caso detenido más de 24h"
MSG_READY_AUTH = "✅ Caso listo para generar autorización"
MSG_LOW_OCR = "🔍 OCR requiere revisión"
MSG_SHAREPOINT = "❌ Error al subir documento"
MSG_MULTI_REGEN = "⚠ Revisar caso"

_MANAGED_TYPES = frozenset(
    {
        ALERT_STALE_CASE,
        ALERT_READY_FOR_AUTH,
        ALERT_LOW_OCR,
        ALERT_SHAREPOINT_FAILED,
        ALERT_MULTIPLE_REGEN,
        ALERT_DAILY_SUMMARY,
    }
)

_SCAN_LIMIT = 250
_OCR_CONFIDENCE_THRESHOLD = 0.70
_MIN_REGENERATIONS = 3


@dataclass
class AlertCandidate:
    alert_type: str
    message: str
    severity: str
    fingerprint: str
    case_id: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class NotificationRuleEngine:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._case_svc = CaseService(self.settings)

    def _base_cases(self, db: Session, seller_name: str | None) -> Any:
        q = db.query(Case)
        if seller_name:
            q = q.filter(Case.seller_name == seller_name)
        return q

    def _open_cases(self, db: Session, seller_name: str | None) -> list[Case]:
        return (
            self._base_cases(db, seller_name)
            .filter(not_(Case.current_status.in_(_CERRADOS)))
            .order_by(Case.updated_at.desc())
            .limit(_SCAN_LIMIT)
            .all()
        )

    def detect_stale_cases(self, db: Session, seller_name: str | None = None) -> list[AlertCandidate]:
        umbral = datetime.now(timezone.utc) - timedelta(hours=24)
        rows = (
            self._base_cases(db, seller_name)
            .filter(
                not_(Case.current_status.in_(_CERRADOS)),
                Case.updated_at < umbral,
            )
            .order_by(Case.updated_at.asc())
            .limit(_SCAN_LIMIT)
            .all()
        )
        out: list[AlertCandidate] = []
        for case in rows:
            out.append(
                AlertCandidate(
                    alert_type=ALERT_STALE_CASE,
                    message=MSG_STALE,
                    severity="warning",
                    fingerprint=f"{ALERT_STALE_CASE}:{case.id}",
                    case_id=case.id,
                    metadata={
                        "public_id": case.public_id,
                        "client_name": case.client_name,
                        "current_status": case.current_status,
                        "updated_at": case.updated_at.isoformat() if case.updated_at else None,
                    },
                )
            )
        return out

    def detect_ready_for_auth(self, db: Session, seller_name: str | None = None) -> list[AlertCandidate]:
        cases = (
            self._base_cases(db, seller_name)
            .filter(
                Case.case_type == C.CASE_TYPE_PEDIDO,
                Case.current_status == C.ST_PED_PREP_AUT,
                Case.order_type.isnot(None),
            )
            .limit(_SCAN_LIMIT)
            .all()
        )
        if not cases:
            return []
        ctx_map = build_tracking_contexts(db, cases, self._case_svc)
        out: list[AlertCandidate] = []
        for case in cases:
            ctx = ctx_map[case.id]
            if not ctx.checklist_ok or not ctx.has_ocr:
                continue
            if suggest_next_action(case, ctx) != ACCION_LISTO_AUT:
                continue
            out.append(
                AlertCandidate(
                    alert_type=ALERT_READY_FOR_AUTH,
                    message=MSG_READY_AUTH,
                    severity="success",
                    fingerprint=f"{ALERT_READY_FOR_AUTH}:{case.id}",
                    case_id=case.id,
                    metadata={
                        "public_id": case.public_id,
                        "checklist": ctx.checklist_short,
                        "has_ocr": True,
                    },
                )
            )
        return out

    def detect_low_ocr_confidence(self, db: Session, seller_name: str | None = None) -> list[AlertCandidate]:
        stmt = (
            select(
                Case.id,
                Case.public_id,
                Case.client_name,
                func.avg(OcrResult.confidence_score).label("avg_conf"),
                func.count(OcrResult.id).label("n_ocr"),
            )
            .join(Document, Document.case_id == Case.id)
            .join(OcrResult, OcrResult.document_id == Document.id)
            .where(
                Document.is_active.is_(True),
                Document.document_type.in_(tuple(OCR_ELIGIBLE_DOCUMENT_TYPES)),
                OcrResult.review_status == "processed",
                OcrResult.confidence_score.isnot(None),
                not_(Case.current_status.in_(_CERRADOS)),
            )
            .group_by(Case.id, Case.public_id, Case.client_name)
            .having(func.avg(OcrResult.confidence_score) < _OCR_CONFIDENCE_THRESHOLD)
        )
        if seller_name:
            stmt = stmt.where(Case.seller_name == seller_name)
        rows = db.execute(stmt.limit(_SCAN_LIMIT)).all()
        return [
            AlertCandidate(
                alert_type=ALERT_LOW_OCR,
                message=MSG_LOW_OCR,
                severity="warning",
                fingerprint=f"{ALERT_LOW_OCR}:{case_id}",
                case_id=case_id,
                metadata={
                    "public_id": public_id,
                    "avg_confidence": round(float(avg_conf or 0), 2),
                    "ocr_count": int(n_ocr or 0),
                },
            )
            for case_id, public_id, client_name, avg_conf, n_ocr in rows
        ]

    def detect_sharepoint_failures(self, db: Session, seller_name: str | None = None) -> list[AlertCandidate]:
        stmt = (
            select(Case.id, Case.public_id, Case.client_name, func.count(Document.id))
            .join(Document, Document.case_id == Case.id)
            .where(
                Document.is_active.is_(True),
                Document.upload_status == "UPLOAD_FAILED",
            )
            .group_by(Case.id, Case.public_id, Case.client_name)
        )
        if seller_name:
            stmt = stmt.where(Case.seller_name == seller_name)
        rows = db.execute(stmt.limit(_SCAN_LIMIT)).all()
        return [
            AlertCandidate(
                alert_type=ALERT_SHAREPOINT_FAILED,
                message=MSG_SHAREPOINT,
                severity="danger",
                fingerprint=f"{ALERT_SHAREPOINT_FAILED}:{case_id}",
                case_id=case_id,
                metadata={"public_id": public_id, "failed_docs": int(n)},
            )
            for case_id, public_id, client_name, n in rows
        ]

    def detect_multiple_regenerations(self, db: Session, seller_name: str | None = None) -> list[AlertCandidate]:
        stmt = (
            select(Case.id, Case.public_id, Case.client_name, func.count(CaseEvent.id))
            .join(CaseEvent, CaseEvent.case_id == Case.id)
            .where(CaseEvent.event_type == AUTH_REGENERATED)
            .group_by(Case.id, Case.public_id, Case.client_name)
            .having(func.count(CaseEvent.id) >= _MIN_REGENERATIONS)
        )
        if seller_name:
            stmt = stmt.where(Case.seller_name == seller_name)

        by_events = {r[0]: r for r in db.execute(stmt).all()}

        job_stmt = (
            select(Case.id, Case.public_id, Case.client_name, func.count(AuthorizationJob.id))
            .select_from(AuthorizationJob)
            .join(Case, Case.id == AuthorizationJob.case_id)
            .where(AuthorizationJob.generation_status == "success")
            .group_by(Case.id, Case.public_id, Case.client_name)
            .having(func.count(AuthorizationJob.id) >= _MIN_REGENERATIONS)
        )
        if seller_name:
            job_stmt = job_stmt.where(Case.seller_name == seller_name)
        by_jobs = {r[0]: r for r in db.execute(job_stmt).all()}

        case_ids = set(by_events) | set(by_jobs)
        out: list[AlertCandidate] = []
        for cid in case_ids:
            ev = by_events.get(cid)
            job_row = by_jobs.get(cid)
            if ev:
                _, public_id, client_name, n_ev = ev
            elif job_row:
                _, public_id, client_name, n_ev = job_row[0], job_row[1], job_row[2], 0
            else:
                continue
            n_jobs = int(job_row[3]) if job_row else 0
            out.append(
                AlertCandidate(
                    alert_type=ALERT_MULTIPLE_REGEN,
                    message=MSG_MULTI_REGEN,
                    severity="warning",
                    fingerprint=f"{ALERT_MULTIPLE_REGEN}:{cid}",
                    case_id=cid,
                    metadata={
                        "public_id": public_id,
                        "regeneration_events": int(n_ev),
                        "successful_jobs": int(n_jobs),
                    },
                )
            )
        return out[:_SCAN_LIMIT]

    def build_daily_summary(
        self, db: Session, seller_name: str | None = None
    ) -> dict[str, Any]:
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        base = self._base_cases(db, seller_name)

        nuevos = base.filter(Case.created_at >= today_start).count()
        listos = len(self.detect_ready_for_auth(db, seller_name))
        open_cases = self._open_cases(db, seller_name)
        ctx_map = build_tracking_contexts(db, open_cases, self._case_svc) if open_cases else {}
        pendientes_ocr = sum(
            1
            for c in open_cases
            if c.case_type == C.CASE_TYPE_PEDIDO
            and ctx_map.get(c.id)
            and ctx_map[c.id].needs_ocr
        )
        sp_fallidos = len(self.detect_sharepoint_failures(db, seller_name))
        sin_avance = len(self.detect_stale_cases(db, seller_name))

        lines = [
            f"Nuevos casos hoy: {nuevos}",
            f"Listos para autorización: {listos}",
            f"Pendientes OCR: {pendientes_ocr}",
            f"SharePoint fallidos: {sp_fallidos}",
            f"Sin avance >24h: {sin_avance}",
        ]
        return {
            "nuevos_casos": nuevos,
            "listos_autorizacion": listos,
            "pendientes_ocr": pendientes_ocr,
            "sharepoint_fallidos": sp_fallidos,
            "stale_24h": sin_avance,
            "message": "Resumen operativo del día\n" + "\n".join(lines),
            "lines": lines,
        }

    def collect_all_alerts(
        self, db: Session, seller_name: str | None = None
    ) -> list[AlertCandidate]:
        alerts: list[AlertCandidate] = []
        alerts.extend(self.detect_stale_cases(db, seller_name))
        alerts.extend(self.detect_ready_for_auth(db, seller_name))
        alerts.extend(self.detect_low_ocr_confidence(db, seller_name))
        alerts.extend(self.detect_sharepoint_failures(db, seller_name))
        alerts.extend(self.detect_multiple_regenerations(db, seller_name))
        summary = self.build_daily_summary(db, seller_name)
        scope = seller_name or "global"
        alerts.append(
            AlertCandidate(
                alert_type=ALERT_DAILY_SUMMARY,
                message=summary["message"],
                severity="info",
                fingerprint=f"{ALERT_DAILY_SUMMARY}:{scope}:{datetime.now(timezone.utc).date().isoformat()}",
                case_id=None,
                metadata=summary,
            )
        )
        return alerts

    def sync_alerts_to_db(
        self, db: Session, seller_name: str | None = None
    ) -> list[OperationalAlert]:
        """Calcula reglas, persiste/actualiza alertas activas y desactiva las obsoletas."""
        candidates = self.collect_all_alerts(db, seller_name)
        new_fps = {c.fingerprint for c in candidates}

        scope_filter = OperationalAlert.alert_type.in_(_MANAGED_TYPES)
        existing = db.query(OperationalAlert).filter(
            scope_filter,
            OperationalAlert.is_active.is_(True),
        )
        if seller_name:
            case_ids_subq = select(Case.id).where(Case.seller_name == seller_name)
            existing = existing.filter(
                (OperationalAlert.case_id.in_(case_ids_subq))
                | (OperationalAlert.case_id.is_(None))
            )
        for row in existing.all():
            if row.fingerprint not in new_fps:
                row.is_active = False

        persisted: list[OperationalAlert] = []
        for cand in candidates:
            row = db.scalar(
                select(OperationalAlert).where(OperationalAlert.fingerprint == cand.fingerprint)
            )
            if row:
                row.message = cand.message
                row.severity = cand.severity
                row.case_id = cand.case_id
                row.metadata_json = cand.metadata
                row.is_active = True
            else:
                row = OperationalAlert(
                    case_id=cand.case_id,
                    alert_type=cand.alert_type,
                    message=cand.message,
                    severity=cand.severity,
                    fingerprint=cand.fingerprint,
                    is_active=True,
                    metadata_json=cand.metadata,
                )
                db.add(row)
            persisted.append(row)
        try:
            db.commit()
        except Exception:
            db.rollback()
            log.exception("Error persistiendo alertas operativas")
            raise
        return persisted

    def get_active_alerts_for_dashboard(
        self,
        db: Session,
        seller_name: str | None = None,
        *,
        limit: int = 30,
    ) -> tuple[list[OperationalAlert], dict[str, Any]]:
        self.sync_alerts_to_db(db, seller_name)
        q = (
            db.query(OperationalAlert)
            .options(joinedload(OperationalAlert.case))
            .filter(
                OperationalAlert.is_active.is_(True),
                OperationalAlert.alert_type != ALERT_DAILY_SUMMARY,
            )
            .order_by(OperationalAlert.updated_at.desc())
        )
        if seller_name:
            case_ids = select(Case.id).where(Case.seller_name == seller_name)
            q = q.filter(OperationalAlert.case_id.in_(case_ids))
        alerts = q.limit(limit).all()
        summary_row = db.scalar(
            select(OperationalAlert)
            .where(
                OperationalAlert.is_active.is_(True),
                OperationalAlert.alert_type == ALERT_DAILY_SUMMARY,
            )
            .order_by(OperationalAlert.updated_at.desc())
            .limit(1)
        )
        summary = (summary_row.metadata_json if summary_row else None) or self.build_daily_summary(
            db, seller_name
        )
        return alerts, summary
