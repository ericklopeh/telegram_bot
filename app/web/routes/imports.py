"""Rutas importación histórica Excel (P32)."""

from __future__ import annotations

from typing import Generator

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.templating import Jinja2Templates
from starlette.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.models.import_batch import SOURCE_CONTRATOS, SOURCE_VENTAS
from app.services.beta_safe_mode_service import BetaSafeModeService
from app.services.excel_import_service import ExcelImportService
from app.web.auth import ROLES_ADMIN_SISTEMAS, get_current_user, require_login, require_roles
from app.web.paths import TEMPLATES_DIR

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)
_svc = ExcelImportService()
_safe = BetaSafeModeService()


def get_web_db() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


@router.get("/imports")
def imports_list(request: Request, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    batches = _svc.list_batches(db)
    msg = request.query_params.get("msg")
    err = request.query_params.get("error")

    return templates.TemplateResponse(
        request=request,
        name="imports_list.html",
        context={
            "usuario": usuario,
            "batches": batches,
            "msg": msg,
            "error": err,
            "beta_safe_mode": _safe.is_enabled(),
        },
    )


@router.post("/imports/upload")
async def imports_upload(
    request: Request,
    db: Session = Depends(get_web_db),
    source_type: str = Form(...),
    file: UploadFile = File(...),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    if source_type not in (SOURCE_VENTAS, SOURCE_CONTRATOS):
        return RedirectResponse(url="/imports?error=Tipo+de+origen+inválido", status_code=302)

    content = await file.read()
    if not content:
        return RedirectResponse(url="/imports?error=Archivo+vacío", status_code=302)

    try:
        batch = _svc.create_batch_from_upload(
            db,
            content=content,
            filename=file.filename or "upload.xlsx",
            source_type=source_type,
            user_id=usuario.get("user_id"),
            username=usuario.get("username"),
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        return RedirectResponse(url=f"/imports?error={exc}", status_code=302)

    return RedirectResponse(url=f"/imports/{batch.id}/preview", status_code=302)


@router.get("/imports/{batch_id}/preview")
def imports_preview(request: Request, batch_id: int, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    batch = _svc.get_batch(db, batch_id)
    if not batch:
        return RedirectResponse(url="/imports?error=Lote+no+encontrado", status_code=302)

    if batch.status == "confirmed":
        return RedirectResponse(url=f"/imports?msg=Lote+{batch_id}+ya+confirmado", status_code=302)
    if batch.status == "rolled_back":
        return RedirectResponse(url="/imports?error=Lote+revertido", status_code=302)

    try:
        if batch.status in ("uploaded", "previewed", "failed"):
            batch = _svc.preview_batch(db, batch_id, username=usuario.get("username"))
            db.commit()
    except Exception as exc:
        db.rollback()
        return RedirectResponse(url=f"/imports?error={exc}", status_code=302)

    errors = _svc.list_row_errors(db, batch_id)
    return templates.TemplateResponse(
        request=request,
        name="imports_preview.html",
        context={
            "usuario": usuario,
            "batch": batch,
            "errors": errors[:100],
            "error_total": len(errors),
        },
    )


@router.post("/imports/{batch_id}/confirm")
def imports_confirm(request: Request, batch_id: int, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    try:
        batch = _svc.confirm_batch(db, batch_id, username=usuario.get("username"))
        db.commit()
    except Exception as exc:
        db.rollback()
        return RedirectResponse(
            url=f"/imports/{batch_id}/preview?error={exc}",
            status_code=302,
        )

    return RedirectResponse(
        url=f"/imports?msg=Importados+{batch.imported_count}+registros+(lote+{batch_id})",
        status_code=302,
    )


@router.post("/imports/{batch_id}/rollback")
def imports_rollback(
    request: Request,
    batch_id: int,
    db: Session = Depends(get_web_db),
    confirm_text: str = Form(""),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    ok, err = _safe.block_mass_rollback_without_phrase(
        batch_id,
        confirm_text,
        username=usuario.get("username"),
    )
    if not ok:
        return RedirectResponse(url=f"/imports?error={err}", status_code=302)

    try:
        _svc.rollback_batch(db, batch_id, username=usuario.get("username"))
        db.commit()
    except Exception as exc:
        db.rollback()
        return RedirectResponse(url=f"/imports?error={exc}", status_code=302)

    return RedirectResponse(url=f"/imports?msg=Lote+{batch_id}+revertido", status_code=302)


@router.get("/imports/{batch_id}/errors")
def imports_errors(request: Request, batch_id: int, db: Session = Depends(get_web_db)):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_ADMIN_SISTEMAS)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    batch = _svc.get_batch(db, batch_id)
    if not batch:
        return RedirectResponse(url="/imports?error=Lote+no+encontrado", status_code=302)

    errors = _svc.list_row_errors(db, batch_id)
    download = request.query_params.get("download")

    if download == "xlsx":
        try:
            path = _svc.export_errors_xlsx(db, batch_id)
        except Exception as exc:
            return RedirectResponse(
                url=f"/imports/{batch_id}/errors?error={exc}",
                status_code=302,
            )
        return FileResponse(
            path,
            filename=path.name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    return templates.TemplateResponse(
        request=request,
        name="imports_errors.html",
        context={
            "usuario": usuario,
            "batch": batch,
            "errors": errors,
        },
    )
