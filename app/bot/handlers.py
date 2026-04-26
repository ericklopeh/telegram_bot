import logging
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.bot.keyboards import (
    COMBINED_MAIN_KEYBOARD,
    SELLER_MAIN_KEYBOARD,
    TIPO_PEDIDO_KEYBOARD,
    dictamen_revision_keyboard,
    keyboard_compulsas,
    keyboard_pedidos,
    order_type_display,
    pedido_confirm_keyboard,
    pedido_document_keyboard,
    revision_resolution_keyboard,
    status_recent_cases_keyboard,
)
from app.config import get_settings
from app.db.session import session_scope
from app.domain import constants as C
from app.domain.constants import checklist_lines, doc_type_label
from app.models.case import Case
from app.repositories.case_repository import CaseRepository
from app.repositories.document_repository import DocumentRepository
from app.services.case_service import CaseService
from app.services.microsoft_graph import upload_document_to_sharepoint
from app.services.sharepoint_retry_queue import (
    enqueue_failed_upload,
    list_retry_items,
    remove_retry_item,
    update_retry_item,
)
from app.services.telegram_file_service import save_incoming_file
from app.utils.case_display import (
    format_case_primary_label,
    format_vendor_case_summary,
)
from app.utils.naming import sanitize_name

log = logging.getLogger(__name__)

user_sessions: dict[int, dict] = {}
last_compulsa_reminder: dict[str, datetime] = {}
last_sla_alert: dict[str, datetime] = {}


def _case_service() -> CaseService:
    return CaseService(get_settings())


async def _upload_document_background(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    document_id: int,
    file_path: str,
    vendedor: str,
    semana: str,
    cliente: str,
    folio: str,
    tipo_documento: str,
    filename: str,
) -> None:
    try:
        file_bytes = Path(file_path).read_bytes()
        result = upload_document_to_sharepoint(
            vendedor=vendedor,
            semana=semana,
            cliente=cliente,
            folio=folio,
            tipo_documento=tipo_documento,
            filename=filename,
            file_bytes=file_bytes,
        )
        with session_scope() as db:
            DocumentRepository.set_upload_uploaded(db, document_id, result.get("webUrl"))
        log.info(
            "Documento subido a SharePoint",
            extra={
                "document_id": document_id,
                "vendedor": vendedor,
                "folio": folio,
                "cliente": cliente,
                "tipo_documento": tipo_documento,
                "ruta_final": result.get("folder_path"),
                "webUrl": result.get("webUrl"),
            },
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Archivo guardado correctamente ✅\\n"
                "Tu documento ya fue registrado."
            ),
            reply_markup=SELLER_MAIN_KEYBOARD,
        )
    except Exception as exc:
        with session_scope() as db:
            DocumentRepository.set_upload_failed(db, document_id, str(exc))
        enqueue_failed_upload(
            file_path=file_path,
            vendedor=vendedor,
            semana=semana,
            cliente=cliente,
            folio=folio,
            tipo_documento=tipo_documento,
            filename=filename,
            document_id=document_id,
            error=str(exc),
        )
        log.exception(
            "Error subiendo documento a SharePoint en background",
            extra={
                "document_id": document_id,
                "vendedor": vendedor,
                "folio": folio,
                "cliente": cliente,
                "tipo_documento": tipo_documento,
                "filename": filename,
            },
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "No se pudo subir el archivo a SharePoint por ahora. "
                "Se reintentará automáticamente."
            ),
            reply_markup=SELLER_MAIN_KEYBOARD,
        )


