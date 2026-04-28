from typing import Generator

from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from starlette.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.models.case import Case
from app.web.services.revision_talon_calculator import calcular_revision_talon

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


@router.get("/casos/{case_id}/revision-talon")
def revision_talon_get(
    case_id: int,
    request: Request,
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request)
    if redirect:
        return redirect

    usuario = get_current_user(request)
    caso = db.query(Case).filter(Case.id == case_id).first()

    if not caso:
        return RedirectResponse(url="/casos", status_code=302)

    return templates.TemplateResponse(
        request=request,
        name="revision_talon.html",
        context={
            "usuario": usuario,
            "caso": caso,
            "resultado": None,
            "form_data": {
                "percepciones": 0,
                "deducciones": 0,
                "liquido": 0,
                "extra": 0,
                "tiene_programados": "NO",
                "monto_programados": 0,
            },
        },
    )


@router.post("/casos/{case_id}/revision-talon")
def revision_talon_post(
    case_id: int,
    request: Request,
    percepciones: float = Form(0),
    deducciones: float = Form(0),
    liquido: float = Form(0),
    extra: float = Form(0),
    tiene_programados: str = Form("NO"),
    monto_programados: float = Form(0),
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request)
    if redirect:
        return redirect

    usuario = get_current_user(request)
    caso = db.query(Case).filter(Case.id == case_id).first()

    if not caso:
        return RedirectResponse(url="/casos", status_code=302)

    tiene_programados_bool = tiene_programados == "SI"

    resultado = calcular_revision_talon(
        percepciones=percepciones,
        deducciones=deducciones,
        extra=extra,
        tiene_programados=tiene_programados_bool,
        monto_programados=monto_programados,
    )

    form_data = {
        "percepciones": percepciones,
        "deducciones": deducciones,
        "liquido": liquido,
        "extra": extra,
        "tiene_programados": tiene_programados,
        "monto_programados": monto_programados,
    }

    return templates.TemplateResponse(
        request=request,
        name="revision_talon.html",
        context={
            "usuario": usuario,
            "caso": caso,
            "resultado": resultado,
            "form_data": form_data,
        },
    )