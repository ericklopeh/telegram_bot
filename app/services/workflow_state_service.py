"""Estados operativos formales del flujo de pedido (P22-A)."""

from __future__ import annotations

from app.domain import constants as C

# Estados workflow P22
WF_PEDIDO_RECIBIDO = "PEDIDO_RECIBIDO"
WF_OCR_PROCESADO = "OCR_PROCESADO"
WF_PREP_AUTORIZACION = "PREP_AUTORIZACION"
WF_EN_COMPULSA = "EN_COMPULSA"
WF_CORRECCION = "CORRECCION"
WF_RECHAZADO = "RECHAZADO"
WF_APROBADO = "APROBADO"
WF_SNTE_PENDIENTE = "SNTE_PENDIENTE"
WF_SNTE_GENERADO = "SNTE_GENERADO"
WF_SHAREPOINT_PENDIENTE = "SHAREPOINT_PENDIENTE"
WF_SHAREPOINT_OK = "SHAREPOINT_OK"
WF_REGISTRO_PENDIENTE = "REGISTRO_PENDIENTE"
WF_REGISTRADO = "REGISTRADO"
WF_CONTRATOS_PENDIENTE = "CONTRATOS_PENDIENTE"
WF_CONTRATOS_OK = "CONTRATOS_OK"
WF_COMISION_PENDIENTE = "COMISION_PENDIENTE"
WF_COMISION_OK = "COMISION_OK"
WF_CERRADO = "CERRADO"

ALL_WORKFLOW_STATES = frozenset(
    {
        WF_PEDIDO_RECIBIDO,
        WF_OCR_PROCESADO,
        WF_PREP_AUTORIZACION,
        WF_EN_COMPULSA,
        WF_CORRECCION,
        WF_RECHAZADO,
        WF_APROBADO,
        WF_SNTE_PENDIENTE,
        WF_SNTE_GENERADO,
        WF_SHAREPOINT_PENDIENTE,
        WF_SHAREPOINT_OK,
        WF_REGISTRO_PENDIENTE,
        WF_REGISTRADO,
        WF_CONTRATOS_PENDIENTE,
        WF_CONTRATOS_OK,
        WF_COMISION_PENDIENTE,
        WF_COMISION_OK,
        WF_CERRADO,
    }
)

# Orden lineal principal (sin CORRECCION/RECHAZADO)
WORKFLOW_LINEAR_ORDER: tuple[str, ...] = (
    WF_PEDIDO_RECIBIDO,
    WF_OCR_PROCESADO,
    WF_PREP_AUTORIZACION,
    WF_EN_COMPULSA,
    WF_APROBADO,
    WF_SNTE_PENDIENTE,
    WF_SNTE_GENERADO,
    WF_SHAREPOINT_PENDIENTE,
    WF_SHAREPOINT_OK,
    WF_REGISTRO_PENDIENTE,
    WF_REGISTRADO,
    WF_CONTRATOS_PENDIENTE,
    WF_CONTRATOS_OK,
    WF_COMISION_PENDIENTE,
    WF_COMISION_OK,
    WF_CERRADO,
)

WORKFLOW_STATE_LABELS: dict[str, str] = {
    WF_PEDIDO_RECIBIDO: "Pedido recibido",
    WF_OCR_PROCESADO: "OCR procesado",
    WF_PREP_AUTORIZACION: "Preparación autorización",
    WF_EN_COMPULSA: "En compulsa",
    WF_CORRECCION: "Corrección",
    WF_RECHAZADO: "Rechazado",
    WF_APROBADO: "Aprobado",
    WF_SNTE_PENDIENTE: "SNTE pendiente",
    WF_SNTE_GENERADO: "SNTE generado",
    WF_SHAREPOINT_PENDIENTE: "SharePoint pendiente",
    WF_SHAREPOINT_OK: "SharePoint OK",
    WF_REGISTRO_PENDIENTE: "Registro venta pendiente",
    WF_REGISTRADO: "Venta registrada",
    WF_CONTRATOS_PENDIENTE: "Contratos pendiente",
    WF_CONTRATOS_OK: "Contratos OK",
    WF_COMISION_PENDIENTE: "Comisión pendiente",
    WF_COMISION_OK: "Comisión OK",
    WF_CERRADO: "Cerrado",
}

