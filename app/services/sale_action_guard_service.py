"""Reglas de acciones permitidas en captura de ventas (P19.1)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.sale_capture import (
    REG_STATUS_REGISTRATION_FAILED,
    SALE_STATUS_DRAFT,
    SALE_STATUS_EXPORT_FAILED,
    SALE_STATUS_PENDING_VALIDATION,
    SALE_STATUS_REGISTERED,
    SaleCapture,
    can_retry_registration,
    effective_registration_status,
    is_registration_complete,
)
from app.models.user import UserRole
from app.repositories.sale_capture_repository import SaleCaptureRepository
from app.security.rbac import Permission
from app.services.rbac_service import RbacService
from app.services.sale_capture_checklist import build_sale_checklist
from app.services.sale_capture_validation import parse_sale_form

_rbac = RbacService()

_ROLES_REGISTER = frozenset(
    {
        UserRole.ADMIN.value,
        UserRole.SISTEMAS.value,
        UserRole.AUTORIZACION.value,
    }
)
_ROLES_EDIT_REGISTERED = frozenset(
    {
        UserRole.ADMIN.value,
        UserRole.SISTEMAS.value,
    }
)


@dataclass
class SaleActionPermissions:
    can_save_draft: bool = False
    can_submit_validation: bool = False
    can_register_definitive: bool = False
    can_edit: bool = False
    can_download_ventas: bool = False
    can_download_contratos: bool = False
    can_retry_registration: bool = False
    save_draft_reason: str | None = None
    submit_validation_reason: str | None = None
    register_reason: str | None = None
    edit_reason: str | None = None
    download_reason: str | None = None
    checklist_ready: bool = False
    checklist_block: str | None = None


def _user_role(user: dict[str, Any] | None) -> str:
    return str((user or {}).get("rol", "")).strip().lower()


def _rbac_relaxed() -> bool:
    return bool(get_settings().web_rbac_relaxed)


def _apply_rbac_sale_overlay(perms: SaleActionPermissions, user: dict[str, Any] | None) -> None:
    """P81 — capa RBAC sobre permisos de venta (UI + POST)."""
    if _rbac.is_relaxed():
        return
    if not _rbac.has_permission(user, Permission.EDIT):
        perms.can_edit = False
        perms.can_save_draft = False
        perms.can_submit_validation = False
        if not perms.edit_reason:
            perms.edit_reason = "Sin permiso de edición (RBAC)."
    if not _rbac.has_permission(user, Permission.APPROVE):
        perms.can_register_definitive = False
        perms.can_retry_registration = False
        if not perms.register_reason:
            perms.register_reason = "Sin permiso de aprobación/registro (RBAC)."
    if not _rbac.has_permission(user, Permission.EXPORT):
        perms.can_download_ventas = False
        perms.can_download_contratos = False
        if not perms.download_reason:
            perms.download_reason = "Sin permiso de exportación/descarga (RBAC)."


def get_sale_action_permissions(
    db: Session,
    user: dict[str, Any] | None,
    sale: SaleCapture | None,
    *,
    form: dict[str, Any] | None = None,
) -> SaleActionPermissions:
    """Evalúa permisos y checklist para la UI y POST."""
    perms = SaleActionPermissions()
    role = _user_role(user)
    relaxed = _rbac_relaxed()
    uid = (user or {}).get("id")

    if sale and is_registration_complete(sale):
        can_edit_reg = role in _ROLES_EDIT_REGISTERED or relaxed
        perms.can_edit = can_edit_reg
        if not can_edit_reg:
            perms.edit_reason = "Solo administración o sistemas puede editar ventas registradas."
        perms.can_download_ventas = bool(
            sale.ventas_export_path and Path(sale.ventas_export_path).is_file()
        )
        perms.can_download_contratos = bool(
            sale.contratos_export_path and Path(sale.contratos_export_path).is_file()
        )
        if not perms.can_download_ventas and not perms.can_download_contratos:
            perms.download_reason = "No hay archivos exportados disponibles."
        perms.register_reason = "La venta ya está registrada."
        _apply_rbac_sale_overlay(perms, user)
        return perms

    is_vendor = role == UserRole.VENDEDOR.value
    can_register_role = role in _ROLES_REGISTER or relaxed

    reg_failed = sale and (
        effective_registration_status(sale) == REG_STATUS_REGISTRATION_FAILED
        or sale.status == SALE_STATUS_EXPORT_FAILED
    )
    if reg_failed:
        perms.can_edit = (
            role in _ROLES_EDIT_REGISTERED
            or role in _ROLES_REGISTER
            or (is_vendor and sale.created_by_user_id == uid)
            or relaxed
        )
        if can_register_role:
            checklist = build_sale_checklist(db, sale)
            perms.checklist_ready = checklist.ready_to_register
            perms.checklist_block = checklist.register_block_reason
            if checklist.ready_to_register:
                perms.can_register_definitive = True
            else:
                perms.register_reason = checklist.register_block_reason
        else:
            perms.register_reason = "Solo autorización, admin o sistemas puede registrar definitivo."
        if can_register_role and can_retry_registration(sale):
            perms.can_retry_registration = True
        _apply_rbac_sale_overlay(perms, user)
        return perms

    can_edit = True
    if sale and sale.status == SALE_STATUS_REGISTERED:
        can_edit = False
    elif is_vendor and sale and sale.created_by_user_id not in (None, uid) and not relaxed:
        can_edit = False
        perms.edit_reason = "No puedes editar capturas de otro vendedor."

    perms.can_edit = can_edit or relaxed
    perms.can_save_draft = perms.can_edit
    perms.can_submit_validation = perms.can_edit

    if not perms.can_save_draft:
        perms.save_draft_reason = perms.edit_reason or "Acción no permitida."
        perms.submit_validation_reason = perms.save_draft_reason

    if is_vendor and not relaxed:
        perms.register_reason = "Solo autorización, admin o sistemas puede registrar definitivo."

    if not can_register_role:
        perms.register_reason = perms.register_reason or (
            "Solo autorización, admin o sistemas puede registrar definitivo."
        )
        _apply_rbac_sale_overlay(perms, user)
        return perms

    eval_sale = sale
    if form and not sale:
        data, errs = parse_sale_form(form)
        if errs:
            perms.register_reason = "; ".join(errs[:2])
            _apply_rbac_sale_overlay(perms, user)
            return perms

    if form and sale:
        data, errs = parse_sale_form(form)
        if errs:
            perms.register_reason = "; ".join(errs[:2])
            _apply_rbac_sale_overlay(perms, user)
            return perms

    checklist = build_sale_checklist(db, eval_sale)
    perms.checklist_ready = checklist.ready_to_register
    perms.checklist_block = checklist.register_block_reason

    if eval_sale and is_registration_complete(eval_sale):
        perms.register_reason = "La venta ya está registrada."
        if can_register_role and can_retry_registration(eval_sale):
            perms.can_retry_registration = False
        _apply_rbac_sale_overlay(perms, user)
        return perms

    if checklist.ready_to_register:
        wf_ok = True
        wf_reason = None
        if sale and sale.case_id:
            from app.repositories.case_repository import CaseRepository
            from app.services.workflow_dependency_service import (
                build_workflow_context,
                can_action_register_sale,
            )

            case = CaseRepository.get_by_id(db, sale.case_id)
            if case:
                ctx = build_workflow_context(db, case)
                wf_ok, wf_reason = can_action_register_sale(ctx)
        if wf_ok:
            perms.can_register_definitive = True
        else:
            perms.register_reason = wf_reason or "Workflow no permite registro aún."
    else:
        perms.register_reason = checklist.register_block_reason or "Checklist incompleto."

    if sale and can_register_role and can_retry_registration(sale):
        perms.can_retry_registration = True

    _apply_rbac_sale_overlay(perms, user)
    return perms


def explain_blocked_action(action: str, perms: SaleActionPermissions) -> str:
    action = (action or "").strip().lower()
    if action in ("save_draft", "draft"):
        return perms.save_draft_reason or "No puedes guardar borrador."
    if action in ("submit_validation", "validation"):
        return perms.submit_validation_reason or "No puedes enviar a validación."
    if action in ("register", "register_definitive"):
        return perms.register_reason or "No puedes registrar definitivo."
    if action in ("edit",):
        return perms.edit_reason or "No puedes editar."
    if action in ("download", "download_ventas", "download_contratos"):
        return perms.download_reason or "Descarga no disponible."
    return "Acción no disponible."


def assert_action(
    db: Session,
    user: dict[str, Any] | None,
    sale: SaleCapture | None,
    action: str,
    *,
    form: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    perms = get_sale_action_permissions(db, user, sale, form=form)
    action = action.strip().lower()
    if action == "save_draft":
        ok = perms.can_save_draft
        return ok, None if ok else explain_blocked_action(action, perms)
    if action == "submit_validation":
        ok = perms.can_submit_validation
        return ok, None if ok else explain_blocked_action(action, perms)
    if action == "register":
        ok = perms.can_register_definitive
        return ok, None if ok else explain_blocked_action(action, perms)
    if action == "edit":
        ok = perms.can_edit
        return ok, None if ok else explain_blocked_action(action, perms)
    if action in ("download_ventas", "download_contratos"):
        ok = (
            perms.can_download_ventas
            if action == "download_ventas"
            else perms.can_download_contratos
        )
        return ok, None if ok else explain_blocked_action("download", perms)
    if action in ("retry_registration", "retry"):
        ok = perms.can_retry_registration
        return ok, None if ok else (perms.register_reason or "Reintento no disponible.")
    return False, "Acción no reconocida."
