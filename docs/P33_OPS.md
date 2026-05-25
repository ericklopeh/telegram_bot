# P33 — Operación real, observabilidad y recovery

## Objetivo

Preparar el sistema para operación interna diaria: detectar fallos, inconsistencias y ofrecer acciones de recuperación seguras sin tocar `storage/excel_masters/`.

## Componentes

| Módulo | Rol |
|--------|-----|
| `app/services/ops_monitor_service.py` | Escaneo de hallazgos + sincronización a `ops_incidents` |
| `app/services/ops_recovery_service.py` | Acciones de recovery idempotentes con auditoría en log e incidencias |
| `app/models/ops_incident.py` | Persistencia de incidencias |
| `app/web/routes/ops.py` | Panel y endpoints POST de recovery |

## Qué monitorea

- Imports fallidos (`import_batches.status = failed`)
- Exports / registro Excel fallido (`sale_captures`)
- SharePoint fallido (`documents.upload_status = UPLOAD_FAILED`)
- Ventas sin comisión (registradas sin fila en `commissions`)
- Ventas sin ruta de export
- Casos atorados >24h (reutiliza P31)
- Workflow bloqueado / documentos faltantes o inválidos
- Conciliación crítica (ERP + comercial + alertas BI)
- Rutas `storage/` requeridas ausentes
- Errores recientes en timeline (`case_events`)

## Rutas

| Método | Ruta |
|--------|------|
| GET | `/ops` |
| GET | `/ops/incidents` |
| POST | `/ops/incidents/{id}/ack` |
| POST | `/ops/incidents/{id}/resolve` |
| POST | `/ops/retry/sharepoint` |
| POST | `/ops/rebuild/conciliation` |
| POST | `/ops/recalculate/commissions` |
| POST | `/ops/regenerate/export/{sale_capture_id}` |
| POST | `/ops/revalidate/checklist/{case_id}` |
| POST | `/ops/retry/import/{batch_id}` |

## Recovery — cuándo usar cada botón

| Acción | Cuándo |
|--------|--------|
| Reintentar SharePoint | Documentos en `UPLOAD_FAILED`; opcional `case_id` / `document_id` en formulario |
| Recalcular conciliación | Tras cambios masivos ERP/ventas; refresca reportes sin escribir masters |
| Recalcular comisiones | Ventas registradas sin comisión |
| Regenerar export venta | `registration_failed` o export ausente; escribe solo bajo `excel_exports/` |
| Revalidar checklist | Caso con documentos faltantes/inválidos en workflow |
| Reintentar import | Lote en `failed` / `uploaded` → ejecuta preview de nuevo |

## Logging (P33)

`app/core/logging_setup.py`:

- `correlation_id` (alias de request id en HTTP)
- `log_ops_action()` — `entity_type`, `entity_id`, `action`, `result`, `elapsed_ms`

Formato ampliado en `config/logging.yaml` para archivo `logs/app.log`.

## Migración

`migrations/versions/k7l8m9n0o1p2_p33_ops_incidents.py`

## Permisos

Panel y recovery: roles `admin` y `sistemas` (sin RBAC granular P28).

## Riesgos

- Auto-resolución de incidencias cuando el hallazgo desaparece (`system:auto_clear`)
- Recalcular comisiones no modifica comisiones ya pagadas/canceladas
- Regenerar export reejecuta registro Excel (copias en exports, no masters)
- El panel ejecuta sync de incidencias en cada visita a `/ops` (carga DB moderada)

## Checklist operativo diario

1. Abrir `/ops` y revisar badges crítico/advertencia
2. Atender incidencias abiertas en `/ops/incidents`
3. SharePoint fallidos → reintentar
4. Exports fallidos → regenerar por venta o cola pendientes
5. Conciliación → recalcular si hubo import ERP o ventas masivas
6. Casos SLA → revisión en `/operacion/revision`
