# P32 — Importación e histórico desde Excel

## Objetivo

Importar información histórica desde archivos Excel (Ventas 2026 y Relación de contratos) hacia el ERP consolidado, sin modificar los maestros originales en `storage/excel_masters/`.

## Flujo seguro

1. **Subir** (`POST /imports/upload`) — archivo en `storage/imports/{batch_id}_{nombre}.xlsx`
2. **Vista previa** (`GET /imports/{id}/preview`) — dry-run: validación, duplicados, errores por fila; **no escribe ventas ERP**
3. **Confirmar** (`POST /imports/{id}/confirm`) — crea `ErpCustomer`, `ErpSale`, `Contract` y `ImportedSaleReference`
4. **Revertir** (`POST /imports/{id}/rollback`) — rollback lógico: desactiva referencias y elimina ventas/contratos creados por el lote (si no tienen pagos)

## Rutas

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/imports` | Listado y formulario de subida |
| POST | `/imports/upload` | Subir archivo |
| GET | `/imports/{batch_id}/preview` | Vista previa / dry-run |
| POST | `/imports/{batch_id}/confirm` | Confirmar importación |
| GET | `/imports/{batch_id}/errors` | Errores por fila |
| GET | `/imports/{batch_id}/errors?download=xlsx` | Exportar errores |

## Modelos

- `ImportBatch` — lote, estado, contadores, `preview_json`, `audit_trail`
- `ImportRowError` — error por fila
- `ImportedSaleReference` — trazabilidad y rollback

## Eventos de auditoría (JSON en lote)

- `IMPORT_UPLOADED`
- `IMPORT_PREVIEWED`
- `IMPORT_CONFIRMED`
- `IMPORT_FAILED`
- `IMPORT_ROLLED_BACK`

## Servicios

- `app/services/excel_import_service.py` — orquestación
- `app/services/commercial_report_service.py` — `read_ventas_rows_raw`, `read_contratos_rows_raw`

## Exportación de errores

`storage/excel_exports/imports/import_errors_{batch_id}.xlsx`

## Migración

`migrations/versions/j6k7l8m9n0o1_p32_excel_imports.py`

## Permisos

Rutas restringidas a roles `admin` y `sistemas`.

## Integración

- ERP dashboard: enlace a importación
- BI: `BiDashboardService.clear_cache()` tras confirmar o revertir
- Conciliación / clientes: datos alimentan tablas ERP usadas por servicios existentes

## Limitaciones

- Límite por defecto 5000 filas por archivo
- Duplicados por folio vs `sales_sale`, `sale_captures` y dentro del archivo
- Rollback no elimina ventas con pagos registrados
- Contratos: hojas por vendedor según plantilla; validación menos estricta que ventas
