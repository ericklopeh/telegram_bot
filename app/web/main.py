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
    from app.db.session import session_scope
    from app.repositories.user_repository import UserRepository
    from app.services.auth_service import AuthService

    with session_scope() as db:
        usuario = UserRepository.get_by_username(db, username)

        if not usuario or not AuthService.verify_password(password, usuario.hashed_password) or not usuario.is_active:
            return templates.TemplateResponse(
                request=request,
                name="login.html",
                context={
                    "error": "Usuario o contraseña incorrectos",
                }
            )

        request.session["usuario"] = {
            "username": usuario.username,
            "nombre": usuario.nombre,
            "rol": usuario.role,
        }

    return RedirectResponse(url="/dashboard", status_code=302)


@web_app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


web_app.include_router(dashboard.router)
web_app.include_router(cases.router)
web_app.include_router(revision_talon.router)