def _is_admin(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False
    admins = get_settings().admin_user_ids_set
    return True if not admins else user.id in admins


def _is_seller(update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False
    sellers = get_settings().seller_user_ids_set
    return True if not sellers else user.id in sellers


def _main_keyboard_for(update: Update) -> ReplyKeyboardMarkup:
    """Teclado completo para pruebas (dictaminar + vendedor)."""
    return COMBINED_MAIN_KEYBOARD


def _status_block_for_list_item(case: Case, is_admin: bool) -> str:
    if is_admin:
        return (
            f"• {format_case_primary_label(case)}\n"
            f"  Visible: {case.visible_status} | Interno: {case.current_status}"
        )
    summary = format_vendor_case_summary(case)
    return "• " + summary.replace("\n", "\n  ")


def _status_single_message(case: Case, is_admin: bool) -> str:
    if is_admin:
        return (
            f"{format_case_primary_label(case)}\n"
            f"Visible: {case.visible_status} | Interno: {case.current_status}"
        )
    return format_vendor_case_summary(case)


def _actor_name(update: Update) -> str | None:
    user = update.effective_user
    if not user:
        return None
    return user.username or user.full_name


def _parse_hhmm(value: str, fallback: time) -> time:
    try:
        hour_str, minute_str = value.strip().split(":", 1)
        hour = int(hour_str)
        minute = int(minute_str)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return time(hour, minute)
    except Exception:
        pass
    return fallback


def _is_business_hours() -> bool:
    settings = get_settings()
    if not settings.business_hours_enabled:
        return True
    now_local = datetime.now(ZoneInfo(settings.display_timezone))
    if now_local.weekday() > 4:
        return False
    current = now_local.time().replace(second=0, microsecond=0)
    start = _parse_hhmm(settings.business_hours_start, time(9, 0))
    end = _parse_hhmm(settings.business_hours_end, time(18, 30))
    return start <= current <= end


async def _enforce_business_hours(update: Update) -> bool:
    if _is_admin(update):
        return True
    if _is_business_hours():
        return True
    settings = get_settings()
    msg = (
        "⏰ El bot está habilitado de lunes a viernes, "
        f"de {settings.business_hours_start} a {settings.business_hours_end} "
        f"({settings.display_timezone})."
    )
    if update.effective_message:
        await update.effective_message.reply_text(msg, reply_markup=_main_keyboard_for(update))
    return False


def _pending_note(case: Case) -> str:
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
    settings = get_settings()
    targets: set[int] = set(settings.admin_user_ids_set)
    if settings.chat_id_admin_alerts:
        targets.add(settings.chat_id_admin_alerts)
    if not targets:
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


async def compulsa_reminder_job(context: ContextTypes.DEFAULT_TYPE) -> None:
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
                    text=f"⏰ {_pending_note(case)}",
                    reply_markup=keyboard_compulsas(case.public_id),
                )
                last_compulsa_reminder[case.public_id] = now
    except Exception:
        log.exception("Error enviando recordatorios de compulsa")


async def sharepoint_retry_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    settings = get_settings()
    max_attempts = max(settings.sharepoint_retry_max_attempts, 1)
    items = list_retry_items()
    if not items:
        return
    for item in items:
        try:
            file_path = Path(item.file_path)
            if not file_path.exists():
                update_retry_item(item.id, attempts=item.attempts + 1, last_error="Archivo local no existe")
                if item.attempts + 1 >= max_attempts:
                    remove_retry_item(item.id)
                continue
            file_bytes = file_path.read_bytes()
            result = upload_document_to_sharepoint(
                vendedor=item.vendedor,
                semana=item.semana,
                cliente=item.cliente,
                folio=item.folio,
                tipo_documento=item.tipo_documento,
                filename=item.filename,
                file_bytes=file_bytes,
            )
            if item.document_id:
                with session_scope() as db:
                    DocumentRepository.set_upload_uploaded(db, item.document_id, result.get("webUrl"))
            log.info(
                "Retry SharePoint exitoso",
                extra={
                    "item_id": item.id,
                    "document_id": item.document_id,
                    "vendedor": item.vendedor,
                    "folio": item.folio,
                    "cliente": item.cliente,
                    "tipo_documento": item.tipo_documento,
                    "ruta_final": result.get("folder_path"),
                    "webUrl": result.get("webUrl"),
                },
            )
            remove_retry_item(item.id)
        except Exception as exc:
            attempts = item.attempts + 1
            if item.document_id:
                with session_scope() as db:
                    DocumentRepository.set_upload_failed(db, item.document_id, str(exc))
            update_retry_item(item.id, attempts=attempts, last_error=str(exc))
            if attempts >= max_attempts:
                remove_retry_item(item.id)
            log.exception(
                "Retry SharePoint falló",
                extra={
                    "item_id": item.id,
                    "document_id": item.document_id,
                    "attempts": attempts,
                    "max_attempts": max_attempts,
                    "vendedor": item.vendedor,
                    "folio": item.folio,
                    "cliente": item.cliente,
                    "tipo_documento": item.tipo_documento,
                },
            )


async def sla_watchdog_job(context: ContextTypes.DEFAULT_TYPE) -> None:
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _enforce_business_hours(update):
        return
    if update.effective_chat:
        user_sessions[update.effective_chat.id] = {}
    await update.message.reply_text(
        "Hola. Selecciona una opción:",
        reply_markup=_main_keyboard_for(update),
    )


async def _resolve_group_reason(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session: dict,
    reason_text: str,
) -> bool:
    status = session.get("pending_status")
    case_public_id = session.get("pending_case_id")
    if not status or not case_public_id:
        return False
    try:
        with session_scope() as db:
            case = CaseRepository.get_by_public_id(db, case_public_id)
            if not case:
                await update.message.reply_text("Caso no encontrado.", reply_markup=_main_keyboard_for(update))
                session.clear()
                return True
            svc = _case_service()
            svc.transition_case_status(
                db,
                case,
                status,
                notes=reason_text,
                action_user=_actor_name(update),
            )
            db.refresh(case)
        await update.message.reply_text(
            f"✅ Estado actualizado.\n{format_case_primary_label(case)}\n"
            f"Estado: {case.current_status}",
            reply_markup=keyboard_compulsas(case.public_id) if case.current_status in (
                C.ST_PED_EN_COMPULSA,
                C.ST_PED_PEND_COMPULSA,
                C.ST_PED_COMPULSA_OK,
                C.ST_PED_COMPRA,
                C.ST_PED_RECHAZADO,
            ) else _main_keyboard_for(update),
        )
        await notificar_vendedor_estado(context, case, detalle=reason_text)
    except Exception:
        log.exception("Error aplicando motivo")
        await update.message.reply_text(
            "No se pudo actualizar el caso.",
            reply_markup=_main_keyboard_for(update),
        )
    session.clear()
    return True


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _enforce_business_hours(update):
        return
    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    if chat_id not in user_sessions:
        user_sessions[chat_id] = {}

    session = user_sessions[chat_id]
    state = session.get("state")

    is_admin = _is_admin(update)
    is_seller = _is_seller(update)

    if state == "waiting_group_reason":
        if not is_admin:
            await update.message.reply_text("No tienes permisos para esta acción.", reply_markup=_main_keyboard_for(update))
            session.clear()
            return
        await _resolve_group_reason(update, context, session, text)
        return

    if text == "📄 Revisión":
        if not is_seller:
            await update.message.reply_text("Esta opción es solo para vendedores.", reply_markup=_main_keyboard_for(update))
            return
        session.clear()
        session["flow"] = "revision"
        session["state"] = "waiting_revision_name"
        await update.message.reply_text("Escribe el nombre del cliente para la revisión.")
        return

    if text == "🛒 Pedido":
        if not is_seller:
            await update.message.reply_text("Esta opción es solo para vendedores.", reply_markup=_main_keyboard_for(update))
            return
        session.clear()
        session["flow"] = "pedido"
        session["state"] = "waiting_pedido_name"
        await update.message.reply_text("Escribe el nombre del cliente para el pedido.")
        return

    if text == "🧾 Dictaminar revisión":
        if not is_admin:
            await update.message.reply_text(
                "No tienes permisos para dictaminar revisiones.",
                reply_markup=_main_keyboard_for(update),
            )
            return
        session.clear()
        session["state"] = "waiting_revision_resolution_pick"
        try:
            with session_scope() as db:
                revs = CaseRepository.list_pending_revisions(db, limit=20)
        except Exception:
            log.exception("Error cargando revisiones recientes")
            revs = []
        kb = dictamen_revision_keyboard(revs)
        if kb is None:
            await update.message.reply_text(
                "No hay revisiones pendientes por dictaminar.",
                reply_markup=_main_keyboard_for(update),
            )
        else:
            await update.message.reply_text(
                "Elige la revisión pendiente de la lista:",
                reply_markup=kb,
            )
        return

    if text == "📊 Mi estatus":
        if not is_seller:
            await update.message.reply_text("Esta opción es solo para vendedores.", reply_markup=_main_keyboard_for(update))
            return
        try:
            with session_scope() as db:
                summary = CaseRepository.seller_visible_status_summary(db, chat_id)
                today_cases = CaseRepository.list_seller_pedidos_of_day(db, chat_id, date.today(), limit=500)
        except Exception:
            log.exception("Error consultando resumen vendedor")
            await update.message.reply_text("No se pudo obtener el resumen.", reply_markup=_main_keyboard_for(update))
            return
        lines = [
            "📊 Resumen vendedor",
            f"Ventas de hoy: {len(today_cases)}",
            "",
        ]
        if summary:
            for status, count in sorted(summary.items(), key=lambda t: t[0]):
                lines.append(f"• {status}: {count}")
        else:
            lines.append("Sin casos registrados.")
        await update.message.reply_text("\n".join(lines), reply_markup=_main_keyboard_for(update))
        return

    if text == "📋 Mis ventas de hoy":
        if not is_seller:
            await update.message.reply_text("Esta opción es solo para vendedores.", reply_markup=_main_keyboard_for(update))
            return
        try:
            with session_scope() as db:
                rows = CaseRepository.list_seller_pedidos_of_day(db, chat_id, date.today(), limit=50)
        except Exception:
            log.exception("Error listando ventas del día")
            await update.message.reply_text("No se pudieron cargar tus ventas de hoy.", reply_markup=_main_keyboard_for(update))
            return
        if not rows:
            await update.message.reply_text("Hoy no tienes ventas registradas.", reply_markup=_main_keyboard_for(update))
            return
        lines = ["📋 Mis ventas de hoy"]
        for c in rows:
            lines.append(f"• {c.client_name} — {c.visible_status}")
        await update.message.reply_text("\n".join(lines), reply_markup=_main_keyboard_for(update))
        return

    if text == "🔎 Consultar estatus":
        session.clear()
        session["state"] = "waiting_status_query"
        help_text = (
            "🔎 Consultar estatus\n\n"
            "Toca un caso reciente en los botones o escribe:\n"
            "• parte del nombre del cliente, o\n"
            "• un folio (PED-…, REVTMP-…).\n\n"
            "Cada caso se muestra como: Nombre — dd/mm/aaaa hh:mm (fecha de registro)."
        )
        try:
            with session_scope() as db:
                if is_admin:
                    recent = CaseRepository.list_recent_cases_global(db, limit=10)
                else:
                    recent = CaseRepository.list_seller_cases_recent(db, chat_id, limit=10)
        except Exception:
            log.exception("Error cargando casos recientes")
            recent = []
        kb = status_recent_cases_keyboard(recent) if recent else None
        await update.message.reply_text(help_text, reply_markup=kb)
        if not recent:
            hint = (
                "Aún no hay casos recientes en el sistema. Escribe un nombre o folio para buscar."
                if is_admin
                else "Aún no tienes casos recientes. Escribe un nombre o folio para buscar."
            )
            await update.message.reply_text(hint, reply_markup=_main_keyboard_for(update))
        return

    if text == "⬅️ Volver al menú":
        session.clear()
        await update.message.reply_text(
            "Volviste al menú principal.",
            reply_markup=_main_keyboard_for(update),
        )
        return

    if state == "waiting_status_query":
        q = sanitize_name(text)
        try:
            with session_scope() as db:
                if is_admin:
                    rows = CaseRepository.search_global(db, q)
                else:
                    rows = CaseRepository.search_for_seller(db, chat_id, q)
        except Exception:
            log.exception("Error consultando estatus")
            await update.message.reply_text(
                "No se pudo consultar la base de datos. Revisa conexión y migraciones.",
                reply_markup=_main_keyboard_for(update),
            )
            session.clear()
            return
        if not rows:
            await update.message.reply_text("Sin resultados para tu búsqueda.", reply_markup=_main_keyboard_for(update))
        else:
            lines = [_status_block_for_list_item(c, is_admin) for c in rows]
            await update.message.reply_text("\n\n".join(lines), reply_markup=_main_keyboard_for(update))
        session.clear()
        return

    if state == "waiting_revision_name":
        session["cliente"] = sanitize_name(text)
        session["state"] = "waiting_revision_file"
        await update.message.reply_text(
            f"Cliente guardado: {session['cliente']}\n"
            "Ahora adjunta la imagen o archivo de la revisión."
        )
        return

    if state == "waiting_pedido_name":
        session["cliente"] = sanitize_name(text)
        session["state"] = "waiting_pedido_type"
        await update.message.reply_text(
            f"Cliente guardado: {session['cliente']}\nAhora selecciona el tipo de pedido:",
            reply_markup=TIPO_PEDIDO_KEYBOARD,
        )
        return

    if state == "waiting_pedido_type":
        if text not in (C.TG_MUEBLE, C.TG_PRESTAMO):
            await update.message.reply_text(
                "Selecciona un tipo válido usando los botones.",
                reply_markup=TIPO_PEDIDO_KEYBOARD,
            )
            return
        try:
            session["order_type"] = C.order_type_from_telegram_label(text)
        except ValueError:
            await update.message.reply_text("Tipo no válido.", reply_markup=TIPO_PEDIDO_KEYBOARD)
            return
        session["state"] = "waiting_pedido_pick_doc"
        session["case_public_id"] = None
        session["pending_doc_type"] = None
        checklist = checklist_lines(session["order_type"], set())
        await update.message.reply_text(
            "Elige qué documento vas a adjuntar (puedes reemplazar uno ya cargado).\n\n"
            f"Checklist:\n{checklist}",
            reply_markup=pedido_document_keyboard(session["order_type"]),
        )
        return

    await update.message.reply_text(
        "Usa los botones del menú para iniciar una opción.",
        reply_markup=_main_keyboard_for(update),
    )


async def handle_files(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _enforce_business_hours(update):
        return
    chat_id = update.effective_chat.id

    if chat_id not in user_sessions:
        await update.message.reply_text(
            "Primero selecciona una opción del menú.",
            reply_markup=_main_keyboard_for(update),
        )
        return

    session = user_sessions[chat_id]
    state = session.get("state")

    if state == "waiting_revision_file":
        cliente = session.get("cliente", "SIN NOMBRE")
        seller = _actor_name(update)
        try:
            with session_scope() as db:
                folio = CaseRepository.next_revision_temp_folio(db)
            svc = _case_service()
            _root, evidencias = svc.ensure_revision_directories(folio, cliente)
            nombre, path_str, orig, mime = await save_incoming_file(
                update,
                evidencias,
                prefijo=f"{folio} {cliente} - REVISION",
            )
            if not nombre:
                await update.message.reply_text(
                    "No se recibió un archivo válido (documento o foto).",
                    reply_markup=_main_keyboard_for(update),
                )
                return
            with session_scope() as db:
                case = svc.create_revision_case(
                    db,
                    client_name=cliente,
                    seller_chat_id=chat_id,
                    seller_name=seller,
                    stored_filename=nombre,
                    file_abs_path=path_str,
                    original_filename=orig,
                    mime_type=mime,
                    folio=folio,
                )
                document = DocumentRepository.get_active_document(db, case.id, C.DOC_REVISION_EVIDENCIA)
                document_id = document.id if document else None
                if document_id:
                    DocumentRepository.set_upload_pending(db, document_id)
        except Exception:
            log.exception("Error persistiendo revisión")
            await update.message.reply_text(
                "Error al guardar la revisión en la base de datos.",
                reply_markup=_main_keyboard_for(update),
            )
            session.clear()
            return

        if not document_id:
            await update.message.reply_text(
                "Archivo recibido, pero no se pudo preparar la subida a SharePoint.",
                reply_markup=_main_keyboard_for(update),
            )
            session.clear()
            return

        await update.message.reply_text(
            "Archivo recibido ✅ Se está subiendo a SharePoint...",
            reply_markup=_main_keyboard_for(update),
        )
        context.application.create_task(
            _upload_document_background(
                context,
                chat_id,
                document_id,
                path_str,
                seller or "SIN VENDEDOR",
                get_settings().effective_semana_activa,
                cliente,
                folio,
                "REVISION",
                nombre,
            )
        )
        await notificar_admin_alertas(
            context,
            case,
            evento="Nueva revisión registrada",
        )
        session.clear()
        return

    if state == "waiting_revision_resolution_file":
        public_id = session.get("revision_case_public_id")
        target_status = session.get("revision_target_status")
        if not public_id or not target_status:
            await update.message.reply_text("No hay dictamen pendiente.", reply_markup=_main_keyboard_for(update))
            session.clear()
            return
        try:
            with session_scope() as db:
                case = CaseRepository.get_by_public_id(db, public_id)
                if not case:
                    await update.message.reply_text("Caso no encontrado.", reply_markup=_main_keyboard_for(update))
                    session.clear()
                    return
                revision_path = Path(case.folder_path) / "REVISION"
                nombre, path_str, orig, mime = await save_incoming_file(
                    update,
                    revision_path,
                    prefijo=f"{case.public_id} {case.client_name} - DICTAMEN",
                )
                if not nombre:
                    await update.message.reply_text("No se recibió imagen válida.", reply_markup=_main_keyboard_for(update))
                    return
                svc = _case_service()
                svc.register_pedido_document(
                    db,
                    case,
                    C.DOC_REVISION_DICTAMEN,
                    nombre,
                    path_str,
                    orig,
                    mime,
                )
                svc.transition_case_status(
                    db,
                    case,
                    target_status,
                    notes="Dictamen con evidencia adjunta",
                    action_user=_actor_name(update),
                )
                db.refresh(case)
            await update.message.reply_text(
                f"✅ Dictamen guardado.\n{format_case_primary_label(case)}\n"
                f"Estado: {case.current_status}",
                reply_markup=_main_keyboard_for(update),
            )
            await notificar_vendedor_estado(context, case, detalle="Revisión dictaminada con evidencia")
        except Exception:
            log.exception("Error guardando dictamen de revisión")
            await update.message.reply_text("Error al guardar dictamen.", reply_markup=_main_keyboard_for(update))
        session.clear()
        return

    if state == "waiting_pedido_file":
        doc_type = session.get("pending_doc_type")
        cliente = session.get("cliente", "SIN NOMBRE")
        order_type = session.get("order_type")
        public_id = session.get("case_public_id")
        if not doc_type or not order_type or not public_id:
            await update.message.reply_text(
                "Primero elige el tipo de documento con los botones.",
                reply_markup=_main_keyboard_for(update),
            )
            return
        seller = _actor_name(update)
        try:
            with session_scope() as db:
                case = CaseRepository.get_by_public_id(db, public_id)
                if not case:
                    await update.message.reply_text("Caso no encontrado. Reinicia el pedido.", reply_markup=_main_keyboard_for(update))
                    session.clear()
                    return
                svc = _case_service()
                evidencias = Path(case.folder_path) / "EVIDENCIAS"
                tipo_limpio = "MUEBLE" if case.order_type == C.ORDER_TYPE_MUEBLE else "PRESTAMO"
                prefijo = f"{case.official_folio} {cliente} - {tipo_limpio} - {doc_type_label(doc_type)}"
                nombre, path_str, orig, mime = await save_incoming_file(
                    update,
                    evidencias,
                    prefijo=prefijo,
                )
                if not nombre:
                    await update.message.reply_text(
                        "No se recibió un archivo válido (documento o foto).",
                    )
                    return
                document = svc.register_pedido_document(
                    db,
                    case,
                    doc_type,
                    nombre,
                    path_str,
                    orig,
                    mime,
                )
                document_id = document.id
                DocumentRepository.set_upload_pending(db, document_id)
                svc.transition_case_status(
                    db,
                    case,
                    case.current_status,
                    notes=f"Documento reemplazado/cargado: {doc_type_label(doc_type)}",
                    action_user=seller,
                )
                db.refresh(case)
                present = DocumentRepository.get_active_types_for_case(db, case.id)
                vendedor = case.seller_name or seller or "SIN VENDEDOR"
                semana = case.week_code
                cliente_case = case.client_name
                folio = case.official_folio or case.public_id
        except Exception:
            log.exception("Error guardando documento de pedido")
            await update.message.reply_text(
                "Error al guardar el archivo.",
                reply_markup=_main_keyboard_for(update),
            )
            session.clear()
            return

        await update.message.reply_text(
            "Archivo recibido ✅ Se está subiendo a SharePoint...",
            reply_markup=_main_keyboard_for(update),
        )
        context.application.create_task(
            _upload_document_background(
                context,
                chat_id,
                document_id,
                path_str,
                vendedor,
                semana,
                cliente_case,
                folio,
                "PEDIDO",
                nombre,
            )
        )

        session["pending_doc_type"] = None
        session["state"] = "waiting_pedido_pick_doc"
        present_set = present if isinstance(present, set) else set(present)
        checklist = checklist_lines(order_type, present_set)
        await update.message.reply_text(
            f"Documento guardado: {doc_type_label(doc_type)}\n\nChecklist:\n{checklist}",
            reply_markup=pedido_document_keyboard(order_type),
        )
        return

    await update.message.reply_text(
        "No estaba esperando archivos en este momento. Usa el menú principal.",
        reply_markup=_main_keyboard_for(update),
    )


async def handle_revision_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not _is_admin(update):
        await query.answer("No tienes permisos.", show_alert=True)
        return
    chat_id = update.effective_chat.id
    data = query.data or ""
    if not data.startswith("rv|"):
        return
    if chat_id not in user_sessions:
        user_sessions[chat_id] = {}
    session = user_sessions[chat_id]
    if session.get("state") != "waiting_revision_resolution_choice":
        await query.answer("Flujo de revisión no activo.", show_alert=True)
        return
    action = data.split("|", 1)[1]
    if action == "liq":
        session["revision_target_status"] = C.ST_REV_LIQUIDEZ
    elif action == "sin":
        session["revision_target_status"] = C.ST_REV_SIN_LIQUIDEZ
    else:
        await query.answer()
        return
    session["state"] = "waiting_revision_resolution_file"
    await query.edit_message_text("Adjunta ahora la imagen del Excel como evidencia del dictamen.")
    await query.answer()


async def _finalize_pedido(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    session: dict,
) -> None:
    try:
        with session_scope() as db:
            case = CaseRepository.get_by_public_id(db, session["case_public_id"])
            if not case:
                await update.effective_message.reply_text("Caso no encontrado.", reply_markup=_main_keyboard_for(update))
                session.clear()
                return
            svc = _case_service()
            if not svc.pedido_has_all_documents(db, case):
                present = DocumentRepository.get_active_types_for_case(db, case.id)
                checklist = checklist_lines(case.order_type or "", present)
                await update.effective_message.reply_text(
                    f"Aún no se puede enviar. Completa:\n{checklist}",
                    reply_markup=pedido_document_keyboard(case.order_type or session.get("order_type", "")),
                )
                return
            svc.finalize_pedido(db, case)
            db.refresh(case)
        await notificar_grupo_pedidos(context, case)
        await notificar_admin_alertas(context, case, evento="Pedido enviado a autorización")
        await update.effective_message.reply_text(
            "✅ Pedido enviado al grupo.\n\n"
            f"{format_vendor_case_summary(case)}\n"
            f"Tipo: {order_type_display(case.order_type)}\n"
            f"Semana: {get_settings().effective_semana_activa}",
            reply_markup=_main_keyboard_for(update),
        )
        await notificar_vendedor_estado(context, case, detalle="Pedido enviado a autorización")
    except Exception:
        log.exception("Error finalizando pedido")
        await update.effective_message.reply_text("Error al finalizar pedido.", reply_markup=_main_keyboard_for(update))
    session.clear()


async def handle_pedido_doc_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not _is_seller(update):
        await query.answer("No tienes permisos.", show_alert=True)
        return
    chat_id = update.effective_chat.id
    data = query.data or ""
    if not data.startswith("pd|"):
        return

    if chat_id not in user_sessions:
        await query.answer("Sesión expirada.", show_alert=True)
        try:
            await query.edit_message_text("Sesión expirada. Usa el menú de nuevo.")
        except Exception:
            pass
        return

    session = user_sessions[chat_id]
    parts = data.split("|")
    if len(parts) < 2:
        await query.answer()
        return
    action = parts[1]
    order_type = session.get("order_type")
    cliente = session.get("cliente", "SIN NOMBRE")
    seller = _actor_name(update)

    doc_map = {"p": C.DOC_PEDIDO, "o": C.DOC_ORDEN_DESCUENTO, "c": C.DOC_CARATULA_BANCARIA}

    if action in doc_map:
        doc_type = doc_map[action]
        if doc_type == C.DOC_CARATULA_BANCARIA and order_type != C.ORDER_TYPE_PRESTAMO:
            await query.answer("Carátula solo aplica a préstamo.", show_alert=True)
            return
        try:
            with session_scope() as db:
                svc = _case_service()
                if not session.get("case_public_id"):
                    case = svc.create_pedido_case_skeleton(
                        db,
                        client_name=cliente,
                        order_type=order_type,
                        seller_chat_id=chat_id,
                        seller_name=seller,
                    )
                    session["case_public_id"] = case.public_id
                session["pending_doc_type"] = doc_type
                session["state"] = "waiting_pedido_file"
        except Exception:
            log.exception("Error creando caso de pedido")
            await query.answer("Error de base de datos.", show_alert=True)
            return
        await query.edit_message_text(f"Adjunta ahora el archivo: {doc_type_label(doc_type)}")
        await query.answer()
        return

    if action == "v":
        if not session.get("case_public_id"):
            await query.answer("Aún no hay documentos cargados.", show_alert=True)
            return
        try:
            with session_scope() as db:
                case = CaseRepository.get_by_public_id(db, session["case_public_id"])
                if not case or not case.order_type:
                    present = set()
                else:
                    present = DocumentRepository.get_active_types_for_case(db, case.id)
        except Exception:
            log.exception("Error leyendo checklist")
            await query.answer("Error al leer checklist.", show_alert=True)
            return
        checklist = checklist_lines(order_type, present)
        await query.message.reply_text(f"Checklist actual:\n{checklist}")
        await query.answer()
        return

    if action == "f":
        if not session.get("case_public_id"):
            await query.answer("Primero carga los documentos.", show_alert=True)
            return
        try:
            with session_scope() as db:
                case = CaseRepository.get_by_public_id(db, session["case_public_id"])
                if not case:
                    await query.answer("Caso no encontrado.", show_alert=True)
                    session.clear()
                    return
                present = DocumentRepository.get_active_types_for_case(db, case.id)
                checklist = checklist_lines(case.order_type or "", present)
        except Exception:
            log.exception("Error validando checklist")
            await query.answer("Error validando documentos.", show_alert=True)
            return
        await query.message.reply_text(
            "Confirma envío del pedido:\n"
            f"{format_case_primary_label(case)}\n"
            f"Checklist:\n{checklist}",
            reply_markup=pedido_confirm_keyboard(),
        )
        await query.answer()
        return

    if action == "cf" and len(parts) >= 3:
        if parts[2] == "no":
            session["state"] = "waiting_pedido_pick_doc"
            await query.edit_message_text("Puedes seguir cargando o reemplazando documentos.")
            await query.message.reply_text(
                "Flujo de pedido activo.",
                reply_markup=pedido_document_keyboard(session.get("order_type", "")),
            )
            await query.answer()
            return
        if parts[2] == "si":
            await query.answer()
            await _finalize_pedido(update, context, session)
            return

    await query.answer()


async def handle_group_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not _is_admin(update):
        await query.answer("No tienes permisos.", show_alert=True)
        return
    await query.answer()
    data = query.data or ""
    if "|" not in data:
        return
    action, case_id = data.split("|", 1)
    actor = _actor_name(update)

    reason_required = {
        "ped_rechazar": C.ST_PED_RECHAZADO,
        "ped_corregir": C.ST_PED_CORRECCION,
        "com_noprocede": C.ST_PED_RECHAZADO,
    }
    if action in reason_required:
        session = user_sessions.setdefault(update.effective_chat.id, {})
        session["state"] = "waiting_group_reason"
        session["pending_case_id"] = case_id
        session["pending_status"] = reason_required[action]
        await query.message.reply_text(
            "Escribe el motivo para esta acción (obligatorio):",
            reply_markup=_main_keyboard_for(update),
        )
        return

    action_map = {
        "ped_aprobar": (C.ST_PED_EN_COMPULSA, "Aprobado en pedidos"),
        "com_ok": (C.ST_PED_COMPULSA_OK, "Compulsa OK"),
        "com_pendiente": (C.ST_PED_PEND_COMPULSA, "Pendiente de compulsa"),
        "com_compra": (C.ST_PED_COMPRA, "Compra realizada"),
        "com_editar": (C.ST_PED_EN_COMPULSA, "Compulsa reabierta para edición"),
    }
    if action not in action_map:
        return

    new_status, note = action_map[action]
    try:
        with session_scope() as db:
            case = CaseRepository.get_by_public_id(db, case_id)
            if not case:
                await query.edit_message_text("Caso no encontrado en la base de datos.")
                return
            svc = _case_service()
            svc.transition_case_status(
                db,
                case,
                new_status,
                notes=note,
                action_user=actor,
            )
            db.refresh(case)
        msg = (
            f"✅ ACTUALIZADO\n\n"
            f"{format_case_primary_label(case)}\n"
            f"Tipo: {order_type_display(case.order_type)}\n"
            f"Semana: {case.week_code}\n"
            f"Estado: {case.current_status}"
        )
        if action.startswith("com_"):
            await query.edit_message_text(msg, reply_markup=keyboard_compulsas(case.public_id))
        else:
            await query.edit_message_text(msg)
        if action == "ped_aprobar":
            await notificar_grupo_compulsas(context, case)
        await notificar_vendedor_estado(context, case, detalle=note)
    except Exception:
        log.exception("Error en callback de grupo")
        await query.edit_message_text("Error al actualizar el caso.")


async def handle_dictamen_revision_pick_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("rd|"):
        return
    if not _is_admin(update):
        await query.answer("Sin permiso.", show_alert=True)
        return
    public_id = query.data.split("|", 1)[1]
    chat_id = update.effective_chat.id
    session = user_sessions.setdefault(chat_id, {})
    if session.get("state") != "waiting_revision_resolution_pick":
        await query.answer("Abre primero «Dictaminar revisión» en el menú.", show_alert=True)
        return
    try:
        with session_scope() as db:
            case = CaseRepository.get_by_public_id(db, public_id)
    except Exception:
        log.exception("Error en callback rd|")
        await query.answer("Error al consultar.", show_alert=True)
        return
    if not case or case.case_type != C.CASE_TYPE_REVISION:
        await query.answer("Revisión no válida.", show_alert=True)
        return
    session["revision_case_public_id"] = public_id
    session["state"] = "waiting_revision_resolution_choice"
    await query.answer()
    await query.message.reply_text(
        "Selecciona el dictamen de revisión:",
        reply_markup=revision_resolution_keyboard(),
    )


async def handle_status_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query.data or not query.data.startswith("st|"):
        return
    public_id = query.data.split("|", 1)[1]
    chat_id = update.effective_chat.id
    is_admin = _is_admin(update)
    try:
        with session_scope() as db:
            case = CaseRepository.get_by_public_id(db, public_id)
            if not case:
                await query.answer("Caso no encontrado.", show_alert=True)
                return
            if not is_admin and case.seller_telegram_chat_id != chat_id:
                await query.answer("Caso no encontrado o no es tuyo.", show_alert=True)
                return
    except Exception:
        log.exception("Error en callback de estatus st|")
        await query.answer("Error al consultar.", show_alert=True)
        return
    await query.answer()
    text = f"🔎 Estatus\n\n{_status_single_message(case, is_admin)}"
    await query.message.reply_text(text, reply_markup=_main_keyboard_for(update))


async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return
    if not await _enforce_business_hours(update):
        await query.answer("Fuera de horario.", show_alert=True)
        return
    if query.data.startswith("st|"):
        await handle_status_pick_callback(update, context)
        return
    if query.data.startswith("rd|"):
        await handle_dictamen_revision_pick_callback(update, context)
        return
    if query.data.startswith("pd|"):
        await handle_pedido_doc_callback(update, context)
        return
    if query.data.startswith("rv|"):
        await handle_revision_callback(update, context)
        return
    if query.data.startswith("ped_") or query.data.startswith("com_"):
        await handle_group_callbacks(update, context)
        return
    await query.answer()


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("Error no manejado en el bot", exc_info=context.error)
