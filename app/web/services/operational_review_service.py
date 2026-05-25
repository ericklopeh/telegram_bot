"""Revisión operativa consolidada (P31)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, not_, select
from sqlalchemy.orm import Session, joinedload

from app.domain import constants as C
from app.models.case import Case
from app.models.commission import Commission, PAYMENT_STATUS_PENDING
from app.models.document import Document
from app.models.sale_capture import REG_STATUS_REGISTRATION_FAILED, REG_STATUS_REGISTERED, SaleCapture
from app.services.bi_dashboard_service import BiDashboardService
from app.services.bi_filters import BiFilters
from app.services.erp_reconciliation_service import ErpReconciliationService

_CERRADOS = (
    C.ST_PED_CERRADO,
    C.ST_PED_RECHAZADO,
    C.ST_PED_COMPRA,
    C.ST_REV_CERRADO,
    C.ST_REV_RECHAZADO,
    C.ST_REV_SIN_LIQUIDEZ,
)


@dataclass(frozen=True)
class ReviewItem:
    title: str
    detail: str
    severity: str
    url: str
    entity_id: int | None = None


@dataclass
class OperationalReviewReport:
    generated_at: datetime
    sections: dict[str, list[ReviewItem]]
    totals: dict[str, int]

    @property
    def critical_count(self) -> int:
        return sum(
            1
            for items in self.sections.values()
            for i in items
            if i.severity == "error"
        )


class OperationalReviewService:
    def build_report(self, db: Session) -> OperationalReviewReport:
        now = datetime.now(timezone.utc)
        umbral = now - timedelta(hours=24)
        sections: dict[str, list[ReviewItem]] = {
            "casos_atorados": [],
            "documentos_pendientes": [],
            "sharepoint_fallidos": [],
            "ventas_pendientes": [],
            "comisiones_pendientes": [],
            "export_excel_fallido": [],
            "conciliacion_critica": [],
        }

        stale_cases = db.scalars(
            select(Case)
            .where(
                not_(Case.current_status.in_(_CERRADOS)),
                Case.updated_at < umbral,
            )
            .order_by(Case.updated_at.asc())
            .limit(40)
        ).all()
        for c in stale_cases:
            sections["casos_atorados"].append(
                ReviewItem(
                    title=c.public_id,
                    detail=f"{c.client_name} · sin movimiento >24h · {c.current_status}",
                    severity="warning",
                    url=f"/casos/{c.id}",
                    entity_id=c.id,
                )
            )

        docs_pending = db.scalars(
            select(Document)
            .options(joinedload(Document.case))
            .where(
                Document.is_active.is_(True),
                Document.review_status == "PENDING_REVIEW",
            )
            .limit(40)
        ).all()
        for d in docs_pending:
            sections["documentos_pendientes"].append(
                ReviewItem(
                    title=f"Doc #{d.id}",
                    detail=f"Caso {d.case_id} · {d.document_type} · revisión pendiente",
                    severity="warning",
                    url=f"/casos/{d.case_id}/documentos",
                    entity_id=d.id,
                )
            )

        sp_failed = db.scalars(
            select(Document)
            .where(Document.is_active.is_(True), Document.upload_status == "UPLOAD_FAILED")
            .order_by(Document.uploaded_at.desc())
            .limit(40)
        ).all()
        for d in sp_failed:
            err = (d.upload_error or "Error de subida")[:120]
            sections["sharepoint_fallidos"].append(
                ReviewItem(
                    title=f"Doc #{d.id}",
                    detail=f"Caso {d.case_id} · {err}",
                    severity="error",
                    url=f"/casos/{d.case_id}/documentos",
                    entity_id=d.id,
                )
            )

        ventas_pend = db.scalars(
            select(SaleCapture)
            .where(
                SaleCapture.registration_status.notin_(
                    (REG_STATUS_REGISTERED, "cancelled", "draft")
                )
            )
            .order_by(SaleCapture.updated_at.desc())
            .limit(40)
        ).all()
        for s in ventas_pend:
            sections["ventas_pendientes"].append(
                ReviewItem(
                    title=s.folio,
                    detail=f"{s.cliente} · {s.registration_status} · {s.vendedor}",
                    severity="info",
                    url="/ventas/pendientes",
                    entity_id=s.id,
                )
            )

        sin_comision = db.execute(
            select(SaleCapture.id, SaleCapture.folio, SaleCapture.cliente)
            .outerjoin(Commission, Commission.sale_capture_id == SaleCapture.id)
            .where(
                SaleCapture.registration_status == REG_STATUS_REGISTERED,
                Commission.id.is_(None),
            )
            .limit(30)
        ).all()
        for sid, folio, cliente in sin_comision:
            sections["comisiones_pendientes"].append(
                ReviewItem(
                    title=folio,
                    detail=f"{cliente} · venta sin comisión",
                    severity="warning",
                    url="/comisiones",
                    entity_id=sid,
                )
            )

        comm_pending = db.scalars(
            select(Commission)
            .where(Commission.payment_status == PAYMENT_STATUS_PENDING)
            .order_by(Commission.created_at.desc())
            .limit(25)
        ).all()
        for c in comm_pending:
            sections["comisiones_pendientes"].append(
                ReviewItem(
                    title=c.seller_name,
                    detail=f"Pago pendiente · ${c.commission_amount}",
                    severity="info",
                    url="/comisiones",
                    entity_id=c.id,
                )
            )

        excel_failed = db.scalars(
            select(SaleCapture)
            .where(SaleCapture.registration_status == REG_STATUS_REGISTRATION_FAILED)
            .limit(30)
        ).all()
        for s in excel_failed:
            sections["export_excel_fallido"].append(
                ReviewItem(
                    title=s.folio,
                    detail=(s.registration_error or s.export_error or "Registro Excel fallido")[:150],
                    severity="error",
                    url="/ventas/pendientes",
                    entity_id=s.id,
                )
            )

        recon = ErpReconciliationService().build_report(db)
        for issue in recon.issues:
            if issue.severity in ("error", "warning"):
                sections["conciliacion_critica"].append(
                    ReviewItem(
                        title=issue.code,
                        detail=issue.message,
                        severity=issue.severity,
                        url="/erp/conciliacion",
                        entity_id=issue.entity_id,
                    )
                )

        bi_alerts = BiDashboardService().build_operational_alerts(db, BiFilters())
        for a in bi_alerts:
            if a.code not in {i.title for i in sections["conciliacion_critica"]}:
                sections["conciliacion_critica"].append(
                    ReviewItem(
                        title=a.title,
                        detail=a.message,
                        severity=a.severity,
                        url=a.drill_url,
                    )
                )

        totals = {k: len(v) for k, v in sections.items()}
        return OperationalReviewReport(
            generated_at=now,
            sections=sections,
            totals=totals,
        )
