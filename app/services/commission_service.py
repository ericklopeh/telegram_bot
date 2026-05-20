"""Orquestación de comisiones por venta registrada (P21)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy.orm import Session

from app.models.commission import (
    PAYMENT_STATUS_CANCELLED,
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_PENDING,
    Commission,
)
from app.models.sale_capture import REG_STATUS_REGISTERED, SaleCapture, is_registration_complete
from app.repositories.commission_repository import CommissionRepository
from app.services.case_event_service import (
    COMMISSION_CANCELLED,
    COMMISSION_CREATED,
    COMMISSION_PAID,
    COMMISSION_UPDATED,
    log_event,
)
from app.services.commission_rules import CommissionRuleContext, resolve_commission_percentage

log = logging.getLogger(__name__)

_TWOPLACES = Decimal("0.01")


class CommissionServiceError(Exception):
    pass


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(_TWOPLACES, rounding=ROUND_HALF_UP)


def _sale_amount_from_capture(sale: SaleCapture) -> Decimal:
    raw = sale.total_venta or sale.venta
    if raw is None:
        raise CommissionServiceError(
            f"Venta {sale.folio} sin monto (total_venta/venta) para calcular comisión."
        )
    return _quantize_money(Decimal(str(raw)))


def calculate_commission(
    sale: SaleCapture,
    *,
    sale_amount: Decimal | None = None,
) -> tuple[Decimal, Decimal, Decimal]:
    """Retorna (porcentaje, monto comisión, monto venta)."""
    amount = sale_amount if sale_amount is not None else _sale_amount_from_capture(sale)
    ctx = CommissionRuleContext(
        seller_name=sale.vendedor,
        seccion=sale.seccion,
        tipo_venta=sale.tipo_venta,
        producto=sale.producto,
        qna=sale.qna,
    )
    pct = resolve_commission_percentage(ctx)
    commission_amt = _quantize_money(amount * pct / Decimal("100"))
    return pct, commission_amt, amount


def _log_commission_event(
    db: Session,
    sale: SaleCapture,
    event_type: str,
    message: str,
    user: dict[str, Any] | None,
    *,
    metadata: dict | None = None,
) -> None:
    if not sale.case_id:
        return
    log_event(
        db,
        case_id=sale.case_id,
        event_type=event_type,
        message=message,
        actor_user_id=(user or {}).get("id"),
        actor_role=(user or {}).get("rol"),
        source="web",
        metadata=metadata,
    )


class CommissionService:
    def generate_commission(
        self,
        db: Session,
        sale: SaleCapture,
        user: dict[str, Any] | None = None,
        *,
        force_update_pending: bool = True,
    ) -> Commission:
        """
        Crea o actualiza comisión para una venta registrada.
        No duplica: si existe pagada/cancelada, bloquea actualización.
        """
        if not is_registration_complete(sale) and sale.registration_status != REG_STATUS_REGISTERED:
            raise CommissionServiceError("La venta no está registrada; no se genera comisión.")

        pct, commission_amt, sale_amount = calculate_commission(sale)
        existing = CommissionRepository.get_by_sale_capture_id(db, sale.id)

        if existing:
            if existing.payment_status == PAYMENT_STATUS_PAID:
                raise CommissionServiceError(
                    "La comisión ya está pagada; no se puede regenerar."
                )
            if existing.payment_status == PAYMENT_STATUS_CANCELLED:
                raise CommissionServiceError(
                    "La comisión está cancelada; no se puede regenerar automáticamente."
                )
            if force_update_pending and existing.payment_status == PAYMENT_STATUS_PENDING:
                existing.seller_name = sale.vendedor
                existing.vendor_code = sale.codigo
                existing.qna = sale.qna
                existing.week = sale.semana
                existing.sale_amount = sale_amount
                existing.commission_percentage = pct
                existing.commission_amount = commission_amt
                CommissionRepository.save(db, existing)
                _log_commission_event(
                    db,
                    sale,
                    COMMISSION_UPDATED,
                    f"Comisión actualizada: {commission_amt} ({pct}%)",
                    user,
                    metadata={
                        "commission_id": existing.id,
                        "percentage": str(pct),
                        "amount": str(commission_amt),
                    },
                )
                return existing
            return existing

        commission = Commission(
            sale_capture_id=sale.id,
            seller_name=sale.vendedor,
            vendor_code=sale.codigo,
            qna=sale.qna,
            week=sale.semana,
            sale_amount=sale_amount,
            commission_percentage=pct,
            commission_amount=commission_amt,
            payment_status=PAYMENT_STATUS_PENDING,
        )
        CommissionRepository.create(db, commission)
        _log_commission_event(
            db,
            sale,
            COMMISSION_CREATED,
            f"Comisión generada: {commission_amt} ({pct}%) — vendedor {sale.vendedor}",
            user,
            metadata={
                "commission_id": commission.id,
                "folio": sale.folio,
                "percentage": str(pct),
                "amount": str(commission_amt),
            },
        )
        return commission

    def ensure_commission_for_registered_sale(
        self,
        db: Session,
        sale: SaleCapture,
        user: dict[str, Any] | None = None,
    ) -> Commission | None:
        """Hook post-registro P20: genera comisión sin romper el flujo principal."""
        try:
            return self.generate_commission(db, sale, user)
        except CommissionServiceError as exc:
            log.warning("Comisión no generada para venta %s: %s", sale.id, exc)
            return None
        except Exception:
            log.exception("Error inesperado generando comisión para venta %s", sale.id)
            return None

    def mark_paid(
        self,
        db: Session,
        commission_id: int,
        user: dict[str, Any] | None = None,
        *,
        notes: str | None = None,
    ) -> Commission:
        commission = CommissionRepository.get_by_id(db, commission_id)
        if not commission:
            raise CommissionServiceError("Comisión no encontrada.")
        if commission.payment_status == PAYMENT_STATUS_CANCELLED:
            raise CommissionServiceError("No se puede marcar pagada una comisión cancelada.")
        if commission.payment_status == PAYMENT_STATUS_PAID:
            return commission

        commission.payment_status = PAYMENT_STATUS_PAID
        commission.paid_at = datetime.now(timezone.utc)
        if notes:
            commission.notes = notes
        CommissionRepository.save(db, commission)

        sale = commission.sale_capture
        if sale:
            _log_commission_event(
                db,
                sale,
                COMMISSION_PAID,
                f"Comisión pagada: {commission.commission_amount} — folio {sale.folio}",
                user,
                metadata={"commission_id": commission.id},
            )
        return commission

    def cancel(
        self,
        db: Session,
        commission_id: int,
        user: dict[str, Any] | None = None,
        *,
        notes: str | None = None,
    ) -> Commission:
        commission = CommissionRepository.get_by_id(db, commission_id)
        if not commission:
            raise CommissionServiceError("Comisión no encontrada.")
        if commission.payment_status == PAYMENT_STATUS_PAID:
            raise CommissionServiceError("No se puede cancelar una comisión ya pagada.")

        commission.payment_status = PAYMENT_STATUS_CANCELLED
        commission.paid_at = None
        if notes:
            commission.notes = notes
        CommissionRepository.save(db, commission)

        sale = commission.sale_capture
        if sale:
            _log_commission_event(
                db,
                sale,
                COMMISSION_CANCELLED,
                f"Comisión cancelada — folio {sale.folio}",
                user,
                metadata={"commission_id": commission.id},
            )
        return commission

    def build_dashboard_payload(self, db: Session) -> dict[str, Any]:
        summary = CommissionRepository.summary_by_status(db)
        pending = summary.get(PAYMENT_STATUS_PENDING, {"count": 0, "total": Decimal("0")})
        paid = summary.get(PAYMENT_STATUS_PAID, {"count": 0, "total": Decimal("0")})
        cancelled = summary.get(
            PAYMENT_STATUS_CANCELLED, {"count": 0, "total": Decimal("0")}
        )
        total_amount = (
            Decimal(str(pending.get("total", 0)))
            + Decimal(str(paid.get("total", 0)))
            + Decimal(str(cancelled.get("total", 0)))
        )
        by_seller = CommissionRepository.aggregate_by_seller(db)
        by_week = CommissionRepository.aggregate_by_week(db)
        by_qna = CommissionRepository.aggregate_by_qna(db)
        supervisor = CommissionRepository.supervisor_metrics(db)
        return {
            "total_amount": total_amount,
            "pending_count": int(pending.get("count", 0)),
            "pending_amount": Decimal(str(pending.get("total", 0))),
            "paid_count": int(paid.get("count", 0)),
            "paid_amount": Decimal(str(paid.get("total", 0))),
            "cancelled_count": int(cancelled.get("count", 0)),
            "cancelled_amount": Decimal(str(cancelled.get("total", 0))),
            "chart_seller_labels": [s[0] for s in by_seller],
            "chart_seller_values": [float(s[1]) for s in by_seller],
            "chart_week_labels": [w[0] for w in by_week],
            "chart_week_values": [float(w[1]) for w in by_week],
            "chart_qna_labels": [q[0] for q in by_qna],
            "chart_qna_values": [float(q[1]) for q in by_qna],
            "supervisor": supervisor,
        }
