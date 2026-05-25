# P24.1 — Upload legacy alineado con gestión documental

## Objetivo

`POST /casos/{case_id}/upload-document` (formulario en detalle de caso) usa el mismo flujo que P24:

- `CaseDocumentService.upload_document_legacy_web`
- `case_document_storage` → `storage/cases/.../documents/`
- Versionado vía `DocumentRepository.add_version`
- Eventos `CASE_DOCUMENT_UPLOADED` y `CASE_DOCUMENT_REPLACED` (si reemplaza tipo activo)
- Checklist de pedido (`log_pedido_checklist_after_upload`)

## Qué dejó de hacer la ruta legacy

- Ya **no** escribe en `storage/uploads/{case_id}/` con UUID suelto.
- Ya **no** inserta `Document` directamente en la ruta.
- Ya **no** emite solo `DOCUMENT_RECEIVED` (sigue disponible en otros flujos: Telegram, etc.).

## Compatibilidad

| Escenario | Comportamiento |
|-----------|----------------|
| Con `case_id` en URL | Subida completa a `documents` + `storage/cases/` |
| Sin caso en BD | `CaseDocumentService.store_bytes_without_case()` → `storage/uploads/{key}/` sin fila DB (respaldo) |
| Tipos permitidos | `LEGACY_WEB_UPLOAD_TYPES` = tipos P24 + `talon` |
| SharePoint | `upload_status=LOCAL` por defecto; reintento en `/documentos/{id}/reintentar-sharepoint` sin cambios |
| OCR automático | Tras commit, igual que antes (`OCR_ELIGIBLE_DOCUMENT_TYPES`) |

## Riesgos

- Archivos antiguos en `storage/uploads/{case_id}/` no se migran automáticamente; siguen accesibles si `file_path` apunta ahí.
- Reintento SharePoint usa `doc.file_path`; con rutas nuevas bajo `storage/cases/` debe existir el archivo en disco.
- `talon` no está en checklist P24 de workflow; solo se versiona y audita.

## Pruebas

```bash
docker compose exec web pytest -q tests/test_p24_1_legacy_upload.py
docker compose exec web pytest -q
```

## Manual

1. Detalle de caso → subir documento (formulario inferior).
2. Verificar en `/casos/{id}/documentos` que el archivo aparece con versión y ruta bajo `storage/cases/`.
3. Subir el mismo tipo otra vez → versión 2 + evento reemplazo en timeline.
