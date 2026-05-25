"""Vista consolidada de cliente ERP (P27)."""

from __future__ import annotations

from typing import Generator

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db_session
from app.models.case_event import CaseEvent
from app.models.contract import Contract
from app.models.document import Document
from app.models.erp_customer import ErpCustomer
from app.models.erp_payment import ErpPayment
from app.services.contract_financial_service import ContractFinancialService
from app.web.auth import get_current_user, require_login
from app.web.paths import TEMPLATES_DIR
from app.web.services.case_timeline import build_case_timeline

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)
_financial = ContractFinancialService()


def get_web_db() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


@router.get("/clientes/{customer_id}")
def cliente_detalle(customer_id: int, request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)
    customer = db.get(ErpCustomer, customer_id)
    if not customer:
        from starlette.responses import RedirectResponse

        return RedirectResponse(url="/erp/dashboard", status_code=302)

    contracts = list(
        db.scalars(
            select(Contract)
            .options(joinedload(Contract.erp_sale), joinedload(Contract.refinances))
            .where(Contract.customer_id == customer_id)
            .order_by(Contract.created_at.desc())
        )
        .unique()
        .all()
    )
    contract_rows = [
        {"contract": c, "snapshot": _financial.compute_snapshot(db, c)} for c in contracts
    ]

    payments = list(
        db.scalars(
            select(ErpPayment)
            .join(Contract, ErpPayment.sale_id == Contract.sales_sale_id)
            .where(Contract.customer_id == customer_id)
            .order_by(ErpPayment.payment_date.desc())
            .limit(50)
        ).all()
    )

    case_ids = [c.case_id for c in contracts if c.case_id]
    documents = []
    timelines = []
    if case_ids:
        documents = list(
            db.scalars(
                select(Document)
                .where(Document.case_id.in_(case_ids), Document.is_active.is_(True))
                .limit(30)
            ).all()
        )
        events = list(
            db.scalars(
                select(CaseEvent)
                .where(CaseEvent.case_id.in_(case_ids))
                .order_by(CaseEvent.created_at.desc())
                .limit(80)
            ).all()
        )
        timelines = build_case_timeline(events)

    total_saldo = sum((row["snapshot"].saldo_final for row in contract_rows), start=0)

    return templates.TemplateResponse(
        request=request,
        name="client_detail.html",
        context={
            "usuario": usuario,
            "customer": customer,
            "contract_rows": contract_rows,
            "payments": payments,
            "documents": documents,
            "timelines": timelines,
            "total_saldo": total_saldo,
        },
    )
