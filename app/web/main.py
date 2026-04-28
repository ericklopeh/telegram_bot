from fastapi import FastAPI, Request, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse

from app.web.routes import dashboard, cases, revision_talon


web_app = FastAPI(title="Sistema Gaman Web")

web_app.add_middleware(
    SessionMiddleware,
    secret_key="CAMBIA_ESTA_CLAVE_DEMO_GAMAN_2026"
)

web_app.mount("/static", StaticFiles(directory="app/web/static"), name="static")

templates = Jinja2Templates(directory="app/web/templates")


@web_app.get("/")
def index():
    return RedirectResponse(url="/login")


@web_app.get("/login")
def login_get(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "error": None,
        }
    )


@web_app.post("/login")
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    usuarios_demo = {
        "admin": {
            "password": "Admin2026!",
            "nombre": "Administrador",
            "rol": "admin"
        },
        "jefe": {
            "password": "Jefe2026!",
            "nombre": "Gerencia",
            "rol": "jefe"
        },
        "autorizaciones": {
            "password": "Auto2026!",
            "nombre": "Autorizaciones",
            "rol": "autorizaciones"
        },
        "vendedor": {
            "password": "Vend2026!",
            "nombre": "Vendedor Demo",
            "rol": "vendedor"
        },
    }

    usuario = usuarios_demo.get(username)

    if not usuario or usuario["password"] != password:
        return templates.TemplateResponse(
            request=request,
            name="login.html",
            context={
                "error": "Usuario o contraseña incorrectos",
            }
        )

    request.session["usuario"] = {
        "username": username,
        "nombre": usuario["nombre"],
        "rol": usuario["rol"],
    }

    return RedirectResponse(url="/dashboard", status_code=302)


@web_app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


web_app.include_router(dashboard.router)
web_app.include_router(cases.router)
web_app.include_router(revision_talon.router)