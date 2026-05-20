# P22 — Pruebas manuales workflow

1. Caso pedido nuevo muestra pipeline en `/casos/{id}`.
2. En `PREP_AUTORIZACION`, botón SNTE **no** visible (o bloqueado con mensaje APROBADO).
3. Tras compulsa OK / `APROBADO`, SNTE se habilita; timeline `SNTE_UNLOCKED_AFTER_APPROVAL` si aplica.
4. Sin SharePoint OK, en venta no aparece «Registrar definitivo» (mensaje SHAREPOINT_OK).
5. Con SharePoint OK, registro venta permitido; post-registro recálculo sube a `REGISTRADO` / comisión.
6. `POST /casos/{id}/recalcular-estado` (admin) actualiza badge workflow.
7. Transición inválida vía admin devuelve error claro en timeline `WORKFLOW_TRANSITION_BLOCKED`.
8. `/admin/workflow` lista estados, transiciones y bloqueos recientes.
9. Dashboard casos abiertos sin cambios bruscos (legacy status preservado).
10. Maestros Excel sin modificar.

```bash
docker compose exec web alembic upgrade head
docker compose restart web
python -m pytest tests/test_workflow_transitions.py tests/test_workflow_dependencies.py -q
```
