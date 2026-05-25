# P43 — Analytics avanzados

## Ruta
`GET /analytics/avanzado`
`GET /analytics/export` — CSV

## Servicio
`app/services/analytics_service.py`

## Métricas
- Aging de casos (0-24h, 24-72h, 72h+)
- Productividad por vendedor
- Tendencia semanal simple
- Forecast heurístico
- Snapshots en `analytics_snapshots`

## Job
Encolar `bi_refresh` desde `/jobs` para capturar snapshot mensual.
