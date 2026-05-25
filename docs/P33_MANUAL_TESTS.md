# P33 — Pruebas manuales

## Requisitos

- Usuario `admin` o `sistemas`
- `alembic upgrade head` (tabla `ops_incidents`)
- P19–P32 operativos

## 1. Panel `/ops`

1. Iniciar sesión como admin
2. Menú **Operación → Panel ops**
3. Verificar KPIs: salud, crítico, advertencia, pendiente
4. Contadores SharePoint / imports / exports
5. Sección Recovery con botones visibles

## 2. Incidencias

1. Tras cargar `/ops`, ir a **Incidencias**
2. Filtrar `OPEN` — deben aparecer hallazgos sincronizados
3. **Ack** en una incidencia → estado `ACKNOWLEDGED`
4. **Resolver** → estado `RESOLVED`, badge verde

## 3. SharePoint retry

1. Tener un documento `UPLOAD_FAILED` (o simular)
2. POST desde panel **Reintentar SharePoint**
3. Mensaje en `/ops?msg=...`
4. Revisar documento y timeline del caso

## 4. Regenerar export

1. Venta con error de registro en `/ventas/pendientes`
2. Desde incidencia o conocer `sale_capture_id`
3. `POST /ops/regenerate/export/{id}` (vía formulario futuro o herramienta HTTP)
4. Confirmar archivos bajo `storage/excel_exports/` y **no** en `excel_masters/`

## 5. Comisiones

1. Venta registrada sin comisión
2. **Recalcular comisiones pendientes**
3. Verificar fila en `/comisiones`

## 6. Conciliación

1. **Recalcular conciliación**
2. Revisar `/control/conciliacion` y `/erp/conciliacion`

## 7. Import fallido

1. Lote `failed` en `/imports`
2. `POST /ops/retry/import/{batch_id}` → redirección a preview

## Automatizado

```bash
python -m pytest -q tests/test_p33_ops.py
```