# Pasos para visualización P22-G
WORKFLOW_UI_STEPS: tuple[tuple[str, str, str], ...] = (
    ("pedido", "Pedido", WF_PEDIDO_RECIBIDO),
    ("ocr", "OCR", WF_OCR_PROCESADO),
    ("autorizacion", "Autorización", WF_PREP_AUTORIZACION),
    ("compulsa", "Compulsa", WF_EN_COMPULSA),
    ("aprobado", "Aprobado", WF_APROBADO),
    ("snte", "SNTE", WF_SNTE_GENERADO),
    ("sharepoint", "SharePoint", WF_SHAREPOINT_OK),
    ("registro", "Registro", WF_REGISTRADO),
    ("contratos", "Contratos", WF_CONTRATOS_OK),
    ("comisiones", "Comisiones", WF_COMISION_OK),
    ("cerrado", "Cerrado", WF_CERRADO),
)

# Compatibilidad dashboards: mapeo workflow → current_status legacy
WORKFLOW_TO_LEGACY_STATUS: dict[str, str] = {
    WF_PEDIDO_RECIBIDO: C.ST_PED_RECIBIDO,
    WF_OCR_PROCESADO: C.ST_PED_RECIBIDO,
    WF_PREP_AUTORIZACION: C.ST_PED_PREP_AUT,
    WF_EN_COMPULSA: C.ST_PED_EN_COMPULSA,
    WF_CORRECCION: C.ST_PED_CORRECCION,
    WF_RECHAZADO: C.ST_PED_RECHAZADO,
    WF_APROBADO: C.ST_PED_COMPULSA_OK,
    WF_SNTE_PENDIENTE: C.ST_PED_COMPULSA_OK,
    WF_SNTE_GENERADO: C.ST_PED_AUT_GENERADA,
    WF_SHAREPOINT_PENDIENTE: C.ST_PED_AUT_GENERADA,
    WF_SHAREPOINT_OK: C.ST_PED_AUT_GENERADA,
    WF_REGISTRO_PENDIENTE: C.ST_PED_AUT_GENERADA,
    WF_REGISTRADO: C.ST_PED_AUT_GENERADA,
    WF_CONTRATOS_PENDIENTE: C.ST_PED_AUT_GENERADA,
    WF_CONTRATOS_OK: C.ST_PED_AUT_GENERADA,
    WF_COMISION_PENDIENTE: C.ST_PED_AUT_GENERADA,
    WF_COMISION_OK: C.ST_PED_COMPRA,
    WF_CERRADO: C.ST_PED_CERRADO,
}

LEGACY_STATUS_TO_WORKFLOW: dict[str, str] = {
    C.ST_PED_RECIBIDO: WF_PEDIDO_RECIBIDO,
    C.ST_PED_PREP_AUT: WF_PREP_AUTORIZACION,
    C.ST_PED_AUT_GENERADA: WF_SNTE_GENERADO,
    C.ST_PED_CORRECCION: WF_CORRECCION,
    C.ST_PED_APROBADO: WF_APROBADO,
    C.ST_PED_EN_COMPULSA: WF_EN_COMPULSA,
    C.ST_PED_PEND_COMPULSA: WF_EN_COMPULSA,
    C.ST_PED_COMPULSA_OK: WF_APROBADO,
    C.ST_PED_COMPRA: WF_COMISION_OK,
    C.ST_PED_CERRADO: WF_CERRADO,
    C.ST_PED_RECHAZADO: WF_RECHAZADO,
}


def workflow_state_index(state: str) -> int:
    try:
        return WORKFLOW_LINEAR_ORDER.index(state)
    except ValueError:
        return -1


def normalize_workflow_state(state: str | None, *, legacy_status: str | None = None) -> str:
    if state and state in ALL_WORKFLOW_STATES:
        return state
    if legacy_status and legacy_status in LEGACY_STATUS_TO_WORKFLOW:
        return LEGACY_STATUS_TO_WORKFLOW[legacy_status]
    return WF_PEDIDO_RECIBIDO


def legacy_status_for_workflow(workflow_state: str) -> str:
    return WORKFLOW_TO_LEGACY_STATUS.get(workflow_state, C.ST_PED_RECIBIDO)


def visible_status_for_workflow(workflow_state: str) -> str:
    legacy = legacy_status_for_workflow(workflow_state)
    return C.visible_status_for_pedido(legacy)
