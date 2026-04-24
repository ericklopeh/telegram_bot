"""Estados y tipos usados en negocio y persistencia."""

# Tipos de caso
CASE_TYPE_REVISION = "revision"
CASE_TYPE_PEDIDO = "pedido"

# Tipos de pedido (order_type en BD)
ORDER_TYPE_MUEBLE = "mueble"
ORDER_TYPE_PRESTAMO = "prestamo"

TG_MUEBLE = "🛏️ Mueble"
TG_PRESTAMO = "💳 Préstamo"


def order_type_from_telegram_label(text: str) -> str:
    if text == TG_MUEBLE:
        return ORDER_TYPE_MUEBLE
    if text == TG_PRESTAMO:
        return ORDER_TYPE_PRESTAMO
    raise ValueError(f"Tipo de pedido no reconocido: {text!r}")

# Tipos de documento obligatorios (pedido)
DOC_PEDIDO = "pedido"
DOC_ORDEN_DESCUENTO = "orden_descuento"
DOC_CARATULA_BANCARIA = "caratula_bancaria"
DOC_REVISION_EVIDENCIA = "revision_evidencia"
DOC_REVISION_DICTAMEN = "revision_dictamen"

# Estados internos — revisión
ST_REV_RECIBIDO = "Recibido"
ST_REV_EN_REVISION = "En revisión"
ST_REV_CORRECCION = "Corrección solicitada"
ST_REV_LIQUIDEZ = "Liquidez a favor"
ST_REV_SIN_LIQUIDEZ = "Sin liquidez"
ST_REV_RECHAZADO = "Rechazado"
ST_REV_CERRADO = "Cerrado"

# Estados internos — pedido
ST_PED_RECIBIDO = "Recibido"
ST_PED_PREP_AUT = "En preparación de autorización"
ST_PED_CORRECCION = "Corrección solicitada"
ST_PED_APROBADO = "Aprobado en pedido"
ST_PED_EN_COMPULSA = "En compulsa"
ST_PED_PEND_COMPULSA = "Pendiente de compulsa"
ST_PED_COMPULSA_OK = "Compulsa OK"
ST_PED_COMPRA = "Compra realizada"
ST_PED_CERRADO = "Cerrado"
ST_PED_RECHAZADO = "Rechazado"

# Visibles vendedor (mapeo mínimo)
VISIBLE_RECIBIDO = "Recibido"
VISIBLE_EN_REVISION = "En revisión"
VISIBLE_LIQUIDEZ = "Liquidez a favor"
VISIBLE_NO_PROCEDE = "No procede"
VISIBLE_EN_PEDIDO = "En pedido"
VISIBLE_EN_COMPULSA = "En compulsa"
VISIBLE_CERRADO = "Cerrado"


def required_doc_types_for_order(order_type: str) -> list[str]:
    if order_type == ORDER_TYPE_MUEBLE:
        return [DOC_PEDIDO, DOC_ORDEN_DESCUENTO]
    return [DOC_PEDIDO, DOC_ORDEN_DESCUENTO, DOC_CARATULA_BANCARIA]


def doc_type_label(doc_type: str) -> str:
    return {
        DOC_PEDIDO: "Pedido",
        DOC_ORDEN_DESCUENTO: "Orden de descuento",
        DOC_CARATULA_BANCARIA: "Carátula bancaria",
        DOC_REVISION_EVIDENCIA: "Evidencia de revisión",
        DOC_REVISION_DICTAMEN: "Evidencia dictamen revisión",
    }.get(doc_type, doc_type)


def checklist_lines(order_type: str, present: set[str]) -> str:
    lines: list[str] = []
    for dt in required_doc_types_for_order(order_type):
        mark = "✅" if dt in present else "❌"
        lines.append(f"{mark} {doc_type_label(dt)}")
    return "\n".join(lines)


def visible_status_for_pedido(current_status: str) -> str:
    if current_status == ST_PED_RECHAZADO:
        return VISIBLE_NO_PROCEDE
    if current_status in (ST_PED_COMPRA, ST_PED_CERRADO):
        return VISIBLE_CERRADO
    if current_status in (ST_PED_EN_COMPULSA, ST_PED_PEND_COMPULSA, ST_PED_COMPULSA_OK):
        return VISIBLE_EN_COMPULSA
    if current_status == ST_PED_APROBADO:
        return VISIBLE_EN_PEDIDO
    return VISIBLE_EN_PEDIDO


def visible_status_for_revision(current_status: str) -> str:
    if current_status in (ST_REV_RECHAZADO, ST_REV_SIN_LIQUIDEZ):
        return VISIBLE_NO_PROCEDE
    if current_status == ST_REV_LIQUIDEZ:
        return VISIBLE_LIQUIDEZ
    if current_status == ST_REV_CERRADO:
        return VISIBLE_CERRADO
    if current_status == ST_REV_RECIBIDO:
        return VISIBLE_RECIBIDO
    return VISIBLE_EN_REVISION
