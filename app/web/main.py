import sys
import traceback

from fastapi import FastAPI, Request, Form
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import PlainTextResponse, RedirectResponse

from app.config import get_settings
from app.web.paths import STATIC_DIR, TEMPLATES_DIR
from app.web.routes import dashboard, cases, revision_talon, authorizations

web_app = FastAPI(title="Sistema Gaman Web")
settings = get_settings()

web_app.add_middleware(
    SessionMiddleware,
    secret_key=settings.web_session_secret,
    same_site="lax",
    https_only=False,
)


@web_app.middleware("http")
async def _log_unhandled_errors(request: Request, call_next):
    """Siempre imprime traceback a stderr; con WEB_DEBUG además responde texto en el navegador."""
    try:
        return await call_next(request)
    except Exception as exc:
        if isinstance(exc, (HTTPException, RequestValidationError)):
            raise exc
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        if settings.web_debug:
            body = (
                "WEB_DEBUG=true: detalle del error (desactivar WEB_DEBUG en producción).\n\n"
                f"{type(exc).__name__}: {exc}\n\n"
                f"{traceback.format_exc()}"
            )
            return PlainTextResponse(
                content=body,
                status_code=500,
                media_type="text/plain; charset=utf-8",
            )
        raise


templates = Jinja2Templates(directory=TEMPLATES_DIR)


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
            "id": usuario.id,
            "user_id": usuario.id,
            "username": usuario.username,
            "nombre": usuario.nombre,
            "rol": getattr(usuario.role, "value", usuario.role),
        }

    return RedirectResponse(url="/dashboard", status_code=302)


@web_app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


web_app.include_router(dashboard.router)
web_app.include_router(cases.router)
web_app.include_router(revision_talon.router)
web_app.include_router(authorizations.router)

# Montar estáticos al final (recomendación FastAPI/Starlette) para no interferir con rutas HTTP.
web_app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
