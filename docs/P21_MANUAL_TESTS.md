# P21 — Control automático de comisiones

## Checklist

1. Registrar venta definitiva (admin) → comisión `pending` en `/comisiones`.
2. Segundo registro de la misma venta no duplica (actualiza si sigue pendiente).
3. Vendedor «Juan Manuel» → 60% sobre monto venta.
4. Otros vendedores → 46%.
5. Timeline del caso: `COMMISSION_CREATED` / `COMMISSION_UPDATED`.
6. Marcar pagada → `COMMISSION_PAID`, estado pagada.
7. Exportar Excel y PDF con filtros activos.
8. Supervisor: top vendedores y promedios en `/comisiones`.

## Comandos

```bash
docker compose exec web alembic upgrade head
docker compose restart web
python -m pytest -q
```

## Commit

```
feat(web): P21 control automático de comisiones
```
