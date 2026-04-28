from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from starlette.responses import RedirectResponse

router = APIRouter()
templates = Jinja2Templates(directory="app/web/templates")


def get_current_user(request: Request):
    return request.session.get("usuario")


def require_login(request: Request):
    usuario = get_current_user(request)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    return None


@router.get("/casos")
def listar_casos(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect

    usuario = get_current_user(request)

    casos = [
        {
            "id": 1,
            "public_id": "PED-00001",
            "client_name": "CLIENTE DEMO 01",
            "seller_name": "Vendedor Demo",
            "case_type": "pedido",
            "current_status": "Recibido",
            "week_code": "SEM 17-2026",
        },
        {
            "id": 2,
            "public_id": "REV-00002",
            "client_name": "CLIENTE DEMO 02",
            "seller_name": "Vendedor Demo",
            "case_type": "revision",
            "current_status": "En revisión",
            "week_code": "SEM 17-2026",
        },
    ]

    return templates.TemplateResponse(
        request=request,
        name="cases.html",
        context={
            "usuario": usuario,
            "casos": casos,
        }
    )