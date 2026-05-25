# P34 — Checklist salida a beta interna

Marcar cada ítem en staging con datos de prueba. Objetivo: validar P19–P33 sin OCR ni RBAC granular.

## Infraestructura

- [ ] `/admin/beta-readiness` score ≥70, sin errores críticos bloqueantes
- [ ] Migraciones al día (`alembic current` = head)
- [ ] `GET /health` → ok/degraded
- [ ] `GET /ping` → ok
- [ ] Backup &lt;48h en `backups/`
- [ ] Logs escribiendo en `logs/app.log`
- [ ] `BETA_SAFE_MODE=true` en beta interna (confirmaciones activas)

## Caso completo (pedido)

- [ ] Crear caso pedido
- [ ] Subir documentos mínimos (pedido, carátula, etc.)
- [ ] Checklist P24 completo / revalidar desde ops
- [ ] Workflow avanza sin bloqueos inesperados
- [ ] Timeline con eventos coherentes

## SharePoint

- [ ] Subida documento → synced o fallo visible
- [ ] Reintento desde caso o `/ops/retry/sharepoint`
- [ ] Incidencia SP en `/ops/incidents` si falla

## Ventas y Excel

- [ ] Captura venta vinculada a caso
- [ ] Registro Excel en copia bajo `excel_exports/` (no masters)
- [ ] Conciliación ventas sin error grave
- [ ] Regenerar export (`REGENERAR-{id}` si safe mode)

## Comisión

- [ ] Comisión generada post-registro
- [ ] Recalcular desde `/ops/recalculate/commissions` si faltó

## ERP / BI

- [ ] `/erp/dashboard` carga KPIs
- [ ] `/erp/conciliacion` sin críticos sin explicar
- [ ] `/bi/dashboard` carga y export bajo `excel_exports/bi`

## Imports históricos (P32)

- [ ] Subir Excel de prueba (copia, no master)
- [ ] Preview dry-run
- [ ] Confirmar lote pequeño
- [ ] Rollback lote con frase `REVERTIR-LOTE-{id}` (safe mode)

## Recovery (P33)

- [ ] Panel `/ops` con contadores
- [ ] Ack + resolve incidencia
- [ ] Rebuild conciliación
- [ ] Ninguna acción escribe en `excel_masters/`

## Backups y restore

- [ ] `./scripts/backup_db.sh` genera `.sql.gz`
- [ ] Restore en entorno aislado (opcional, ventana controlada)

## Automatizado

```bash
python -m pytest -q tests/test_p34_beta.py
python -m pytest -q
```

## Criterio de salida

- Checklist manual ≥90% en verde
- Sin incidencias `CRITICAL` abiertas >24h
- Operación diaria documentada (`P34_DAILY_OPERATIONS.md`) asignada a responsable
