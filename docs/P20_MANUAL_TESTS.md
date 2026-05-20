# P20 — Cola segura de registro y conciliación Excel

## Checklist manual

1. **Admin registra venta correctamente** — `POST /ventas/nueva` con acción «Registrar definitivo»; timeline muestra `SALE_CAPTURE_REGISTRATION_QUEUED`, `SALE_CAPTURE_PROCESSING`, `SALE_CAPTURE_REGISTERED`.
2. **Venta queda registered** — `registration_status=registered`, `status=registered`, `registered_at` con fecha.
3. **Excel bloqueado** — Con el archivo de operación abierto en Excel, el registro falla → `registration_failed` / `export_failed`, sin marcar registrada.
4. **Error visible** — En `/ventas/{id}` se muestran `registration_error` y `export_error`.
5. **Pendientes** — La venta fallida aparece en `/ventas/pendientes` (solo admin/sistemas/autorización).
6. **Reintentar** — Botón o `POST /ventas/{id}/reintentar-registro` incrementa `registration_attempts` y, si Excel está libre, completa el registro.
7. **Timeline** — Eventos queued / processing / failed / registered / retry en el caso vinculado.
8. **Vendedor** — No ve enlaces ni accede a `/ventas/pendientes` ni `/control/conciliacion` (redirige a dashboard).
9. **Conciliación** — `/control/conciliacion` lista inconsistencias (archivos faltantes, duplicados, errores activos).
10. **Maestros intactos** — Verificar que `storage/excel_masters/` no cambia; solo `storage/excel_exports/`.

## Comandos

```bash
docker compose exec web alembic upgrade head
docker compose restart web
docker compose logs -f web
python -m pytest -q
docker compose run --rm web python scripts/smoke_check.py
```

## Commit sugerido

```
feat(web): P20 cola segura y conciliación de registro Excel

Agrega estados formales de registro, cola segura para exportaciones Excel,
reintentos operativos, vista de pendientes y conciliación comercial sin
modificar los maestros originales.
```
