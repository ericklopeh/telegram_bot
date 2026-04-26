from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup

from app.domain import constants as C
from app.models.case import Case
from app.utils.case_display import format_vendor_button_label

SELLER_MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["📄 Revisión", "🛒 Pedido"],
        ["🔎 Consultar estatus", "📊 Mi estatus"],
        ["📋 Mis ventas de hoy"],
    ],
    resize_keyboard=True,
)

ADMIN_MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🧾 Dictaminar revisión"],
        ["🔎 Consultar estatus"],
    ],
    resize_keyboard=True,
)

# Pruebas: mismo usuario con todas las acciones (vendedor + dictaminar + consultar)
COMBINED_MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🧾 Dictaminar revisión"],
        ["📄 Revisión", "🛒 Pedido"],
        ["🔎 Consultar estatus", "📊 Mi estatus"],
        ["📋 Mis ventas de hoy"],
    ],
    resize_keyboard=True,
)

# Compatibilidad con imports antiguos
MAIN_KEYBOARD = COMBINED_MAIN_KEYBOARD

TIPO_PEDIDO_KEYBOARD = ReplyKeyboardMarkup(
    [
        [C.TG_MUEBLE, C.TG_PRESTAMO],
        ["⬅️ Volver al menú"],
    ],
    resize_keyboard=True,
)


def status_recent_cases_keyboard(cases: list[Case]) -> InlineKeyboardMarkup | None:
    """Vendedor: nombre en primer plano + fecha/hora corta (callback sigue usando public_id)."""
    if not cases:
        return None
    rows: list[list[InlineKeyboardButton]] = []
    for c in cases:
        emoji = "🛒" if c.case_type == C.CASE_TYPE_PEDIDO else "📄"
        label = f"{emoji} {format_vendor_button_label(c)}"
        if len(label) > 64:
            label = label[:63] + "…"
        rows.append([InlineKeyboardButton(label, callback_data=f"st|{c.public_id}")])
    return InlineKeyboardMarkup(rows)


def dictamen_revision_keyboard(cases: list[Case]) -> InlineKeyboardMarkup | None:
    """Admin: revisiones pendientes con estado visual y vendedor."""
    if not cases:
        return None

    def _short_seller(name: str | None) -> str:
        raw = (name or "").strip()
        if not raw:
            return "Sin vendedor"
        parts = [p for p in raw.split() if p]
        if len(parts) == 1:
            return parts[0]
        return f"{parts[0]} {parts[-1][:1]}."

    rows: list[list[InlineKeyboardButton]] = []
    for c in cases:
        if c.current_status in (C.ST_REV_RECIBIDO, C.ST_REV_EN_REVISION, C.ST_REV_CORRECCION):
            status_icon = "🟡"
        else:
            status_icon = "🟢"
        label = f"{status_icon} C: {c.client_name} · V: {_short_seller(c.seller_name)}"
        if len(label) > 64:
            label = label[:63] + "…"
        rows.append([InlineKeyboardButton(label, callback_data=f"rd|{c.public_id}")])
    return InlineKeyboardMarkup(rows)


def pedido_document_keyboard(order_type: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("📎 Pedido", callback_data="pd|p"),
            InlineKeyboardButton("📎 Orden descuento", callback_data="pd|o"),
        ],
    ]
    if order_type == C.ORDER_TYPE_PRESTAMO:
        rows.append([InlineKeyboardButton("📎 Carátula bancaria", callback_data="pd|c")])
    rows.append(
        [
            InlineKeyboardButton("📋 Ver checklist", callback_data="pd|v"),
            InlineKeyboardButton("✅ Enviar pedido", callback_data="pd|f"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def pedido_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Confirmar envío", callback_data="pd|cf|si"),
                InlineKeyboardButton("↩️ Seguir editando", callback_data="pd|cf|no"),
            ]
        ]
    )


def revision_resolution_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Liquidez a favor", callback_data="rv|liq"),
                InlineKeyboardButton("❌ Sin liquidez", callback_data="rv|sin"),
            ]
        ]
    )


def keyboard_pedidos(case_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Aprobar", callback_data=f"ped_aprobar|{case_id}"),
                InlineKeyboardButton("❌ Rechazar", callback_data=f"ped_rechazar|{case_id}"),
            ],
            [
                InlineKeyboardButton(
                    "🟡 Pedir corrección", callback_data=f"ped_corregir|{case_id}"
                )
            ],
        ]
    )


def keyboard_compulsas(case_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Compulsa OK", callback_data=f"com_ok|{case_id}"),
                InlineKeyboardButton("⚠️ Pendiente", callback_data=f"com_pendiente|{case_id}"),
            ],
            [
                InlineKeyboardButton("❌ No procede", callback_data=f"com_noprocede|{case_id}"),
                InlineKeyboardButton("📦 Compra realizada", callback_data=f"com_compra|{case_id}"),
            ],
            [
                InlineKeyboardButton("✏️ Editar compulsa", callback_data=f"com_editar|{case_id}"),
            ],
        ]
    )


def order_type_display(order_type: str | None) -> str:
    if order_type == C.ORDER_TYPE_MUEBLE:
        return C.TG_MUEBLE
    if order_type == C.ORDER_TYPE_PRESTAMO:
        return C.TG_PRESTAMO
    return order_type or "—"
