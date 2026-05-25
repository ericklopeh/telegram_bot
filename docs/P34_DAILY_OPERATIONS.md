# P34 — Operación diaria segura

## Cada mañana (15 min)

1. Abrir `/admin/beta-readiness` — revisar score y checklist.
2. Abrir `/ops` — atender críticos (SharePoint, exports, imports).
3. Revisar `/ops/incidents` — ack o resolver lo conocido.
4. Verificar último backup en readiness (&lt;48h ideal).
5. `GET /health` o `/health/full` — estado `ok` o `degraded` aceptable para beta.

## Durante el día

| Señal | Acción |
|--------|--------|
| Badge **Modo beta seguro** | Confirmaciones textuales activas (`BETA_SAFE_MODE=true`) |
| Incidencias críticas | Resolver causa; usar recovery en `/ops` |
| Import fallido | `/imports` → preview → confirmar o corregir archivo |
| Export fallido | `/ops` → regenerar export (frase si safe mode) |
| SharePoint fallido | Reintentar por caso o masivo (frase masiva si safe mode) |

## Semanal

- Ejecutar `./scripts/backup_db.sh` y confirmar `.sql.gz` en `backups/`.
- Revisar `docs/P34_BETA_CHECKLIST.md` (muestra de flujos).
- Conciliación: `/control/conciliacion` + `/erp/conciliacion` tras cargas masivas.
- Limpiar incidencias `RESOLVED` obsoletas (opcional).

## Ante un incidente

1. No tocar `storage/excel_masters/`.
2. Registrar en `/ops/incidents` (ack → investigar → resolve).
3. Recovery acotado (un lote, una venta, un caso).
4. Si falla dos veces, escalar y revisar logs en `logs/app.log`.

## Imports históricos

- Solo archivos fuera de masters.
- Flujo: subir → preview (dry-run) → confirmar.
- Rollback de lote: requiere `REVERTIR-LOTE-{id}` con `BETA_SAFE_MODE=true`.

## SharePoint

- Reintentar documentos fallidos antes de cerrar casos.
- Si Graph no configurado: readiness mostrará “degradado” (esperado en staging sin SP).

## Exports Excel

- Salidas solo en `storage/excel_exports/`.
- Regenerar venta vía `/ops` o cola de ventas pendientes.

## Qué NO tocar

- `storage/excel_masters/` (solo lectura).
- Rollback masivo de imports sin confirmación en beta seguro.
- `WEB_RBAC_RELAXED=true` en entornos compartidos.
- Commits de secretos en `.env`.

## Backups

```bash
./scripts/backup_db.sh
```

Restore solo en ventana controlada: ver `docs/P30_BACKUPS.md`.

## Restart seguro

1. Detener web/bot sin matar BD.
2. `alembic upgrade head` si hubo despliegue.
3. Arrancar web — revisar `/admin/beta-readiness`.
4. Smoke: login, `/ops`, un caso de prueba.
