# P41 — Search global

## Rutas
- `GET /search` — UI agrupada
- `GET /api/search` — JSON (sesión web)
- `GET /api/v1/search?q=` — API token

## Servicio
`app/services/global_search_service.py`

## Grupos
Casos, ventas, documentos, comisiones, import batches.

## Navbar
Campo con debounce (`/static/js/global_search.js`).
