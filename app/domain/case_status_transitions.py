"""Reglas centralizadas de transiciones de estado de casos (validación en CaseService)."""

from __future__ import annotations

import logging

from app.domain import constants as C
from app.models.case import Case

log = logging.getLogger(__name__)

# Transiciones explícitas (pedido) usadas por bot / web. No incluye no-op (mismo estado).
_PEDIDO_EDGES: frozenset[tuple[str, str]] = frozenset(
    {
        (C.ST_PED_PREP_AUT, C.ST_PED_EN_COMPULSA),
        (C.ST_PED_PREP_AUT, C.ST_PED_RECHAZADO),
        (C.ST_PED_PREP_AUT, C.ST_PED_CORRECCION),
        (C.ST_PED_PREP_AUT, C.ST_PED_AUT_GENERADA),
        (C.ST_PED_EN_COMPULSA, C.ST_PED_COMPULSA_OK),
        (C.ST_PED_PEND_COMPULSA, C.ST_PED_COMPULSA_OK),
        (C.ST_PED_EN_COMPULSA, C.ST_PED_PEND_COMPULSA),
        (C.ST_PED_COMPULSA_OK, C.ST_PED_PEND_COMPULSA),
        (C.ST_PED_COMPRA, C.ST_PED_PEND_COMPULSA),
        (C.ST_PED_PEND_COMPULSA, C.ST_PED_EN_COMPULSA),
        (C.ST_PED_COMPULSA_OK, C.ST_PED_EN_COMPULSA),
        (C.ST_PED_COMPRA, C.ST_PED_EN_COMPULSA),
        (C.ST_PED_EN_COMPULSA, C.ST_PED_COMPRA),
        (C.ST_PED_COMPULSA_OK, C.ST_PED_COMPRA),
        (C.ST_PED_PEND_COMPULSA, C.ST_PED_COMPRA),
        (C.ST_PED_EN_COMPULSA, C.ST_PED_RECHAZADO),
        (C.ST_PED_PEND_COMPULSA, C.ST_PED_RECHAZADO),
        (C.ST_PED_COMPULSA_OK, C.ST_PED_RECHAZADO),
        (C.ST_PED_COMPRA, C.ST_PED_RECHAZADO),
    }
)

_REVISION_EDGES: frozenset[tuple[str, str]] = frozenset(
    {
        (C.ST_REV_RECIBIDO, C.ST_REV_LIQUIDEZ),
        (C.ST_REV_RECIBIDO, C.ST_REV_SIN_LIQUIDEZ),
        (C.ST_REV_EN_REVISION, C.ST_REV_LIQUIDEZ),
        (C.ST_REV_EN_REVISION, C.ST_REV_SIN_LIQUIDEZ),
        (C.ST_REV_CORRECCION, C.ST_REV_LIQUIDEZ),
        (C.ST_REV_CORRECCION, C.ST_REV_SIN_LIQUIDEZ),
    }
)


def list_allowed_pedido_transitions() -> list[tuple[str, str]]:
    """Lista ordenada de aristas (estado_origen, estado_destino) permitidas para pedidos."""
    return sorted(_PEDIDO_EDGES, key=lambda p: (p[0], p[1]))


def list_allowed_revision_transitions() -> list[tuple[str, str]]:
    """Lista ordenada de aristas permitidas para revisiones (dictamen con evidencia)."""
    return sorted(_REVISION_EDGES, key=lambda p: (p[0], p[1]))


def list_aut_generada_source_states() -> tuple[str, ...]:
    """Estados desde los que se permite pasar a Autorización generada (cambio real de estado)."""
    return (C.ST_PED_PREP_AUT,)


def validate_case_status_transition(case: Case, old_status: str | None, new_status: str) -> None:
    """
    Verifica que el cambio de estado sea coherente con el tipo de caso y el flujo actual.
    Las transiciones al mismo estado (notas / historial) siempre se permiten.
    """
    if old_status == new_status:
        log.debug(
            "Transición de caso no-op permitida",
            extra={
                "case_id": case.id,
                "case_type": case.case_type,
                "status": new_status,
            },
        )
        return

    if case.case_type == C.CASE_TYPE_REVISION:
        pair = (old_status or "", new_status)
        if pair not in _REVISION_EDGES:
            msg = (
                f"Transición de revisión no permitida: {old_status!r} → {new_status!r}. "
                f"Transiciones válidas: {sorted(_REVISION_EDGES)}"
            )
            log.warning(
                "Transición de revisión rechazada",
                extra={
                    "case_id": case.id,
                    "old_status": old_status,
                    "new_status": new_status,
                },
            )
            raise ValueError(msg)
        log.info(
            "Transición de revisión permitida",
            extra={"case_id": case.id, "old_status": old_status, "new_status": new_status},
        )
        return

    if case.case_type == C.CASE_TYPE_PEDIDO:
        pair = (old_status or "", new_status)
        if pair not in _PEDIDO_EDGES:
            if new_status == C.ST_PED_AUT_GENERADA:
                msg = (
                    f"No se puede marcar «{C.ST_PED_AUT_GENERADA}» desde el estado «{old_status}». "
                    f"Solo se permite desde: {', '.join(list_aut_generada_source_states())}."
                )
            else:
                msg = (
                    f"Transición de pedido no permitida: {old_status!r} → {new_status!r}. "
                    f"Revise el flujo o los datos del caso (id={case.id})."
                )
            log.warning(
                "Transición de pedido rechazada",
                extra={
                    "case_id": case.id,
                    "old_status": old_status,
                    "new_status": new_status,
                },
            )
            raise ValueError(msg)
        if new_status == C.ST_PED_AUT_GENERADA:
            log.info(
                "Transición a autorización generada permitida",
                extra={"case_id": case.id, "old_status": old_status},
            )
        else:
            log.info(
                "Transición de pedido permitida",
                extra={"case_id": case.id, "old_status": old_status, "new_status": new_status},
            )
        return

    msg = f"Tipo de caso no soportado para transiciones: {case.case_type!r}"
    log.warning(msg, extra={"case_id": case.id, "case_type": case.case_type})
    raise ValueError(msg)
