# P37 — Async Jobs / Cola real

## Arquitectura
- Tabla `background_jobs` (PostgreSQL).
- `app/services/job_service.py`: encolar, procesar, reintentar.
- `app/jobs/registry.py`: handlers por tipo (SharePoint, imports, comisiones, BI, recovery).
- Panel web: `GET /jobs` (admin/sistemas).

## Ejecución
1. **Thread local** (default): `JOBS_ASYNC_ENABLED=true` sin Redis.
2. **RQ + Redis** (opcional): `REDIS_URL=redis://redis:6379/0` y worker `rq worker gaman`.

## Tipos de job
`sharepoint_sync`, `import_batch`, `export_report`, `recovery_bulk`, `commission_recalc`, `reconciliation_heavy`, `bi_refresh`

## Docker Redis (opcional)
```bash
docker compose --profile with-redis up -d
```
