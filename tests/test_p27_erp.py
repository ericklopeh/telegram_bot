"""Pruebas P27 — consolidación ERP operacional/comercial."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from app.models.contract import CONTRACT_ACTIVE, Contract
from app.models.erp_customer import ErpCustomer
from app.models.erp_payment import ErpPayment
from app.models.erp_sale import ErpSale
from app.services.contract_financial_service import ContractFinancialService
from app.services.erp_export_service import ErpExportService
from app.services.erp_reconciliation_service import ErpReconciliationService
from app.services.erp_search_service import ErpSearchService
from app.services.excel_path_guard import is_under_excel_masters
from app.web.services.case_timeline import present_timeline_event
from app.models.case_event import CaseEvent
from app.services.case_event_service import PAYMENT_REGISTERED, REFINANCE_CREATED, CONTRACT_CLOSED


def _contract(**kwargs) -> Contract:
    c = Contract(
        id=1,
        customer_id=10,
        sales_sale_id=5,
        original_balance=Decimal("10000"),
        current_balance=Decimal("8000"),
        total_paid=Decimal("2000"),
        refinanced_amount=Decimal("0"),
        status=CONTRACT_ACTIVE,
    )
    for k, v in kwargs.items():
        setattr(c, k, v)
    return c


def test_compute_snapshot_balance_and_recovery():
    contract = _contract()
    sale = ErpSale(id=5, customer_id=10, total_amount=Decimal("10000"))
    db = MagicMock()
    db.get.return_value = sale
    db.scalar.side_effect = lambda _stmt: Decimal("500")
    db.scalars.return_value.all.return_value = []

    svc = ContractFinancialService()
    with patch.object(svc, "payments_total_for_sale", return_value=Decimal("3000")):
        snap = svc.compute_snapshot(db, contract)
    assert snap.total_sale == Decimal("10000.00")
    assert snap.total_paid == Decimal("3000.00")
    assert snap.refinanciado == Decimal("500.00")
    assert snap.saldo_sin_refin == Decimal("7000.00")
    assert snap.saldo_final == Decimal("7500.00")
    assert snap.recovery_pct == Decimal("30.00")


@patch("app.services.case_event_service.log_event")
def test_register_payment_updates_balance(mock_log):
    contract = _contract(case_id=99)
    db = MagicMock()
    db.get.return_value = contract
    payment = ErpPayment(id=7, sale_id=5, amount=Decimal("500"))
    db.add = MagicMock()
    db.flush = MagicMock()

    svc = ContractFinancialService()
    with patch.object(svc, "refresh_contract_balances", return_value=contract):
        result = svc.register_payment(db, 1, Decimal("500"), log_case_event=True)
    assert result.amount == Decimal("500.00")
    mock_log.assert_called_once()
    assert mock_log.call_args.kwargs["event_type"] == "PAYMENT_REGISTERED"


@patch("app.services.case_event_service.log_event")
def test_create_refinance_increases_balance(mock_log):
    contract = _contract(case_id=42)
    db = MagicMock()
    db.get.return_value = contract
    db.add = MagicMock()
    db.flush = MagicMock()

    svc = ContractFinancialService()
    snap = MagicMock()
    snap.saldo_final = Decimal("5000")
    with patch.object(svc, "compute_snapshot", return_value=snap):
        op = svc.create_refinance(db, 1, Decimal("1000"), notes="test")
    assert op.refinanced_amount == Decimal("1000.00")
    assert contract.refinanced_amount == Decimal("1000.00")
    mock_log.assert_called_once()


def test_reconciliation_detects_negative_balance():
    contract = _contract()
    db = MagicMock()
    db.scalars.return_value.all.side_effect = [
        [contract],
        [],
        [],
        [],
    ]
    db.scalar.return_value = None

    snap = MagicMock()
    snap.saldo_final = Decimal("-1")
    snap.total_paid = Decimal("0")

    with patch.object(ContractFinancialService, "compute_snapshot", return_value=snap):
        with patch.object(ContractFinancialService, "payments_total_for_sale", return_value=Decimal("0")):
            report = ErpReconciliationService().build_report(db)
    codes = [i.code for i in report.issues]
    assert "NEGATIVE_BALANCE" in codes


def test_global_search_requires_min_length():
    db = MagicMock()
    assert ErpSearchService().search(db, "a") == []
    db.scalars.assert_not_called()


def test_global_search_finds_customer():
    customer = ErpCustomer(id=3, name="Juan Pérez", rfc="XAXX010101000", curp=None)
    db = MagicMock()
    db.scalars.return_value.all.side_effect = [[customer], [], []]
    hits = ErpSearchService().search(db, "Juan")
    assert hits[0].kind == "cliente"
    assert hits[0].url == "/clientes/3"


def test_erp_export_writes_under_exports_not_masters(tmp_path):
    export_dir = tmp_path / "excel_exports" / "erp"
    with patch("app.services.erp_export_service.EXCEL_EXPORTS_DIR", tmp_path / "excel_exports"):
        with patch("app.services.erp_export_service.assert_writable_excel_path") as guard:
            db = MagicMock()
            db.scalars.return_value.unique.return_value.all.return_value = []
            path = ErpExportService().export_executive_summary(db)
            guard.assert_called_once()
    assert "excel_masters" not in str(path).replace("\\", "/")
    assert not is_under_excel_masters(path)
    assert path.parent == export_dir or path.parent.name == "erp"


def test_timeline_labels_for_financial_events():
    for et, label in (
        (PAYMENT_REGISTERED, "Pago registrado"),
        (REFINANCE_CREATED, "Refinanciamiento creado"),
        (CONTRACT_CLOSED, "Contrato cerrado"),
    ):
        ev = CaseEvent(id=1, case_id=1, event_type=et, message=None, source="erp")
        item = present_timeline_event(ev)
        assert item["type_label"] == label
