# P31 — Checklist E2E operativo

Prueba manual de punta a punta en staging o desarrollo (`docker compose up`). Marque cada paso.

## Pre-requisitos

- [ ] `.env` configurado (sin secretos en git)
- [ ] `storage/excel_masters/` presente
- [ ] `alembic upgrade head`
- [ ] `/health/full` en verde o degradado documentado
- [ ] Usuario web de prueba (admin/sistemas)

## 1. Caso nuevo

- [ ] Crear caso pedido desde web o Telegram
- [ ] Abrir `/casos/{id}` y ver **flujo guiado** con siguiente acción
- [ ] Breadcrumbs: Dashboard → Casos → folio

## 2. Documentos (P24)

- [ ] `/casos/{id}/documentos` — subir pedido, orden, carátula según tipo
- [ ] Validar / rechazar documento
- [ ] Panel guiado actualiza documentos faltantes

## 3. SharePoint (P25)

- [ ] Sync `/casos/{id}/sharepoint/sync` o cola automática
- [ ] Admin `/admin/sharepoint/health` OK o error legible
- [ ] Reintento si `UPLOAD_FAILED`

## 4. Workflow (P22)

- [ ] Pipeline visible en detalle de caso
- [ ] Transición bloqueada muestra mensaje amigable (no traceback)
- [ ] Recalcular estado (admin) si aplica

## 5. Venta y Excel (P19–P20)

- [ ] Captura `/ventas/nueva` vinculada al caso
- [ ] Registro Excel exitoso → `registered`
- [ ] Venta fallida aparece en `/ventas/pendientes` y **Revisión operativa**

## 6. Comisión (P21)

- [ ] Comisión generada tras registro
- [ ] Visible en `/comisiones` y en panel guiado del caso

## 7. ERP (P27)

- [ ] `/erp/dashboard` — KPIs y búsqueda
- [ ] `/clientes/{id}` si hay cliente consolidado
- [ ] `/erp/conciliacion` sin errores críticos inesperados

## 8. BI (P29)

- [ ] `/bi/dashboard` — gráficas y filtros
- [ ] `/bi/alertas` alineado con revisión operativa
- [ ] Export BI en `storage/excel_exports/bi/` (no `excel_masters`)

## 9. Revisión operativa (P31)

- [ ] `/operacion/revision` carga todas las secciones
- [ ] Enlaces **Ver** llevan al recurso correcto
- [ ] Contadores coherentes con dashboard

## 10. DevOps (P30)

- [ ] `GET /health` y `/health/full`
- [ ] `./scripts/backup_db.sh` genera `.sql.gz`
- [ ] Logs en `logs/app.log` con actividad reciente

## 11. Regresión rápida

- [ ] Login / logout
- [ ] Dashboard operativo `/dashboard`
- [ ] No escritura accidental en `excel_masters/`

## Criterio de éxito

Todos los pasos críticos (1–6, 9–10) OK o documentado como bloqueo externo (Graph, masters faltantes).

## Commit sugerido

```
feat(ux): [P31] polish operational flow and guided review
```
