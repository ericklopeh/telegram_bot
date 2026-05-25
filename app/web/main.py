import logging
import sys
import traceback
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Form
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import PlainTextResponse, RedirectResponse, Response

from app.config import get_settings
from app.core.logging_setup import set_request_id, setup_logging
from app.services.storage_layout_service import ensure_runtime_directories
from app.web.paths import STATIC_DIR, TEMPLATES_DIR
from app.web.routes import (
    approved_authorizations,
    authorizations,
    case_documents,
    cases,
    sharepoint,
    admin_workflow,
    clients,
    commercial_reconciliation,
    commercial_reports,
    commissions,
    dashboard,
    erp,
    bi,
    health,
    operational,
    sales,
    revision_talon,
    imports,
)

_log = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def _lifespan(app: FastAPI):
    setup_logging(settings.log_level)
    ensure_runtime_directories()
    paths = [getattr(r, "path", None) for r in app.routes]
    paths = [p for p in paths if p]
    _log.warning(
        "Arranque web env=%s version=%s /health=%s /ping=%s",
        settings.environment,
        settings.app_version,
        "/health" in paths,
        "/ping" in paths,
    )
    yield


web_app = FastAPI(title="Sistema Gaman Web", lifespan=_lifespan)

web_app.add_middleware(
    SessionMiddleware,
    secret_key=settings.web_session_secret,
    same_site="lax",
    https_only=False,
)


@web_app.middleware("http")
async def _request_id_middleware(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:12]
    set_request_id(rid)
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


@web_app.middleware("http")
async def _security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    if settings.environment in ("staging", "production"):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


@web_app.middleware("http")
async def _log_unhandled_errors(request: Request, call_next):
    """Registra errores; traceback solo si WEB_DEBUG=true."""
    try:
        response = await call_next(request)
        code = getattr(response, "status_code", None)
        if code is not None and code >= 500:
            _log.error("HTTP %s para %s %s", code, request.method, request.url.path)
        return response
    except Exception as exc:
        if isinstance(exc, (HTTPException, RequestValidationError)):
            raise exc
        _log.exception("Excepción no controlada en %s %s", request.method, request.url.path)
        if settings.web_debug:
            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()
            body = (
                "Error interno (detalle para desarrollo).\n\n"
                f"{type(exc).__name__}: {exc}\n\n"
                f"{traceback.format_exc()}"
            )
            return PlainTextResponse(content=body, status_code=500, media_type="text/plain; charset=utf-8")
        return PlainTextResponse(
            content="Error interno del servidor. Contacte al administrador.",
            status_code=500,
            media_type="text/plain; charset=utf-8",
        )


templates = Jinja2Templates(directory=TEMPLATES_DIR)


@web_app.get("/ping")
def ping():
    """Comprueba que esta instancia es la app web (sin BD)."""
    return {"status": "ok", "service": "sistema_gaman_web"}


@web_app.get("/")
def index():
    return RedirectResponse(url="/login")


def _no_store_cache(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@web_app.get("/login")
def login_get(request: Request):
    resp = templates.TemplateResponse(
        request=request,
        name="login.html",
        context={
            "error": None,
        },
    )
    return _no_store_cache(resp)


@web_app.post("/login")
def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    from app.db.session import session_scope
    from app.repositories.user_repository import UserRepository
    from app.services.auth_service import AuthService

    username = username.strip()
    password = password.strip()

    with session_scope() as db:
        usuario = UserRepository.get_by_username(db, username)

        if not usuario or not AuthService.verify_password(password, usuario.hashed_password) or not usuario.is_active:
            return _no_store_cache(
                templates.TemplateResponse(
                    request=request,
                    name="login.html",
                    context={
                        "error": "Usuario o contraseña incorrectos",
                    },
                )
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


web_app.include_router(health.router)
web_app.include_router(dashboard.router)
web_app.include_router(admin_workflow.router)
web_app.include_router(cases.router)
web_app.include_router(case_documents.router)
web_app.include_router(sharepoint.router)
web_app.include_router(revision_talon.router)
web_app.include_router(authorizations.router)
web_app.include_router(approved_authorizations.router)
web_app.include_router(commercial_reports.router)
web_app.include_router(commercial_reconciliation.router)
web_app.include_router(commissions.router)
web_app.include_router(sales.router)
web_app.include_router(erp.router)
web_app.include_router(bi.router)
web_app.include_router(operational.router)
web_app.include_router(clients.router)
web_app.include_router(imports.router)

# Montar estáticos al final (recomendación FastAPI/Starlette) para no interferir con rutas HTTP.
web_app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
