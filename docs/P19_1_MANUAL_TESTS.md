# P19.1 — Pruebas manuales (Action guard + checklist)

## Preparación

```powershell
docker compose exec web alembic upgrade head
docker compose restart web
docker compose logs -f web
```

## Checklist manual

| # | Caso | Esperado |
|---|------|----------|
| 1 | Login **vendedor** → `/ventas/nueva` | No aparece botón activo «Registrar definitivo» (deshabilitado con tooltip) |
| 2 | Login **admin** → `/ventas/{id}` con checklist completo | Botón «Registrar definitivo» habilitado |
| 3 | Mismo folio en otra captura | Mensaje de bloqueo; no marca `registered` |
| 4 | Registrar con Excel abierto en escritorio (si aplica) | `export_failed`, mensaje claro, **no** `registered` |
| 5 | `/ventas/nueva?case_id={id}` caso pedido válido | Formulario precargado; `case_id` oculto |
| 6 | `/ventas/{id}` | Checklist con badges OK / Pendiente / Error |
| 7 | `/ventas` filtros folio, RFC, registrado sí/no | Tabla filtrada |

## Smoke rápido

- `GET http://localhost:8010/ping` → OK
- `GET http://localhost:8010/ventas` → login o listado
- Tras registrar: archivos en `storage/excel_exports/operations/{id}/` y copia diaria

## Commit sugerido

```
feat(web): P19.1 action guard, checklist y duplicados en captura de ventas
```
