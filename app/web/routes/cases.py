from typing import Generator

from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from starlette.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.models.case import Case

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


def get_current_user(request: Request):
    return request.session.get("usuario")


def require_login(request: Request):
    usuario = get_current_user(request)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    return None


def get_web_db() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


@router.get("/casos")
def listar_casos(
    request: Request,
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request)
    if redirect:
        return redirect

    usuario = get_current_user(request)

    query = db.query(Case)

    if usuario["rol"] == "vendedor":
        query = query.filter(Case.seller_name == usuario["nombre"])

    casos = query.order_by(Case.created_at.desc()).limit(50).all()

    return templates.TemplateResponse(
        request=request,
        name="cases.html",
        context={
            "usuario": usuario,
            "casos": casos,
        }
    )