"""Consolidación contratos desde ventas históricas y sale_captures (P27)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.contract import CONTRACT_ACTIVE, Contract, ContractInstallment
from app.models.erp_customer import ErpCustomer
from app.models.erp_payment import ErpInstallment
from app.models.erp_sale import ErpSale
from app.models.sale_capture import SaleCapture, REG_STATUS_REGISTERED


class ErpConsolidationService:
    def ensure_contract_for_sale(self, db: Session, sale_id: int) -> Contract:
        existing = db.scalar(select(Contract).where(Contract.sales_sale_id == sale_id))
        if existing:
            return existing
        sale = db.get(ErpSale, sale_id)
        if not sale:
            raise ValueError(f"Venta ERP {sale_id} no encontrada.")
        contract = Contract(
            customer_id=sale.customer_id,
            sales_sale_id=sale.id,
            folio=sale.folio,
            contract_code=sale.contract_code,
            original_balance=sale.total_amount,
            current_balance=sale.total_amount,
            status=CONTRACT_ACTIVE,
        )
        db.add(contract)
        db.flush()
        self._sync_installments_from_sale(db, contract, sale)
        return contract

    def _sync_installments_from_sale(self, db: Session, contract: Contract, sale: ErpSale) -> None:
        for inst in db.scalars(
            select(ErpInstallment).where(ErpInstallment.sale_id == sale.id)
        ).all():
            exists = db.scalar(
                select(ContractInstallment.id).where(
                    ContractInstallment.contract_id == contract.id,
                    ContractInstallment.payments_installment_id == inst.id,
                )
            )
            if exists:
                continue
            db.add(
                ContractInstallment(
                    contract_id=contract.id,
                    payments_installment_id=inst.id,
                    installment_number=inst.installment_number,
                    due_date=inst.due_date,
                    amount=inst.amount,
                    paid_amount=inst.paid_amount,
                    status=inst.status,
                )
            )

    def link_sale_capture(self, db: Session, sale_capture: SaleCapture) -> Contract | None:
        if not sale_capture.cliente:
            return None
        customer = db.scalar(
            select(ErpCustomer).where(ErpCustomer.name == sale_capture.cliente).limit(1)
        )
        if not customer:
            customer = ErpCustomer(
                name=sale_capture.cliente,
                seccion=sale_capture.seccion,
            )
            db.add(customer)
            db.flush()
        amount = sale_capture.total_venta or sale_capture.venta or Decimal("0")
        existing = db.scalar(
            select(Contract).where(Contract.sale_capture_id == sale_capture.id)
        )
        if existing:
            return existing
        erp_sale = ErpSale(
            customer_id=customer.id,
            folio=sale_capture.folio,
            vendedor=sale_capture.vendedor,
            seccion=sale_capture.seccion,
            sale_date=sale_capture.sale_date,
            total_amount=amount,
            status="active",
        )
        db.add(erp_sale)
        db.flush()
        contract = Contract(
            customer_id=customer.id,
            sales_sale_id=erp_sale.id,
            sale_capture_id=sale_capture.id,
            case_id=sale_capture.case_id,
            folio=sale_capture.folio,
            original_balance=amount,
            current_balance=amount,
            status=CONTRACT_ACTIVE,
        )
        db.add(contract)
        db.flush()
        return contract

    def sync_registered_sale_captures(self, db: Session, *, limit: int = 500) -> int:
        rows = list(
            db.scalars(
                select(SaleCapture)
                .where(SaleCapture.registration_status == REG_STATUS_REGISTERED)
                .order_by(SaleCapture.id.desc())
                .limit(limit)
            ).all()
        )
        n = 0
        for sc in rows:
            if self.link_sale_capture(db, sc):
                n += 1
        return n
