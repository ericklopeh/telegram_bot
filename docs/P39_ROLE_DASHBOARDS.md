# P39 — Dashboard vendedor / supervisor

## Rutas
| Rol | Ruta |
|-----|------|
| Vendedor | `GET /mi-dashboard` |
| Supervisor | `GET /supervisor/dashboard` |

## Servicio
`app/services/role_dashboard_service.py`

## Contenido vendedor
Mis casos, ventas, comisiones, SLA en riesgo, pendientes.

## Contenido supervisor
Ranking vendedores, casos atorados (>24h), vendedores críticos, KPIs de equipo.
