"""
Prueba independiente de subida a SharePoint con Microsoft Graph.

Uso:
  python scripts/test_graph_upload.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.microsoft_graph import GraphUploadError, upload_document_to_sharepoint  # noqa: E402


def main() -> int:
    content_revision = b"Prueba de subida desde bot Telegram - REVISION"
    content_pedido = b"Prueba de subida desde bot Telegram - PEDIDO"
    try:
        revision_result = upload_document_to_sharepoint(
            vendedor="TEST VENDEDOR",
            semana="SEM 18-2026",
            cliente="PABLO",
            folio="TMP-2026-0002",
            tipo_documento="REVISION",
            filename="test_revision.txt",
            file_bytes=content_revision,
        )
        pedido_result = upload_document_to_sharepoint(
            vendedor="TEST VENDEDOR",
            semana="SEM 18-2026",
            cliente="PABLO",
            folio="00001",
            tipo_documento="PEDIDO",
            filename="test_pedido.txt",
            file_bytes=content_pedido,
        )
    except GraphUploadError as exc:
        print("ERROR (GraphUploadError):", str(exc))
        return 1
    except Exception as exc:
        print("ERROR (inesperado):", type(exc).__name__, str(exc))
        return 1

    print("site_id:", revision_result.get("site_id"))
    print("drive_id:", revision_result.get("drive_id"))
    print("")
    print("=== Resultado REVISION ===")
    print("tipo_documento:", "REVISION")
    print("carpeta caso:", revision_result.get("case_folder"))
    print("ruta final:", revision_result.get("folder_path"))
    print("webUrl:", revision_result.get("webUrl"))
    print("")
    print("=== Resultado PEDIDO ===")
    print("tipo_documento:", "PEDIDO")
    print("carpeta caso:", pedido_result.get("case_folder"))
    print("ruta final:", pedido_result.get("folder_path"))
    print("webUrl:", pedido_result.get("webUrl"))
    print("")
    print("resultado completo:")
    print(
        json.dumps(
            {"revision": revision_result, "pedido": pedido_result},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
