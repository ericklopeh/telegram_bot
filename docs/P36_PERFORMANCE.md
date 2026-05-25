# P36 — Performance & Scaling

## Componentes
- `app/services/performance_service.py`: cache en memoria, paginación, profiling SQL (queries > `SLOW_QUERY_MS`), reporte `/admin/performance`.

## Variables
- `SLOW_QUERY_MS` (default 500)
- `CACHE_TTL_SECONDS` (default 60)

## Uso
Los dashboards BI y rol usan `PerformanceService.cached()` para reducir carga repetida.

## Índices (migración `l8m9n0o1p2q3`)
- `cases`: `(current_status, updated_at)`, `(seller_name, updated_at)`, `(company_id, branch_id)`
