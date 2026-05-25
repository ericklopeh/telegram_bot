"""Captura de ventas web (P19 / P19.1)."""

from __future__ import annotations

import urllib.parse
from pathlib import Path
from typing import Generator

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.config import get_settings
from app.db.session import get_db_session
from app.models.sale_capture import (
    REG_STATUS_REGISTERED,
    REG_STATUS_REGISTRATION_FAILED,
    SALE_STATUS_DRAFT,
    SALE_STATUS_EXPORT_FAILED,
    SALE_STATUS_PENDING_VALIDATION,
    SALE_STATUS_REGISTERED,
    effective_registration_status,
)
from app.repositories.sale_capture_repository import SaleCaptureRepository
from app.services.sale_capture_case_prefill import build_form_prefill_from_case
from app.services.sale_capture_service import SaleCaptureService
from app.web.auth import (
    ROLES_AUTORIZACION_SNTE,
    get_current_user,
    require_login,
    require_roles,
    web_should_scope_vendedor_cases,
)
from app.web.paths import TEMPLATES_DIR

router = APIRouter()
templates = Jinja2Templates(directory=TEMPLATES_DIR)

STATUS_LABELS = {
    SALE_STATUS_DRAFT: "Borrador",
    SALE_STATUS_PENDING_VALIDATION: "Pendiente validación",
    SALE_STATUS_REGISTERED: "Registrada",
    SALE_STATUS_EXPORT_FAILED: "Error exportación",
}

REGISTRATION_STATUS_LABELS = {
    "draft": "Borrador",
    "pending_validation": "Pendiente validación",
    "pending_registration": "Cola de registro",
    "processing_registration": "Procesando Excel",
    "registered": "Registrada",
    "registration_failed": "Registro fallido",
}


def get_web_db() -> Generator[Session, None, None]:
    db = get_db_session()
    try:
        yield db
    finally:
        db.close()


def _sale_to_form(sale) -> dict:
    return {
        "id": sale.id,
        "folio": sale.folio,
        "fecha": sale.sale_date.isoformat() if sale.sale_date else "",
        "vendedor": sale.vendedor,
        "seccion": sale.seccion or "",
        "qna": sale.qna or "",
        "cliente": sale.cliente,
        "rfc": sale.rfc or "",
        "codigo": sale.codigo or "",
        "producto": sale.producto or "",
        "tipo_venta": sale.tipo_venta or "",
        "plazo": sale.plazo if sale.plazo is not None else "",
        "costo": str(sale.costo) if sale.costo is not None else "",
        "venta": str(sale.venta) if sale.venta is not None else "",
        "venta_refinanciamiento": (
            str(sale.venta_refinanciamiento) if sale.venta_refinanciamiento is not None else ""
        ),
        "total_venta": str(sale.total_venta) if sale.total_venta is not None else "",
        "precio_comision": str(sale.precio_comision) if sale.precio_comision is not None else "",
        "venta_sin_agregado": (
            str(sale.venta_sin_agregado) if sale.venta_sin_agregado is not None else ""
        ),
        "recuperacion": str(sale.recuperacion) if sale.recuperacion is not None else "",
        "tipo_cotizacion": sale.tipo_cotizacion or "",
        "observaciones": sale.observaciones or "",
        "semana": sale.semana or "",
        "status": sale.status,
        "case_id": sale.case_id,
    }


def _form_context(
    db: Session,
    usuario: dict,
    *,
    form: dict,
    sale=None,
    errors: list | None = None,
    success_msg: str | None = None,
    error_msg: str | None = None,
    detail_mode: bool = False,
    warnings: list | None = None,
) -> dict:
    svc = SaleCaptureService()
    perms = svc.permissions(db, usuario, sale, form=form)
    checklist = svc.checklist(db, sale) if detail_mode or sale else None
    return {
        "usuario": usuario,
        "form": form,
        "sale": sale,
        "errors": errors or [],
        "warnings": warnings or [],
        "success_msg": success_msg,
        "error_msg": error_msg,
        "perms": perms,
        "checklist": checklist,
        "can_validate": svc.can_validate(usuario),
        "can_register": perms.can_register_definitive,
        "is_readonly": bool(
            sale
            and effective_registration_status(sale) == REG_STATUS_REGISTERED
            and not perms.can_edit
        ),
        "detail_mode": detail_mode,
        "status_labels": STATUS_LABELS,
        "registration_status_labels": REGISTRATION_STATUS_LABELS,
    }


@router.get("/ventas")
def listar_ventas(
    request: Request,
    db: Session = Depends(get_web_db),
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    vendedor: str | None = Query(default=None),
    folio: str | None = Query(default=None),
    cliente: str | None = Query(default=None),
    rfc: str | None = Query(default=None),
    registered: str | None = Query(default=None),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)
    if web_should_scope_vendedor_cases(usuario or {}):
        vendedor = usuario.get("nombre")

    ventas = SaleCaptureRepository.list_recent(
        db,
        vendedor=vendedor,
        status=status,
        q=q,
        folio=folio,
        cliente=cliente,
        rfc=rfc,
        registered=registered,
        limit=200,
    )
    vendedores = SaleCaptureRepository.list_vendedores(db)

    return templates.TemplateResponse(
        request=request,
        name="ventas_list.html",
        context={
            "usuario": usuario,
            "ventas": ventas,
            "vendedores": vendedores,
            "filtros": {
                "q": q or "",
                "status": status or "",
                "vendedor": vendedor or "",
                "folio": folio or "",
                "cliente": cliente or "",
                "rfc": rfc or "",
                "registered": registered or "",
            },
            "status_labels": STATUS_LABELS,
        },
    )


