"""Conciliación avanzada ERP (P27)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.contract import Contract
from app.models.erp_payment import ErpPayment
from app.models.erp_sale import ErpSale
from app.services.contract_financial_service import ContractFinancialService


@dataclass(frozen=True)
class ReconciliationIssue:
    code: str
    severity: str
    message: str
    entity_type: str
    entity_id: int | None = None


@dataclass(frozen=True)
class ErpReconciliationReport:
    issues: list[ReconciliationIssue]
    contracts_checked: int
    payments_checked: int

    @property
    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)


class ErpReconciliationService:
    def __init__(self) -> None:
        self.financial = ContractFinancialService()

    def build_report(self, db: Session) -> ErpReconciliationReport:
        issues: list[ReconciliationIssue] = []
        contracts = list(db.scalars(select(Contract)).all())
        fin = self.financial

        for c in contracts:
            snap = fin.compute_snapshot(db, c)
            if snap.saldo_final < 0:
                issues.append(
                    ReconciliationIssue(
                        code="NEGATIVE_BALANCE",
                        severity="error",
                        message=f"Contrato {c.id} saldo negativo: {snap.saldo_final}",
                        entity_type="contract",
                        entity_id=c.id,
                    )
                )
            if c.sales_sale_id:
                paid_db = fin.payments_total_for_sale(db, c.sales_sale_id)
                if abs(paid_db - snap.total_paid) > Decimal("0.05") and paid_db > 0:
                    issues.append(
                        ReconciliationIssue(
                            code="PAYMENT_MISMATCH",
                            severity="warning",
                            message=(
                                f"Contrato {c.id}: pagos venta {paid_db} vs consolidado {snap.total_paid}"
                            ),
                            entity_type="contract",
                            entity_id=c.id,
                        )
                    )
            if not c.customer_id:
                issues.append(
                    ReconciliationIssue(
                        code="MISSING_CUSTOMER",
                        severity="error",
                        message=f"Contrato {c.id} sin cliente",
                        entity_type="contract",
                        entity_id=c.id,
                    )
                )

        from app.models.contract import RefinanceOperation

        dup_refi = db.execute(
            select(RefinanceOperation.contract_id, func.count())
            .group_by(RefinanceOperation.contract_id)
            .having(func.count() > 1)
        ).all()
        for contract_id, cnt in dup_refi:
            issues.append(
                ReconciliationIssue(
                    code="DUPLICATE_REFI",
                    severity="warning",
                    message=f"Contrato {contract_id} con {cnt} operaciones de refinanciamiento",
                    entity_type="contract",
                    entity_id=contract_id,
                )
            )

        linked_sales = select(Contract.sales_sale_id).where(Contract.sales_sale_id.isnot(None))
        sales_without_contract = db.scalar(
            select(func.count(ErpSale.id)).where(ErpSale.id.not_in(linked_sales))
        ) or 0

        orphan_payments = list(
            db.scalars(
                select(ErpPayment).where(
                    ErpPayment.sale_id.is_(None),
                    ErpPayment.amount > 0,
                )
            ).all()
        )
        for p in orphan_payments:
            issues.append(
                ReconciliationIssue(
                    code="ORPHAN_PAYMENT",
                    severity="warning",
                    message=f"Pago huérfano #{p.id} sin venta (${p.amount})",
                    entity_type="payment",
                    entity_id=p.id,
                )
            )

        if sales_without_contract:
            issues.append(
                ReconciliationIssue(
                    code="SALE_WITHOUT_CONTRACT",
                    severity="info",
                    message=f"{sales_without_contract} ventas sin contrato consolidado",
                    entity_type="sale",
                )
            )

        payments_count = db.scalar(select(func.count(ErpPayment.id))) or 0

        return ErpReconciliationReport(
            issues=issues,
            contracts_checked=len(contracts),
            payments_checked=int(payments_count),
        )
