# P44 — Multiempresa / sucursales

## Modelos
- `companies`, `branches`
- Columnas `company_id`, `branch_id` en `users` y `cases` (default `1`)

## Servicio
`app/services/tenant_service.py`

## Compatibilidad single-tenant
Instalación actual usa empresa/sucursal `default` / `main` (id=1). Sin filtro agresivo que oculte datos legacy.

## Sesión
Login enriquece `company_name`, `branch_name` en sesión web.

## Futuro
Selector empresa/sucursal en navbar; branding desde `companies.branding_json`.