@router.get("/ventas/nueva")
def ventas_nueva_get(
    request: Request,
    db: Session = Depends(get_web_db),
    id: int | None = Query(default=None),
    case_id: int | None = Query(default=None),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)
    svc = SaleCaptureService()
    sale = None
    form_data: dict = {}

    if id:
        sale = SaleCaptureRepository.get_by_id(db, id)
        if not sale:
            return RedirectResponse(url="/ventas", status_code=302)
        if not svc.can_edit_sale(db, sale, usuario or {}):
            msg = urllib.parse.quote("No tienes permiso para editar esta captura.")
            return RedirectResponse(url=f"/ventas?error={msg}", status_code=302)
        form_data = _sale_to_form(sale)
    elif case_id:
        prefill, err = build_form_prefill_from_case(
            db, case_id, suggested_folio=svc.suggest_folio(db)
        )
        if err:
            return RedirectResponse(
                url=f"/ventas/nueva?error={urllib.parse.quote(err)}", status_code=302
            )
        form_data = prefill or {}
    else:
        default_vendedor = usuario.get("nombre") or ""
        form_data = {
            "folio": svc.suggest_folio(db),
            "fecha": "",
            "vendedor": default_vendedor,
            "semana": get_settings().effective_semana_activa,
            "tipo_venta": "PARALELA",
            "tipo_cotizacion": "MATERIAL",
        }

    ctx = _form_context(
        db,
        usuario or {},
        form=form_data,
        sale=sale,
        success_msg=request.query_params.get("success"),
        error_msg=request.query_params.get("error"),
    )
    return templates.TemplateResponse(request=request, name="ventas_form.html", context=ctx)


@router.post("/ventas/nueva")
async def ventas_nueva_post(
    request: Request,
    db: Session = Depends(get_web_db),
    action: str = Form("save_draft"),
    sale_id: str = Form(""),
    confirm_probable_duplicate: str = Form(""),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)
    form = dict(await request.form())
    sid: int | None = None
    if sale_id and str(sale_id).strip().isdigit():
        sid = int(sale_id)

    if web_should_scope_vendedor_cases(usuario or {}):
        form["vendedor"] = usuario.get("nombre") or form.get("vendedor", "")

    linked_case_id = None
    if str(form.get("case_id", "")).isdigit():
        linked_case_id = int(form["case_id"])

    svc = SaleCaptureService()
    sale = None
    errors: list[str] = []
    warnings: list[str] = []
    confirm_dup = confirm_probable_duplicate in ("1", "true", "on", "yes")

    if action == "save_draft":
        sale, result_msgs = svc.save_draft(
            db, usuario or {}, form, sale_id=sid, linked_case_id=linked_case_id
        )
        if sale is None:
            errors = result_msgs
        else:
            warnings = result_msgs
    elif action == "submit_validation":
        sale, result_msgs = svc.submit_for_validation(
            db, usuario or {}, form, sale_id=sid, linked_case_id=linked_case_id
        )
        if sale is None:
            errors = result_msgs
        else:
            warnings = result_msgs
    elif action == "register":
        sale, result_msgs = svc.register_definitive(
            db,
            usuario or {},
            form,
            sale_id=sid,
            linked_case_id=linked_case_id,
            confirm_probable_duplicate=confirm_dup,
        )
        if sale is None:
            errors = result_msgs
        else:
            warnings = result_msgs
    else:
        errors = ["Acción no reconocida."]

    if errors:
        sale_obj = SaleCaptureRepository.get_by_id(db, sid) if sid else None
        ctx = _form_context(
            db,
            usuario or {},
            form=form,
            sale=sale_obj,
            errors=errors,
            warnings=warnings,
            detail_mode=bool(sale_obj and request.query_params.get("from_detail")),
        )
        return templates.TemplateResponse(
            request=request, name="ventas_form.html", context=ctx, status_code=422
        )

    db.commit()

    if action == "register" and sale:
        msg = urllib.parse.quote(
            f"Venta {sale.folio} registrada. Puedes descargar los Excel generados."
        )
        return RedirectResponse(url=f"/ventas/{sale.id}?success={msg}", status_code=302)

    if sale:
        msg = urllib.parse.quote("Guardado correctamente.")
        target = f"/ventas/{sale.id}" if action == "submit_validation" else f"/ventas/nueva?id={sale.id}"
        return RedirectResponse(url=f"{target}?success={msg}", status_code=302)

    return RedirectResponse(url="/ventas", status_code=302)


