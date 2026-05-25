# P25 — Pruebas manuales SharePoint

## Preparación

1. Completar `.env` con credenciales Graph (ver `docs/P25_SHAREPOINT.md` y `.env.example`).
2. Migrar y reiniciar:

```bash
docker compose exec web alembic upgrade head
docker compose restart web
docker compose exec web pytest -q
```

## 1. Configuración

1. Dejar `MS_TENANT_ID` vacío → `/admin/sharepoint` debe mostrar aviso de variables faltantes.
2. Completar variables → el aviso desaparece.

## 2. Subida desde caso

1. Caso pedido con documento en `/casos/{id}/documentos`.
2. Clic **Subir a SharePoint**.
3. Verificar columna SharePoint: `OK` y enlace si Graph respondió.
4. En timeline del caso: `SHAREPOINT_UPLOAD_STARTED` y `SHAREPOINT_UPLOAD_OK`.

## 3. Fallo y reintento

1. Simular fallo (credencial inválida o archivo inexistente).
2. Estado `UPLOAD_FAILED` y mensaje en `upload_error`.
3. **Reintentar fallidos** o `/casos/{id}/sharepoint/retry`.
4. Tras corregir config/archivo: `SHAREPOINT_OK`.

## 4. Admin

1. `/admin/sharepoint` — listas pendientes, fallidos, OK recientes.
2. **Reintentar todos los fallidos** procesa lote.

## 5. Workflow

1. Caso con docs `VALID` pero sin SharePoint → transición a registro debe bloquearse (mensaje SHAREPOINT).
2. Tras sync OK en docs críticos → desbloqueo según reglas P22.

## 6. Seguridad rutas

1. Confirmar que no se crean archivos en `storage/excel_masters/`.
2. Exports de venta, si se sincronizan, solo desde `storage/excel_exports/`.

## Automatizado

```bash
docker compose exec web pytest -q tests/test_p25_sharepoint.py
```
