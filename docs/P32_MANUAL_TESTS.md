# P32 — Pruebas manuales

## Requisitos

- Usuario `admin` o `sistemas`
- Migración aplicada: `alembic upgrade head`
- Copia de prueba del Excel **fuera** de `storage/excel_masters/` (por ejemplo en `storage/imports/`)

## 1. Subida y preview (dry-run)

1. Ir a `/imports`
2. Tipo: **Ventas 2026**, subir `.xlsx` de prueba
3. Verificar redirección a `/imports/{id}/preview`
4. Comprobar contadores: filas, listas, duplicados, errores
5. Confirmar que el estado es `previewed` y aparece badge dry-run
6. En BD: `import_batches` sin `imported_count` incrementado; sin nuevas filas en `sales_sale` hasta confirmar

## 2. Confirmación

1. En preview, pulsar **Confirmar importación**
2. Ver mensaje en listado con cantidad importada
3. Verificar en `/erp/dashboard` búsqueda por folio importado
4. `import_batches.status` = `confirmed`, `audit_trail` contiene `IMPORT_CONFIRMED`

## 3. Duplicados

1. Re-subir el mismo archivo o fila con folio ya existente
2. Preview debe marcar `duplicate_count` > 0 y código `DUPLICATE` en errores

## 4. Columnas faltantes

1. Subir Excel sin columnas FOLIO/VENDEDOR/CLIENTE
2. Preview debe fallar con `failed` o errores `MISSING_COLUMNS`

## 5. Export errores

1. Abrir `/imports/{id}/errors?download=xlsx`
2. Archivo en `storage/excel_exports/imports/import_errors_{id}.xlsx`
3. Confirmar que no se creó nada bajo `excel_masters/`

## 6. Rollback

1. Tras confirmar, en listado usar **Revertir**
2. Estado `rolled_back`; referencias `is_active=false`
3. Ventas del lote eliminadas si no tenían pagos

## 7. Contratos

1. Subir plantilla relación de contratos (copia fuera de masters)
2. Repetir preview → confirm
3. Verificar contratos en ERP/conciliación

## Automatizado

```bash
pytest -q tests/test_p32_excel_import.py
```
