"""Cálculos financieros consolidados por contrato (P27)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.contract import CONTRACT_ACTIVE, Contract, ContractInstallment, RefinanceOperation
from app.models.erp_payment import ErpPayment
from app.models.erp_sale import ErpSale

_TWO = Decimal("0.01")


def _money(value: Decimal | float | int | None) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value)).quantize(_TWO, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class ContractFinancialSnapshot:
    contract_id: int
    customer_id: int
    total_sale: Decimal
    total_paid: Decimal
    saldo_final: Decimal
    saldo_sin_refin: Decimal
    refinanciado: Decimal
    atraso: Decimal
    recovery_pct: Decimal
    overdue_installments: int
    status: str


@dataclass(frozen=True)
class ErpDashboardKpis:
    active_contracts: int
    total_balance: Decimal
    total_refinanced: Decimal
    total_recovery_pct: Decimal
    overdue_amount: Decimal
    recent_payments_count: int
    top_vendedores: list[tuple[str, Decimal]]
    top_secciones: list[tuple[str, Decimal]]


class ContractFinancialService:
    def payments_total_for_sale(self, db: Session, sale_id: int) -> Decimal:
        total = db.scalar(
            select(func.coalesce(func.sum(ErpPayment.amount), 0)).where(ErpPayment.sale_id == sale_id)
        )
        return _money(total)

    def compute_snapshot(self, db: Session, contract: Contract) -> ContractFinancialSnapshot:
        total_sale = _money(contract.original_balance)
        if contract.sales_sale_id:
            sale = db.get(ErpSale, contract.sales_sale_id)
            if sale and sale.total_amount:
                total_sale = _money(sale.total_amount)

        paid_from_payments = Decimal("0")
        if contract.sales_sale_id:
            paid_from_payments = self.payments_total_for_sale(db, contract.sales_sale_id)

        paid_installments = _money(
            db.scalar(
                select(func.coalesce(func.sum(ContractInstallment.paid_amount), 0)).where(
                    ContractInstallment.contract_id == contract.id
                )
            )
        )
        total_paid = max(paid_from_payments, paid_installments, _money(contract.total_paid))

        refinanciado = _money(
            db.scalar(
                select(func.coalesce(func.sum(RefinanceOperation.refinanced_amount), 0)).where(
                    RefinanceOperation.contract_id == contract.id
                )
            )
        )
        if refinanciado == 0:
            refinanciado = _money(contract.refinanced_amount)

        saldo_sin_refin = total_sale - total_paid
        if saldo_sin_refin < 0:
            saldo_sin_refin = Decimal("0")
        saldo_final = saldo_sin_refin + refinanciado

        today = date.today()
        overdue_rows = db.scalars(
            select(ContractInstallment).where(
                ContractInstallment.contract_id == contract.id,
                ContractInstallment.due_date.isnot(None),
                ContractInstallment.due_date < today,
                ContractInstallment.status != "paid",
            )
        ).all()
        atraso = sum(
            (_money(r.amount) - _money(r.paid_amount) for r in overdue_rows),
            Decimal("0"),
        )
        recovery = Decimal("0")
        if total_sale > 0:
            recovery = (total_paid / total_sale * Decimal("100")).quantize(_TWO)

        return ContractFinancialSnapshot(
            contract_id=contract.id,
            customer_id=contract.customer_id,
            total_sale=total_sale,
            total_paid=total_paid,
            saldo_final=saldo_final,
            saldo_sin_refin=saldo_sin_refin,
            refinanciado=refinanciado,
            atraso=atraso,
            recovery_pct=recovery,
            overdue_installments=len(overdue_rows),
            status=contract.status,
        )

    def refresh_contract_balances(self, db: Session, contract_id: int) -> Contract:
        contract = db.get(Contract, contract_id)
        if not contract:
            raise ValueError(f"Contrato {contract_id} no encontrado.")
        snap = self.compute_snapshot(db, contract)
        contract.original_balance = snap.total_sale
        contract.current_balance = snap.saldo_final
        contract.total_paid = snap.total_paid
        contract.refinanced_amount = snap.refinanciado
        if snap.saldo_final <= 0 and contract.status == CONTRACT_ACTIVE:
            from datetime import datetime, timezone

            from app.services.case_event_service import CONTRACT_CLOSED, log_event

            contract.status = "closed"
            contract.closed_at = datetime.now(timezone.utc)
            if contract.case_id:
                log_event(
                    db,
                    case_id=contract.case_id,
                    event_type=CONTRACT_CLOSED,
                    message=f"Contrato {contract.id} cerrado (saldo cero)",
                    source="erp",
                    metadata={"contract_id": contract.id},
                )
        db.flush()
        return contract

    def build_dashboard_kpis(self, db: Session) -> ErpDashboardKpis:
        contracts = list(
            db.scalars(
                select(Contract)
                .options(joinedload(Contract.erp_sale))
                .where(Contract.status == CONTRACT_ACTIVE)
            )
            .unique()
            .all()
        )
        total_balance = Decimal("0")
        total_refin = Decimal("0")
        total_sale_sum = Decimal("0")
        total_paid_sum = Decimal("0")
        overdue = Decimal("0")
        vendedor_map: dict[str, Decimal] = {}
        seccion_map: dict[str, Decimal] = {}

        for c in contracts:
            snap = self.compute_snapshot(db, c)
            total_balance += snap.saldo_final
            total_refin += snap.refinanciado
            total_sale_sum += snap.total_sale
            total_paid_sum += snap.total_paid
            overdue += snap.atraso
            if c.erp_sale and c.erp_sale.vendedor:
                vendedor_map[c.erp_sale.vendedor] = vendedor_map.get(c.erp_sale.vendedor, Decimal("0")) + snap.total_sale
            if c.erp_sale and c.erp_sale.seccion:
                seccion_map[c.erp_sale.seccion] = seccion_map.get(c.erp_sale.seccion, Decimal("0")) + snap.total_sale

        recovery = Decimal("0")
        if total_sale_sum > 0:
            recovery = (total_paid_sum / total_sale_sum * Decimal("100")).quantize(_TWO)

        recent = db.scalar(
            select(func.count(ErpPayment.id)).where(
                ErpPayment.payment_date.isnot(None),
                ErpPayment.payment_date >= date.today().replace(day=1),
            )
        ) or 0

        top_v = sorted(vendedor_map.items(), key=lambda x: x[1], reverse=True)[:5]
        top_s = sorted(seccion_map.items(), key=lambda x: x[1], reverse=True)[:5]

        return ErpDashboardKpis(
            active_contracts=len(contracts),
            total_balance=_money(total_balance),
            total_refinanced=_money(total_refin),
            total_recovery_pct=recovery,
            overdue_amount=_money(overdue),
            recent_payments_count=int(recent),
            top_vendedores=top_v,
            top_secciones=top_s,
        )

    def register_payment(
        self,
        db: Session,
        contract_id: int,
        amount: Decimal,
        *,
        payment_date: date | None = None,
        reference: str | None = None,
        log_case_event: bool = True,
    ) -> ErpPayment:
        from app.services.case_event_service import PAYMENT_REGISTERED, log_event

        contract = db.get(Contract, contract_id)
        if not contract:
            raise ValueError("Contrato no encontrado.")
        payment = ErpPayment(
            sale_id=contract.sales_sale_id,
            amount=_money(amount),
            payment_date=payment_date or date.today(),
            reference=reference,
        )
        db.add(payment)
        db.flush()
        self.refresh_contract_balances(db, contract_id)
        if log_case_event and contract.case_id:
            log_event(
                db,
                case_id=contract.case_id,
                event_type=PAYMENT_REGISTERED,
                message=f"Pago registrado: ${_money(amount)}",
                source="web",
                metadata={"contract_id": contract_id, "payment_id": payment.id, "amount": str(amount)},
            )
        return payment

    def create_refinance(
        self,
        db: Session,
        contract_id: int,
        refinanced_amount: Decimal,
        *,
        notes: str | None = None,
    ) -> RefinanceOperation:
        from datetime import datetime, timezone

        from app.services.case_event_service import REFINANCE_CREATED, log_event

        contract = db.get(Contract, contract_id)
        if not contract:
            raise ValueError("Contrato no encontrado.")
        snap = self.compute_snapshot(db, contract)
        op = RefinanceOperation(
            contract_id=contract_id,
            previous_balance=snap.saldo_final,
            refinanced_amount=_money(refinanced_amount),
            new_balance=snap.saldo_final + _money(refinanced_amount),
            notes=notes,
        )
        db.add(op)
        contract.status = "refinanced"
        contract.refinanced_amount = _money(contract.refinanced_amount) + _money(refinanced_amount)
        contract.current_balance = op.new_balance
        contract.updated_at = datetime.now(timezone.utc)
        db.flush()
        if contract.case_id:
            log_event(
                db,
                case_id=contract.case_id,
                event_type=REFINANCE_CREATED,
                message=f"Refinanciamiento: ${_money(refinanced_amount)}",
                source="web",
                metadata={"contract_id": contract_id, "refinance_id": op.id},
            )
        return op
