"""P58 — IA operacional sin OCR (heurísticas + resúmenes)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.case import Case
from app.models.ops_incident import OpsIncident
from app.models.sale_capture import SaleCapture


class AiOpsService:
    """Insights basados en reglas; integrable con LLM externo después."""

    def case_summary(self, db: Session, case: Case) -> str:
        age_h = 0
        if case.updated_at:
            age_h = int((datetime.now(timezone.utc) - case.updated_at).total_seconds() / 3600)
        return (
            f"Caso {case.public_id} ({case.client_name}): estado {case.current_status}, "
            f"vendedor {case.seller_name or 'N/A'}, sin movimiento ~{age_h}h."
        )

    def classify_incident(self, message: str) -> dict[str, str]:
        msg = (message or "").lower()
        if "sharepoint" in msg or "graph" in msg:
            return {"category": "integration", "severity": "high"}
        if "sla" in msg or "24h" in msg:
            return {"category": "sla", "severity": "medium"}
        if "import" in msg or "excel" in msg:
            return {"category": "data", "severity": "medium"}
        return {"category": "general", "severity": "low"}

    def recovery_suggestions(self, db: Session) -> list[str]:
        tips = []
        stale = db.scalar(
            select(func.count(Case.id)).where(
                Case.updated_at < datetime.now(timezone.utc) - timedelta(hours=24)
            )
        ) or 0
        if stale:
            tips.append(f"Revisar {stale} casos sin avance >24h (recovery masivo en /ops).")
        failed_sales = db.scalar(
            select(func.count(SaleCapture.id)).where(
                SaleCapture.registration_status == "registration_failed"
            )
        ) or 0
        if failed_sales:
            tips.append(f"Reintentar {failed_sales} ventas con registro fallido.")
        if not tips:
            tips.append("Operación estable; sin acciones recovery urgentes.")
        return tips

    def detect_anomalies(self, db: Session) -> list[dict[str, Any]]:
        anomalies = []
        by_vendor = db.execute(
            select(SaleCapture.vendedor, func.count(SaleCapture.id))
            .group_by(SaleCapture.vendedor)
        ).all()
        if by_vendor:
            counts = [c for _, c in by_vendor if c]
            if counts:
                avg = sum(counts) / len(counts)
                for vendor, cnt in by_vendor:
                    if vendor and cnt > avg * 3:
                        anomalies.append(
                            {
                                "type": "sales_spike",
                                "label": vendor,
                                "detail": f"Volumen {cnt} vs media {avg:.0f}",
                            }
                        )
        open_incidents = db.scalar(
            select(func.count(OpsIncident.id)).where(OpsIncident.status == "OPEN")
        ) or 0
        if open_incidents > 5:
            anomalies.append(
                {
                    "type": "incidents_high",
                    "label": "ops",
                    "detail": f"{open_incidents} incidencias abiertas",
                }
            )
        return anomalies

    def bi_insights(self, db: Session) -> list[str]:
        anomalies = self.detect_anomalies(db)
        return [f"{a['type']}: {a['detail']}" for a in anomalies[:5]]

    def explain_blockage(self, db: Session, case: Case) -> str:
        wf = case.workflow_state or case.current_status
        if "SHAREPOINT" in (case.current_status or "").upper():
            return "Bloqueo probable: sincronización SharePoint pendiente o fallida. Revise documentos y panel Graph."
        if "PEND" in (case.current_status or "").upper():
            return f"El caso aguarda acción en etapa {wf}. Verifique dependencias y documentos obligatorios."
        return f"Sin bloqueo crítico detectado; estado actual {wf}."

    def copilot_briefing(self, db: Session, *, company_id: int = 1) -> dict[str, Any]:
        """Briefing operativo para /ai/copilot (sin LLM externo)."""
        stale = db.scalar(
            select(func.count(Case.id)).where(
                Case.updated_at < datetime.now(timezone.utc) - timedelta(hours=24)
            )
        ) or 0
        return {
            "summary": (
                f"Operación con {stale} casos sin avance >24h. "
                f"{len(self.detect_anomalies(db))} anomalías detectadas."
            ),
            "recovery": self.recovery_suggestions(db),
            "anomalies": self.detect_anomalies(db),
            "insights": self.bi_insights(db),
            "priorities": [
                {"level": "high", "text": "Casos SLA vencidos", "href": "/supervisor/cockpit"},
                {"level": "medium", "text": "Jobs fallidos", "href": "/jobs"},
                {"level": "low", "text": "Analytics", "href": "/analytics/avanzado"},
            ],
            "llm_ready": True,
            "note": "Integración LLM externa: configurar endpoint en futuro release.",
        }
