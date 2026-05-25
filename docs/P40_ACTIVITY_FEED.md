# P40 — Timeline / Activity feed

## Ruta
`GET /activity`

## Servicio
`app/services/activity_feed_service.py`

## Fuentes
- Tabla `activity_events` (eventos explícitos)
- Fallback: `case_events` recientes

## API de registro
`ActivityFeedService.record(...)` — usar desde uploads, workflow, imports, recovery.

## Filtros
`?entity_type=case&entity_id=123`
