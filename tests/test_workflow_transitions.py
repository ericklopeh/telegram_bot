"""Pruebas transiciones workflow P22."""

import pytest

from app.services.workflow_state_service import (
    WF_APROBADO,
    WF_PEDIDO_RECIBIDO,
    WF_REGISTRADO,
    WF_SNTE_PENDIENTE,
    WF_SNTE_GENERADO,
)
from app.services.workflow_transition_service import (
    is_transition_allowed,
    transition_block_message,
)


def test_cannot_jump_to_registrado_from_pedido_recibido():
    assert not is_transition_allowed(WF_PEDIDO_RECIBIDO, WF_REGISTRADO)


def test_aprobado_enables_snte_pendiente():
    assert is_transition_allowed(WF_APROBADO, WF_SNTE_PENDIENTE)


def test_snte_pendiente_to_generado():
    assert is_transition_allowed(WF_SNTE_PENDIENTE, WF_SNTE_GENERADO)


def test_cannot_generate_snte_from_prep_path_via_transition():
    assert not is_transition_allowed(WF_PEDIDO_RECIBIDO, WF_SNTE_GENERADO)


def test_blocked_message_includes_missing():
    msg = transition_block_message(WF_PEDIDO_RECIBIDO, WF_REGISTRADO, ["SHAREPOINT_OK"])
    assert "REGISTRADO" in msg
    assert "SHAREPOINT_OK" in msg
