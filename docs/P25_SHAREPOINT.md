# P25 — SharePoint / OneDrive vía Microsoft Graph

## Resumen

Sincronización real de documentos de caso (P24) y exports Excel hacia SharePoint usando **client credentials**. El archivo local en `storage/cases/` es la fuente; si Graph falla, el documento queda en `UPLOAD_FAILED` y se puede reintentar.

## Variables `.env`

| Variable | Uso |
|----------|-----|
| `MS_TENANT_ID` | Azure AD tenant |
| `MS_CLIENT_ID` | App registration |
| `MS_CLIENT_SECRET` | Secret (nunca en repo) |
| `MS_SITE_ID` o `MS_SITE_HOSTNAME` + `MS_SITE_PATH` | Sitio SharePoint |
| `MS_DRIVE_ID` o `MS_DRIVE_NAME` | Biblioteca / drive |
| `MS_ROOT_FOLDER` | Carpeta raíz bajo el drive |

Opcionales: `SHAREPOINT_RETRY_INTERVAL_MINUTES`, `SHAREPOINT_RETRY_MAX_ATTEMPTS` (cola legacy del bot).

## Permisos Graph (aplicación)

- `Sites.ReadWrite.All` o permisos de Files.ReadWrite en el sitio/drive usado
- Admin consent en el tenant

## Árbol remoto (alineado P24)

```
{MS_ROOT_FOLDER}/
  {year}/
    SEM_{week}/
      {vendedor}/
        FOLIO_{folio}_{cliente}/
          documents/
            {archivos versionados}
          excel_exports/   (opcional, exports de venta)
```

Equivale a `storage/cases/{year}/SEM_{week}/.../documents/`.

## Estados en `documents.upload_status`

| Estado | Significado |
|--------|-------------|
| `LOCAL` | Solo disco local (subida P24) |
| `PENDING_UPLOAD` | Pendiente de Graph |
| `UPLOADING` | Subida en curso |
| `SHAREPOINT_OK` | Sincronizado (éxito P25) |
| `UPLOADED` | Alias legacy (tratado como OK en workflow) |
| `UPLOAD_FAILED` | Error; ver `upload_error` |

Campos adicionales: `sharepoint_drive_id`, `sharepoint_item_id`, `sharepoint_web_url`, `sharepoint_folder_path`.

## Servicios

| Módulo | Rol |
|--------|-----|
| `sharepoint_graph_client.py` | Token, carpetas, upload simple/sesión, retries |
| `sharepoint_sync_service.py` | `sync_document`, `sync_case_documents`, retries, admin buckets |
| `microsoft_graph.py` | API legacy (bot); convive con cliente P25 |
| `sharepoint_document_service.py` | Fachada background → `SharePointSyncService` |

## Rutas web

| Método | Ruta |
|--------|------|
| POST | `/casos/{id}/sharepoint/sync` |
| POST | `/casos/{id}/sharepoint/retry` |
| GET | `/admin/sharepoint` |
| POST | `/admin/sharepoint/retry-failed` |

Vista documentos: botones **Subir a SharePoint** y **Reintentar fallidos**.

## Workflow P22

Para documentos críticos, el registro final exige `SHAREPOINT_OK` o `UPLOADED` (`is_sharepoint_synced()`). Si Graph falla, el caso puede seguir en local y reintentar.

## Eventos timeline

- `SHAREPOINT_UPLOAD_STARTED`
- `SHAREPOINT_UPLOAD_OK`
- `SHAREPOINT_UPLOAD_FAILED`
- `SHAREPOINT_RETRY_REQUESTED`

## Migración

Revisión Alembic: `h4i5j6k7l8m9` (campos SharePoint en `documents`).

```bash
docker compose exec web alembic upgrade head
docker compose restart web
```

## Restricciones

- No escribir en `storage/excel_masters/`
- Exports de venta solo desde rutas bajo `storage/excel_exports/`
