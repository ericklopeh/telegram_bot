# P25.1 — Checklist staging Microsoft Graph

## Variables `.env` obligatorias

```env
MS_TENANT_ID=
MS_CLIENT_ID=
MS_CLIENT_SECRET=
MS_SITE_HOSTNAME=mgaman.sharepoint.com
MS_SITE_PATH=/sites/miunidad
MS_DRIVE_NAME=01_MIGRACION/gdrive
# o bien IDs directos:
MS_SITE_ID=
MS_DRIVE_ID=
MS_ROOT_FOLDER=Mi unidad/Lingry Nuevo Leon/PEDIDOS
```

Opcionales P25.1:

```env
MS_GRAPH_MAX_RETRIES=5
MS_GRAPH_RETRY_BASE_SECONDS=1.0
MS_GRAPH_UPLOAD_CHUNK_BYTES=3276800
MS_GRAPH_REQUEST_TIMEOUT=30
MS_GRAPH_UPLOAD_TIMEOUT=120
MS_GRAPH_SMALL_FILE_MAX_BYTES=4194304
```

Nunca commitear `MS_CLIENT_SECRET`.

## Permisos Entra ID (aplicación)

1. Registro de aplicación → **API permissions**.
2. Microsoft Graph → **Application permissions**:
   - `Sites.ReadWrite.All` (recomendado para carpetas en sitio)
   - y/o `Files.ReadWrite.All`
3. **Grant admin consent** en el tenant.
4. Crear **Client secret** y copiar el valor a `.env` (solo una vez visible).

## Arranque

```bash
docker compose exec web alembic upgrade head
docker compose restart web
docker compose exec web pytest -q
```

## 1. Health check

1. Login como admin/sistemas.
2. Abrir `/admin/sharepoint/health`.
3. Esperado:
   - Estado global **OK** (verde).
   - Token OAuth ✓, site/drive IDs visibles.
   - MS_ROOT_FOLDER legible y escritura de prueba ✓.
4. Si falla: leer errores en pantalla (401 → credenciales; 403 → permisos; 404 → root/drive incorrecto).

## 2. PDF pequeño (&lt; 4 MB)

1. Caso pedido con documento local en `/casos/{id}/documentos`.
2. **Subir a SharePoint**.
3. Columna SharePoint: badge **OK** + enlace “SharePoint”.
4. Timeline: `SHAREPOINT_UPLOAD_STARTED`, `SHAREPOINT_UPLOAD_OK`.
5. Abrir enlace: archivo visible en ruta  
   `{MS_ROOT_FOLDER}/{year}/SEM_{week}/{vendedor}/FOLIO_{folio}_{cliente}/documents/`.

## 3. PDF grande (&gt; 4 MB)

1. Subir PDF &gt; 4 MB al caso (mismo flujo P24).
2. **Subir a SharePoint** (usa sesión por fragmentos).
3. Verificar en logs (contenedor `web`): `graph_upload_ok` con `elapsed_ms` y `size_bytes`.
4. Confirmar `SHAREPOINT_OK` y enlace válido.

## 4. Provocar `UPLOAD_FAILED`

1. Quitar temporalmente `MS_CLIENT_SECRET` o poner site/drive incorrecto.
2. Intentar sync → estado **Error**, `upload_error` con mensaje sanitizado (sin secretos).
3. Timeline: `SHAREPOINT_UPLOAD_FAILED`.
4. Restaurar `.env` correcto.

## 5. Reintento

1. Con documento en `UPLOAD_FAILED`, clic **Reintentar fallidos** o `/casos/{id}/sharepoint/retry`.
2. Timeline: `SHAREPOINT_RETRY_REQUESTED`.
3. Tras corregir Graph: `SHAREPOINT_OK`.

## 6. Workflow

1. Docs críticos en `VALID` pero sin SharePoint → bloqueo hacia registro (P22).
2. Tras sync OK en todos los críticos → transición permitida según reglas existentes.

## 7. Admin panel

- `/admin/sharepoint`: pendientes / fallidos / OK.
- `/admin/sharepoint/retry-failed`: lote global.

## Screenshots esperados (staging)

| Pantalla | Qué capturar |
|----------|----------------|
| Health | Estado OK + site/drive + root folder |
| Documentos | Columna SharePoint verde + URL |
| Timeline | Eventos SHAREPOINT_* |
| Admin fallidos | Lista con `upload_error` legible |

## Logs (sin secretos)

Buscar en logs del servicio `web`:

- `graph_upload_ok` / `graph_upload_failed`
- Campos: `document_id`, `case_id`, `graph_request_id`, `upload_attempt`, `elapsed_ms`, `error_code`

No debe aparecer `client_secret`, `access_token` ni JWT en texto plano.
