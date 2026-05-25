# P70 — Monitoreo

## Endpoints

| Ruta | Uso |
|------|-----|
| GET /health | Liveness |
| GET /health/full | Readiness (DB, storage, templates) |
| GET /metrics | Prometheus text exposition |

## Métricas expuestas

- `gaman_up`, `gaman_uptime_seconds`
- `gaman_redis_available`
- `gaman_websocket_subscribers`
- `http_requests_total`, `jobs_processed_total`, `realtime_publish_total`

## Sentry (opcional)

```env
SENTRY_DSN=https://...
```

Requiere `pip install sentry-sdk` en la imagen si se usa.

## Logs

- `logs/app.log`, `logs/errors.log`
- `logs/realtime.log`, `logs/jobs.log`, `logs/compliance.log`

Correlation ID: header `X-Request-ID` en respuestas.
