import logging

from telegram.ext import ContextTypes

from app.bot.keyboards import (
    SELLER_MAIN_KEYBOARD,
    keyboard_compulsas,
    keyboard_pedidos,
    order_type_display,
)
from app.config import get_settings
from app.db.session import session_scope
from app.models.case import Case
from app.repositories.user_repository import UserRepository
from app.utils.case_display import (
    format_case_primary_label,
    format_vendor_case_summary,
)

log = logging.getLogger(__name__)


def pending_note(case: Case) -> str:
    return (
        f"Recordatorio de compulsa pendiente.\n"
        f"{format_case_primary_label(case)}\n"
        f"Tipo: {order_type_display(case.order_type)}\n"
        f"Estado: {case.current_status}"
    )


async def notificar_grupo_pedidos(
    context: ContextTypes.DEFAULT_TYPE,
    case: Case,
) -> None:
    settings = get_settings()
    if not settings.chat_id_pedidos:
        return
    mensaje = (
        "📥 NUEVO PEDIDO\n\n"
        f"{format_case_primary_label(case)}\n"
        f"Tipo: {order_type_display(case.order_type)}\n"
        f"Semana: {settings.effective_semana_activa}\n"
        f"Estado: {case.current_status}"
    )
    await context.bot.send_message(
        chat_id=settings.chat_id_pedidos,
        text=mensaje,
        reply_markup=keyboard_pedidos(case.public_id),
    )


async def notificar_grupo_compulsas(
    context: ContextTypes.DEFAULT_TYPE,
    case: Case,
) -> None:
    settings = get_settings()
    if not settings.chat_id_compulsas:
        return
    mensaje = (
        "📤 PEDIDO EN COMPULSA\n\n"
        f"{format_case_primary_label(case)}\n"
        f"Tipo: {order_type_display(case.order_type)}\n"
        f"Semana: {settings.effective_semana_activa}\n"
        f"Estado: En compulsa"
    )
    await context.bot.send_message(
        chat_id=settings.chat_id_compulsas,
        text=mensaje,
        reply_markup=keyboard_compulsas(case.public_id),
    )


async def notificar_vendedor_estado(
    context: ContextTypes.DEFAULT_TYPE,
    case: Case,
    detalle: str | None = None,
) -> None:
    if not case.seller_telegram_chat_id:
        return
    msg = "🔔 Actualización de estatus\n\n" + format_vendor_case_summary(case)
    if detalle:
        msg = f"{msg}\n\nNota: {detalle}"
    await context.bot.send_message(
        chat_id=case.seller_telegram_chat_id,
        text=msg,
        reply_markup=SELLER_MAIN_KEYBOARD,
    )


async def notificar_admin_alertas(
    context: ContextTypes.DEFAULT_TYPE,
    case: Case,
    evento: str,
    detalle: str | None = None,
) -> None:
    try:
        with session_scope() as db:
            admins = UserRepository.list_active_admins_with_telegram_id(db)
            targets: set[int] = {admin.telegram_id for admin in admins if admin.telegram_id is not None}
    except Exception:
        log.exception("Error consultando admins activos para alerta", extra={"public_id": case.public_id})
        return

    if not targets:
        log.warning("Alerta admin sin admins configurados", extra={"public_id": case.public_id, "evento": evento})
        return

    mensaje = (
        f"🚨 {evento}\n\n"
        f"{format_case_primary_label(case)}\n"
        f"Tipo: {order_type_display(case.order_type)}\n"
        f"Folio: {case.public_id}\n"
        f"Vendedor: {case.seller_name or 'Sin vendedor'}\n"
        f"Estado: {case.current_status}"
    )
    if detalle:
        mensaje = f"{mensaje}\nDetalle: {detalle}"

    for target in targets:
        try:
            await context.bot.send_message(chat_id=target, text=mensaje)
        except Exception:
            log.exception("Error enviando alerta admin", extra={"chat_id": target, "public_id": case.public_id})
