from datetime import datetime
from pathlib import Path

from telegram import Update

from app.utils.naming import sanitize_name


async def save_incoming_file(
    update: Update,
    carpeta_destino: Path,
    prefijo: str,
) -> tuple[str, str, str | None, str | None]:
    """
    Descarga documento o foto desde Telegram.
    Retorna: (stored_filename, file_path absoluto, original_filename, mime_type)
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    carpeta_destino.mkdir(parents=True, exist_ok=True)

    if update.message and update.message.document:
        doc = update.message.document
        file_obj = await doc.get_file()
        original_name = doc.file_name if doc.file_name else "archivo"
        original_name = sanitize_name(original_name)
        nombre_final = f"{prefijo} - {timestamp} - {original_name}"
        ruta_final = carpeta_destino / nombre_final
        await file_obj.download_to_drive(custom_path=str(ruta_final))
        mime = doc.mime_type
        return nombre_final, str(ruta_final), original_name, mime

    if update.message and update.message.photo:
        photo = update.message.photo[-1]
        file_obj = await photo.get_file()
        nombre_final = f"{prefijo} - {timestamp}.jpg"
        ruta_final = carpeta_destino / nombre_final
        await file_obj.download_to_drive(custom_path=str(ruta_final))
        return nombre_final, str(ruta_final), nombre_final, "image/jpeg"

    return "", "", None, None
