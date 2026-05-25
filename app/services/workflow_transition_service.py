"""Transiciones válidas del workflow operativo (P22-B)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.domain import constants as C
from app.models.case import Case
from app.repositories.case_repository import CaseRepository
from app.services.case_event_service import (
    SNTE_UNLOCKED_AFTER_APPROVAL,
    WORKFLOW_DEPENDENCY_MISSING,
    WORKFLOW_TRANSITION_BLOCKED,
    WORKFLOW_TRANSITION_COMPLETED,
    WORKFLOW_TRANSITION_REQUESTED,
    log_event,
)
from app.services.workflow_dependency_service import (
    build_workflow_context,
    check_dependencies_for_state,
    highest_achievable_state,
)
from app.services.workflow_state_service import (
    ALL_WORKFLOW_STATES,
    WF_APROBADO,
    WF_CORRECCION,
    WF_RECHAZADO,
    WF_SNTE_PENDIENTE,
    WORKFLOW_STATE_LABELS,
    legacy_status_for_workflow,
    normalize_workflow_state,
    visible_status_for_workflow,
    workflow_state_index,
)

log = logging.getLogger(__name__)

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "PEDIDO_RECIBIDO": frozenset({"OCR_PROCESADO"}),
    "OCR_PROCESADO": frozenset({"PREP_AUTORIZACION"}),
    "PREP_AUTORIZACION": frozenset({"EN_COMPULSA"}),
    "EN_COMPULSA": frozenset({"APROBADO", "CORRECCION", "RECHAZADO"}),
    "CORRECCION": frozenset({"PREP_AUTORIZACION", "EN_COMPULSA"}),
    "APROBADO": frozenset({"SNTE_PENDIENTE"}),
    "SNTE_PENDIENTE": frozenset({"SNTE_GENERADO"}),
    "SNTE_GENERADO": frozenset({"SHAREPOINT_PENDIENTE"}),
    "SHAREPOINT_PENDIENTE": frozenset({"SHAREPOINT_OK"}),
    "SHAREPOINT_OK": frozenset({"REGISTRO_PENDIENTE"}),
    "REGISTRO_PENDIENTE": frozenset({"REGISTRADO"}),
    "REGISTRADO": frozenset({"CONTRATOS_PENDIENTE"}),
    "CONTRATOS_PENDIENTE": frozenset({"CONTRATOS_OK"}),
    "CONTRATOS_OK": frozenset({"COMISION_PENDIENTE"}),
    "COMISION_PENDIENTE": frozenset({"COMISION_OK"}),
    "COMISION_OK": frozenset({"CERRADO"}),
    "RECHAZADO": frozenset(),
    "CORRECCION": frozenset({"PREP_AUTORIZACION", "EN_COMPULSA"}),
}


class WorkflowTransitionError(Exception):
    pass


def is_transition_allowed(from_state: str, to_state: str) -> bool:
    from_state = normalize_workflow_state(from_state)
    to_state = normalize_workflow_state(to_state)
    if from_state == to_state:
        return True
    allowed = ALLOWED_TRANSITIONS.get(from_state, frozenset())
    return to_state in allowed


def transition_block_message(from_state: str, to_state: str, missing: list[str]) -> str:
    if missing:
        return f"No se puede pasar a {to_state} porque falta {missing[0]}."
    label_from = WORKFLOW_STATE_LABELS.get(from_state, from_state)
    label_to = WORKFLOW_STATE_LABELS.get(to_state, to_state)
    return (
        f"Transición no permitida: {label_from} → {label_to}. "
        "Sigue el orden operativo del flujo."
    )


def _sync_legacy_case_status(case: Case, workflow_state: str) -> None:
    case.workflow_state = workflow_state
    legacy = legacy_status_for_workflow(workflow_state)
    case.current_status = legacy
    case.visible_status = visible_status_for_workflow(workflow_state)


def _log_workflow(
    db: Session,
    case: Case,
    event_type: str,
    message: str,
    user: dict[str, Any] | None,
    *,
    metadata: dict | None = None,
) -> None:
    log_event(
        db,
        case_id=case.id,
        event_type=event_type,
        message=message,
        actor_user_id=(user or {}).get("id"),
        actor_role=(user or {}).get("rol"),
        source="web",
        metadata=metadata,
    )


def request_transition(
    db: Session,
    case_id: int,
    target_state: str,
    user: dict[str, Any] | None,
    *,
    apply: bool = True,
) -> tuple[Case, str | None]:
    """
    Solicita transición. Si apply=True y es válida, persiste en el caso.
    Retorna (case, error_message).
    """
    if target_state not in ALL_WORKFLOW_STATES:
        raise WorkflowTransitionError(f"Estado workflow inválido: {target_state}")

    case = CaseRepository.get_by_id(db, case_id)
    if not case:
        raise WorkflowTransitionError("Caso no encontrado.")
    if case.case_type != C.CASE_TYPE_PEDIDO:
        raise WorkflowTransitionError("Workflow estricto solo aplica a pedidos.")

    ctx = build_workflow_context(db, case)
    current = normalize_workflow_state(
        getattr(case, "workflow_state", None), legacy_status=case.current_status
    )

    _log_workflow(
        db,
        case,
        WORKFLOW_TRANSITION_REQUESTED,
        f"Solicitud: {current} → {target_state}",
        user,
        metadata={"from": current, "to": target_state},
    )

    if current == target_state:
        return case, None

    if not is_transition_allowed(current, target_state):
        msg = transition_block_message(current, target_state, [])
        _log_workflow(
            db,
            case,
            WORKFLOW_TRANSITION_BLOCKED,
            msg,
            user,
            metadata={"from": current, "to": target_state},
        )
        return case, msg

    missing = check_dependencies_for_state(ctx, target_state)
    try:
        from app.services.case_document_service import CaseDocumentService

        doc_missing = CaseDocumentService().missing_for_workflow_target(db, case, target_state)
        if doc_missing:
            from app.domain.constants import doc_type_label

            labels = ", ".join(doc_type_label(dt) for dt in doc_missing)
            doc_msg = (
                f"Documentos obligatorios incompletos o sin validar ({labels}). "
                "Gestione documentos en el caso."
            )
            missing = list(missing) + [doc_msg]
    except Exception:
        log.exception("Error comprobando documentos P24 en transición workflow")

    if missing:
        msg = transition_block_message(current, target_state, missing)
        _log_workflow(
            db,
            case,
            WORKFLOW_TRANSITION_BLOCKED,
            msg,
            user,
            metadata={"from": current, "to": target_state, "missing": missing},
        )
        _log_workflow(
            db,
            case,
            WORKFLOW_DEPENDENCY_MISSING,
            msg,
            user,
            metadata={"missing": missing, "target": target_state},
        )
        return case, msg

    if apply:
        _sync_legacy_case_status(case, target_state)
        CaseRepository.save(db, case)
        _log_workflow(
            db,
            case,
            WORKFLOW_TRANSITION_COMPLETED,
            f"Transición completada: {WORKFLOW_STATE_LABELS.get(current)} → {WORKFLOW_STATE_LABELS.get(target_state)}",
            user,
            metadata={"from": current, "to": target_state},
        )
        if current != WF_APROBADO and target_state == WF_SNTE_PENDIENTE:
            _log_workflow(
                db,
                case,
                SNTE_UNLOCKED_AFTER_APPROVAL,
                "SNTE habilitado tras aprobación y compulsa",
                user,
            )
        try:
            from app.services.platform_cohesion_service import PlatformCohesionService

            actor = user or {}
            PlatformCohesionService().emit(
                db,
                action="workflow_transition",
                title=f"Workflow → {target_state}",
                entity_type="case",
                entity_id=case.id,
                detail=f"{current} → {target_state}",
                actor_user_id=actor.get("id"),
                actor_label=actor.get("nombre") or actor.get("username"),
                source="workflow",
                tone="info",
                href=f"/casos/{case.id}",
                compliance_before={"workflow_state": current},
                compliance_after={"workflow_state": target_state},
                rule_trigger="workflow_transition",
                rule_context={
                    "entity_type": "case",
                    "entity_id": case.id,
                    "from": current,
                    "to": target_state,
                },
                automation_trigger="workflow_approved" if target_state in ("APROBADO", "SNTE_PENDIENTE") else None,
                automation_context={"case_id": case.id, "href": f"/casos/{case.id}"},
            )
        except Exception:
            log.debug("Cohesion emit workflow falló", exc_info=True)

    return case, None


def recalculate_case_workflow_state(
    db: Session,
    case_id: int,
    user: dict[str, Any] | None = None,
    *,
    apply: bool = True,
) -> tuple[Case, str, str | None]:
    """
    Recalcula estado según hechos (OCR, docs, SNTE, SP, venta, comisión).
    Retorna (case, new_state, warning).
    """
    from app.services.case_event_service import WORKFLOW_STATE_RECALCULATED

    case = CaseRepository.get_by_id(db, case_id)
    if not case:
        raise WorkflowTransitionError("Caso no encontrado.")
    if case.case_type != C.CASE_TYPE_PEDIDO:
        raise WorkflowTransitionError("Solo pedidos usan workflow P22.")

    ctx = build_workflow_context(db, case)
    current = normalize_workflow_state(
        getattr(case, "workflow_state", None), legacy_status=case.current_status
    )
    derived = highest_achievable_state(ctx)

    warning = None
    if workflow_state_index(derived) < workflow_state_index(current) and current not in (
        WF_CORRECCION,
        WF_RECHAZADO,
    ):
        warning = (
            f"Estado recalculado retrocede de {WORKFLOW_STATE_LABELS.get(current)} "
            f"a {WORKFLOW_STATE_LABELS.get(derived)} según dependencias actuales."
        )

    if apply:
        _sync_legacy_case_status(case, derived)
        CaseRepository.save(db, case)
        _log_workflow(
            db,
            case,
            WORKFLOW_STATE_RECALCULATED,
            f"Workflow recalculado: {WORKFLOW_STATE_LABELS.get(derived)}",
            user,
            metadata={"previous": current, "derived": derived},
        )

    return case, derived, warning
