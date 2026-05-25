# P45 — API interna / pública

## Base
`/api/v1`

## Autenticación
Header `Authorization: Bearer <token>` o `X-API-Key: <token>`

Tabla `api_tokens` (hash SHA-256, rate limit por token).

## Endpoints
| Método | Ruta | Scope |
|--------|------|-------|
| GET | `/api/v1/health` | público |
| GET | `/api/v1/casos` | read |
| GET | `/api/v1/casos/{id}` | read |
| GET | `/api/v1/search` | read |
| GET | `/api/v1/bi/summary` | read |
| GET | `/api/v1/jobs` | admin |
| POST | `/api/v1/jobs/{job_type}` | write |

## OpenAPI
Documentación automática FastAPI en `/docs` (si está habilitada en el entorno).

## Integraciones futuras
Power BI, app móvil, n8n — consumir JSON v1 sin romper rutas web P19-P35.
