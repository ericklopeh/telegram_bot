# P69 — Smoke tests

## scripts/smoke_check_web.py

| Check | Descripción |
|-------|-------------|
| database | SELECT 1 |
| redis_optional | PING si REDIS_URL |
| imports_core | Módulos críticos |
| excel_masters_protected | Guard path sin escribir en masters |
| storage_writable | storage/imports/exports |
| templates_critical | Plantillas P61+ |
| migrations_head | alembic heads/current |
| realtime_hub | publish + poll + heartbeat |
| jobs_registry | JOB_TYPES + reconcile |
| feature_flags | defaults |
| log_secret_scrub | SecretScrubFilter |
| http_* | Con `--base-url` |

Salida: `OK` / `WARN` / `FAIL` + ms + resumen.

Código salida: `0` sin FAIL, `1` con FAIL.

## scripts/smoke_check.py

Smoke legacy (env, plantillas SNTE, imports). Complementario.