@router.get("/ventas/pendientes")
def ventas_pendientes(
    request: Request,
    db: Session = Depends(get_web_db),
    registration_status: str | None = Query(default=None),
    vendedor: str | None = Query(default=None),
    q: str | None = Query(default=None),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_AUTORIZACION_SNTE)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    ventas = SaleCaptureRepository.list_pending_registration(
        db,
        registration_status=registration_status,
        vendedor=vendedor,
        q=q,
    )
    vendedores = SaleCaptureRepository.list_vendedores(db)

    return templates.TemplateResponse(
        request=request,
        name="ventas_pending.html",
        context={
            "usuario": usuario,
            "ventas": ventas,
            "vendedores": vendedores,
            "filtros": {
                "registration_status": registration_status or "",
                "vendedor": vendedor or "",
                "q": q or "",
            },
            "registration_status_labels": REGISTRATION_STATUS_LABELS,
        },
    )


@router.post("/ventas/{sale_id}/reintentar-registro")
async def reintentar_registro_venta(
    sale_id: int,
    request: Request,
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect
    denied = require_roles(request, db, ROLES_AUTORIZACION_SNTE)
    if denied:
        return denied

    usuario = get_current_user(request, db)
    from app.services.sale_action_guard_service import assert_action

    sale = SaleCaptureRepository.get_by_id(db, sale_id)
    if not sale:
        return RedirectResponse(url="/ventas/pendientes", status_code=302)

    ok, reason = assert_action(db, usuario or {}, sale, "retry_registration")
    if not ok:
        msg = urllib.parse.quote(reason or "Reintento no permitido.")
        return RedirectResponse(url=f"/ventas/{sale_id}?error={msg}", status_code=302)

    svc = SaleCaptureService()
    updated, errors = svc.retry_registration(db, usuario or {}, sale_id)
    db.commit()

    if errors:
        err_msg = urllib.parse.quote(errors[0])
        return RedirectResponse(url=f"/ventas/{sale_id}?error={err_msg}", status_code=302)

    folio = updated.folio if updated else sale.folio
    msg = urllib.parse.quote(f"Reintento exitoso: venta {folio} registrada en Excel.")
    return RedirectResponse(url=f"/ventas/{sale_id}?success={msg}", status_code=302)


@router.get("/ventas/{sale_id}")
def ventas_detalle(
    sale_id: int,
    request: Request,
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    usuario = get_current_user(request, db)
    sale = SaleCaptureRepository.get_by_id(db, sale_id)
    if not sale:
        return RedirectResponse(url="/ventas", status_code=302)

    if web_should_scope_vendedor_cases(usuario or {}):
        if sale.vendedor != usuario.get("nombre"):
            return RedirectResponse(url="/ventas", status_code=302)

    ctx = _form_context(
        db,
        usuario or {},
        form=_sale_to_form(sale),
        sale=sale,
        success_msg=request.query_params.get("success"),
        error_msg=request.query_params.get("error"),
        detail_mode=True,
    )
    if sale.case_id:
        from app.repositories.case_repository import CaseRepository
        from app.web.services.workflow_visualization import build_workflow_pipeline

        linked_case = CaseRepository.get_by_id(db, sale.case_id)
        if linked_case:
            ctx["workflow_pipeline"] = build_workflow_pipeline(db, linked_case)
            ctx["caso"] = linked_case
            ctx["can_recalc_workflow"] = (usuario or {}).get("rol") in ROLES_AUTORIZACION_SNTE
    return templates.TemplateResponse(request=request, name="ventas_form.html", context=ctx)


@router.get("/ventas/{sale_id}/descargar/{kind}")
def descargar_excel_venta(
    sale_id: int,
    kind: str,
    request: Request,
    db: Session = Depends(get_web_db),
):
    redirect = require_login(request, db)
    if redirect:
        return redirect

    from app.security.rbac import Permission
    from app.web.rbac_helpers import require_permission

    perm_redirect = require_permission(
        request,
        db,
        Permission.EXPORT,
        action="download_sale_export",
        entity_type="sale_capture",
        entity_id=sale_id,
    )
    if perm_redirect:
        return perm_redirect

    usuario = get_current_user(request, db)
    sale = SaleCaptureRepository.get_by_id(db, sale_id)
    if not sale:
        return RedirectResponse(url="/ventas", status_code=302)

    action = "download_ventas" if kind == "ventas" else "download_contratos"
    from app.services.sale_action_guard_service import assert_action

    ok, reason = assert_action(db, usuario or {}, sale, action)
    if not ok:
        msg = urllib.parse.quote(reason or "Descarga no disponible.")
        return RedirectResponse(url=f"/ventas/{sale_id}?error={msg}", status_code=302)

    path_str = sale.ventas_export_path if kind == "ventas" else sale.contratos_export_path
    if not path_str:
        msg = urllib.parse.quote("No hay archivo exportado para esta venta.")
        return RedirectResponse(url=f"/ventas/{sale_id}?error={msg}", status_code=302)

    path = Path(path_str)
    if not path.is_file():
        msg = urllib.parse.quote("El archivo exportado ya no está en el servidor.")
        return RedirectResponse(url=f"/ventas/{sale_id}?error={msg}", status_code=302)

    return FileResponse(
        path=path,
        filename=path.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
