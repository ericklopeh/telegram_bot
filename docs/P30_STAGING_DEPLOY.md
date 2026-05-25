# P30 — Staging / deploy en VPS

## Requisitos VPS

- Ubuntu 22.04+ (o similar) con Docker Engine 24+ y Compose v2
- 2 GB RAM mínimo (4 GB recomendado con OCR/Tesseract)
- Disco: espacio para `storage/`, `logs/`, `backups/`
- Puertos: `8080` (HTTP nginx) o el definido en `NGINX_HTTP_PORT`
- Copiar `storage/excel_masters/` al servidor (no versionado en git)

## Instalación rápida

```bash
git clone <repo> sistema_gaman && cd sistema_gaman
cp .env.example .env
# Editar .env con secretos reales (nunca commitear .env)
mkdir -p storage logs backups
# Copiar masters Excel y plantillas bajo storage/
chmod +x scripts/*.sh
./scripts/deploy_staging.sh
```

## Compose: desarrollo vs staging

| Archivo | Uso |
|---------|-----|
| `docker-compose.yml` | Desarrollo local: bind `./:/app`, puerto `WEB_HOST_PORT` (8010) |
| `docker-compose.staging.yml` | VPS/staging: nginx frontal, `WEB_DEBUG=false`, volúmenes `storage` + `logs` |

## Variables críticas (.env)

Ver `.env.example`. Obligatorias:

- `DATABASE_URL`, `POSTGRES_*`, `WEB_SESSION_SECRET`, `TELEGRAM_BOT_TOKEN`
- SharePoint: `MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET`, `MS_ROOT_FOLDER`
- P30: `ENVIRONMENT=staging`, `LOG_LEVEL=INFO`, `WEB_DEBUG=false`

## Levantar staging manualmente

```bash
docker compose -f docker-compose.staging.yml up -d db web nginx
./scripts/run_migrations.sh
curl http://localhost:8080/health
curl http://localhost:8080/health/full
```

## Bot Telegram (opcional)

```bash
docker compose -f docker-compose.staging.yml --profile with-bot up -d bot
```

## Health endpoints

| Ruta | Uso |
|------|-----|
| `GET /health` | Liveness (sin BD) |
| `GET /health/full` | Readiness: BD, storage, exports, Graph config |
| `GET /ping` | Identificación instancia web |

Nginx expone `/health` sin logs de acceso.

## Migraciones

```bash
docker compose -f docker-compose.staging.yml exec web alembic upgrade head
# o
./scripts/run_migrations.sh
```

## Reinicio

```bash
./scripts/restart_services.sh
```

## Troubleshooting

| Problema | Solución |
|----------|----------|
| 502 nginx | `docker compose ... logs web`; esperar healthcheck web |
| `/health/full` 503 | Revisar checks en JSON; BD, storage, masters |
| Sin masters Excel | Montar/copiar `storage/excel_masters/` |
| SharePoint falla | `/admin/sharepoint/health`; revisar `logs/sharepoint.log` |
| 500 con detalle | Verificar `WEB_DEBUG=false` en staging |

## SharePoint

- Timeouts nginx: 300s en `nginx/app.conf`
- Logs: `logs/sharepoint.log`, `logs/errors.log`
