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


@router.get("/dashboard")
def dashboard(request: Request):
    redirect = require_login(request)
    if redirect:
        return redirect

    usuario = get_current_user(request)

    resumen = {
        "total": 12,
        "recibidos": 4,
        "en_revision": 3,
        "aprobados": 4,
        "rechazados": 1,
    }

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "usuario": usuario,
            "resumen": resumen,
        }
    )