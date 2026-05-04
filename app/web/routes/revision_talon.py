from typing import Generator

from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from starlette.responses import RedirectResponse
from sqlalchemy.orm import Session

from decimal import Decimal
from app.db.session import get_db_session
from app.models.case import Case
from app.web.services.talon_review_service import guardar_revision_talon

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
    percepciones: Decimal = Form(Decimal("0")),
    deducciones: Decimal = Form(Decimal("0")),
    liquido: Decimal = Form(Decimal("0")),
    extra: Decimal = Form(Decimal("0")),
    tiene_programados: str = Form("NO"),
    monto_programados: Decimal = Form(Decimal("0")),
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

    guardar_revision_talon(
        db=db,
        case=caso,
        percepciones=percepciones,
        deducciones=deducciones,
        liquido=liquido,
        extra=extra,
        tiene_programados=tiene_programados_bool,
        monto_programados=monto_programados,
        usuario_nombre=usuario.get("nombre", "web_user")
    )

    return RedirectResponse(url=f"/casos/{case_id}", status_code=302)