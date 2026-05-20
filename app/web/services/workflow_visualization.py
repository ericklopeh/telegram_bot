"""Visualización del pipeline workflow en web (P22-G)."""

from __future__ import annotations

from typing import Any

from app.services.workflow_dependency_service import (
    WorkflowContext,
    build_workflow_context,
)
from app.services.workflow_state_service import (
    WF_CORRECCION,
    WF_RECHAZADO,
    WORKFLOW_STATE_LABELS,
    WORKFLOW_UI_STEPS,
    normalize_workflow_state,
    workflow_state_index,
)
from sqlalchemy.orm import Session

from app.models.case import Case


def _step_status(
    step_wf_state: str,
    current_index: int,
    *,
    is_error: bool,
    is_blocked: bool,
) -> str:
    idx = workflow_state_index(step_wf_state)
    if is_error and step_wf_state in (WF_CORRECCION, WF_RECHAZADO):
        return "error"
    if idx < 0:
        return "pending"
    if idx < current_index:
        return "completed"
    if idx == current_index:
        return "blocked" if is_blocked else "current"
    return "pending"


def build_workflow_pipeline(
    db: Session,
    case: Case,
    *,
    ctx: WorkflowContext | None = None,
) -> dict[str, Any]:
    ctx = ctx or build_workflow_context(db, case)
    current = normalize_workflow_state(
        getattr(case, "workflow_state", None), legacy_status=case.current_status
    )
    cur_idx = workflow_state_index(current)
    if current in (WF_RECHAZADO, WF_CORRECCION):
        cur_idx = workflow_state_index(
            WF_RECHAZADO if current == WF_RECHAZADO else WF_CORRECCION
        )

    is_error = current in (WF_RECHAZADO, WF_CORRECCION)
    is_blocked = ctx.sharepoint_failed or ctx.has_critical_timeline_error

    steps: list[dict[str, Any]] = []
    for key, label, wf_state in WORKFLOW_UI_STEPS:
        steps.append(
            {
                "key": key,
                "label": label,
                "workflow_state": wf_state,
                "status": _step_status(
                    wf_state,
                    cur_idx if wf_state not in (WF_RECHAZADO, WF_CORRECCION) else cur_idx,
                    is_error=is_error and wf_state == current,
                    is_blocked=is_blocked,
                ),
            }
        )

    return {
        "current_state": current,
        "current_label": WORKFLOW_STATE_LABELS.get(current, current),
        "steps": steps,
    }
