import logging
from datetime import datetime, timedelta

from telegram.ext import ContextTypes

from app.bot.keyboards import (
    SELLER_MAIN_KEYBOARD,
    keyboard_compulsas,
    keyboard_pedidos,
    order_type_display,
)
from app.config import get_settings
from app.db.session import session_scope
from app.domain import constants as C
from app.models.case import Case
from app.repositories.case_repository import CaseRepository
from app.repositories.user_repository import UserRepository
from app.utils.case_display import (
    format_case_primary_label,
    format_vendor_case_summary,
)

log = logging.getLogger(__name__)

last_compulsa_reminder: dict[str, datetime] = {}
last_sla_alert: dict[str, datetime] = {}


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


async def run_compulsa_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    if not settings.chat_id_compulsas:
        return
    threshold = timedelta(minutes=max(settings.compulsa_reminder_minutes, 1))
    now = datetime.utcnow()
    try:
        with session_scope() as db:
            pending_cases = CaseRepository.get_pendiente_compulsa(db)
            for case in pending_cases:
                last_sent = last_compulsa_reminder.get(case.public_id)
                if last_sent and (now - last_sent) < threshold:
                    continue
                await context.bot.send_message(
                    chat_id=settings.chat_id_compulsas,
                    text=f"⏰ {pending_note(case)}",
                    reply_markup=keyboard_compulsas(case.public_id),
                )
                last_compulsa_reminder[case.public_id] = now
    except Exception:
        log.exception("Error enviando recordatorios de compulsa")


async def run_sla_watchdog_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    interval = timedelta(minutes=max(settings.sla_alert_interval_minutes, 1))
    now = datetime.utcnow()

    sla_rules: list[tuple[str, tuple[str, ...], int]] = [
        ("revision", (C.ST_REV_RECIBIDO, C.ST_REV_EN_REVISION, C.ST_REV_CORRECCION), settings.sla_revision_minutes),
        ("autorizacion", (C.ST_PED_PREP_AUT,), settings.sla_autorizacion_minutes),
        ("compulsa", (C.ST_PED_PEND_COMPULSA,), settings.sla_compulsa_minutes),
    ]
    try:
        with session_scope() as db:
            for stage_name, statuses, minutes in sla_rules:
                cutoff = now - timedelta(minutes=max(minutes, 1))
                overdue_cases = CaseRepository.list_cases_in_status_before(db, statuses, cutoff)
                for case in overdue_cases:
                    key = f"{stage_name}:{case.public_id}"
                    last = last_sla_alert.get(key)
                    if last and (now - last) < interval:
                        continue
                    detail = f"Etapa: {stage_name}. Superó SLA de {minutes} min."
                    await notificar_admin_alertas(context, case, evento="SLA vencido", detalle=detail)
                    last_sla_alert[key] = now
    except Exception:
        log.exception("Error en SLA watchdog")

async def notify_snte_generation_from_web(case_id: int) -> None:
    try:
        from telegram import Bot
        from app.db.session import session_scope
        from app.repositories.case_repository import CaseRepository
        from app.models.user import User, UserRole

        settings = get_settings()
        if not settings.telegram_bot_token:
            log.warning("No telegram_bot_token configurado, ignorando notificación web.")
            return

        bot = Bot(token=settings.telegram_bot_token)

        with session_scope() as db:
            case = CaseRepository.get_by_id(db, case_id)
            if not case:
                log.warning("Caso no encontrado para notificar generación", extra={"case_id": case_id})
                return

            # Notificar Vendedor
            if case.seller_telegram_chat_id:
                try:
                    msg_vendedor = "✅ Tu autorización SNTE fue generada y está en proceso de carga a SharePoint."
                    await bot.send_message(chat_id=case.seller_telegram_chat_id, text=msg_vendedor)
                except Exception:
                    log.exception("Error notificando vendedor desde web", extra={"chat_id": case.seller_telegram_chat_id})
            else:
                log.info("Vendedor sin telegram_chat_id, ignorando notificación", extra={"case_id": case_id})

            # Notificar Admins / Sistemas / Autorizacion
            admin_roles = [UserRole.ADMIN.value, UserRole.SISTEMAS.value, UserRole.AUTORIZACION.value]
            admins = db.query(User).filter(
                User.telegram_id.isnot(None),
                User.is_active.is_(True),
                User.role.in_(admin_roles),
            ).all()

            targets = {a.telegram_id for a in admins if a.telegram_id}
            
            if targets:
                msg_admin = f"📄 Autorización SNTE generada para el folio {case.public_id} - {case.client_name}."
                for target in targets:
                    try:
                        await bot.send_message(chat_id=target, text=msg_admin)
                    except Exception:
                        log.exception("Error notificando admin desde web", extra={"chat_id": target, "case_id": case_id})
            else:
                log.info("No hay admins/sistemas/autorizacion activos para notificar", extra={"case_id": case_id})

    except Exception:
        log.exception("Error general en notify_snte_generation_from_web", extra={"case_id": case_id})
