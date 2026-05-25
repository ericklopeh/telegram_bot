# P76 — Observability and monitoring

Monitoreo mínimo productivo sobre endpoints y métricas ya existentes (P30/P70).

## Endpoints de salud

| Ruta | Tipo | Uso monitor externo |
|------|------|---------------------|
| `GET /health` | Liveness | Uptime cada 1–5 min |
| `GET /health/full` | Readiness | Alerta si 503 > 5 min |
| `GET /ping` | Identidad | Opcional |
| `GET /metrics` | Prometheus text | Scraping interno |

Implementación: `app/web/routes/health.py`, `app/observability/metrics.py`.

## Métricas clave (`/metrics`)

| Métrica | Significado |
|---------|-------------|
| `gaman_up` | Proceso activo |
| `gaman_uptime_seconds` | Tiempo desde arranque contador |
| `gaman_environment_info{env}` | staging / production |
| `gaman_redis_available` | Redis alcanzable (si configurado) |
| `gaman_websocket_subscribers` | Conexiones WS en memoria |
| `http_requests_total` | Contador requests HTTP |
| `jobs_processed_total` | Jobs worker (si incrementado) |

Deshabilitar exposición: `METRICS_ENABLED=false` → 404.

## Logs esperados

| Origen | Nivel | Ejemplos |
|--------|-------|----------|
| Web arranque | WARNING | `Arranque web env=... /health=...` |
| Errores 500 | ERROR | `HTTP 500 para GET /...` |
| Slow queries | WARNING | P36 `SLOW_QUERY_MS` |
| Bot | INFO | `JobQueue habilitado`, errores token |
| Sentry | — | Si `SENTRY_DSN` configurado (`app/observability/sentry_init.py`) |

Formato: logging estándar Python; en Docker: `docker compose logs -f web`.

## Checklist — uptime monitor externo

- [ ] Monitor HTTP(S) a `{URL}/health` cada 60s
- [ ] Alerta email/Slack si down > 3 checks
- [ ] Monitor secundario a `/health/full` (opcional, puede 503 si Graph off)
- [ ] Registrar `X-Request-ID` en tickets de soporte
- [ ] Dashboard proveedor (UptimeRobot, Better Stack, Datadog synthetics)

## Checklist — alertas básicas

- [ ] Disco VPS > 85%
- [ ] Contenedor `web` reiniciado > 3 veces/hora
- [ ] PostgreSQL conexiones agotadas
- [ ] Backup stale (> 48h sin `backups/pg_*.sql.gz`)
- [ ] Certificado TLS < 14 días para expirar

## Staging / producción

```bash
curl -sf https://staging.example.com/health
curl -sf https://staging.example.com/metrics | head
```

## Referencias

- `docs/P70_MONITORING.md`
- `docs/P69_STABILIZATION.md` (logging)
