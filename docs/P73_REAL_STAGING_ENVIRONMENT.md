# P73 — Real staging environment checklist

Checklist operativo para dejar **staging real** listo (Heroku, Render o VPS Docker). Complementa `docs/P71_STAGING_DEPLOY.md` y `docs/P72_STAGING_DEPLOY_AUTOMATION.md`.

## Opciones de hosting

### A) VPS Docker (recomendado para este repo)

| Item | Checklist |
|------|-----------|
| SO | Ubuntu 22.04+ con Docker y Compose v2 |
| Clone | Repo en `STAGING_APP_PATH` (ej. `/opt/sistema_gaman`) |
| Compose | `docker-compose.staging.yml` |
| Proxy | Nginx del compose o reverse proxy externo con TLS |
| Deploy | GitHub Actions P72 o `scripts/deploy_staging.sh` |
| `.env` | Solo en servidor: `cp .env.staging.example .env` |

### B) Render

| Item | Checklist |
|------|-----------|
| Servicio Web | Dockerfile.web o build command |
| PostgreSQL | Add-on managed Postgres |
| `DATABASE_URL` | Variable de Render (Internal URL) |
| Health check | Path `/health`, puerto del proceso |
| `ENVIRONMENT` | `staging` |
| Storage | Disco persistente o S3 para `storage/` |
| Bot | Webhook P74 (no polling largo en web service) |

### C) Heroku

| Item | Checklist |
|------|-----------|
| Procfile / container | Web dyno con uvicorn |
| `heroku-postgresql` | Addon + `DATABASE_URL` |
| Config vars | Mismas que `.env.staging.example` (sin commitear) |
| Health | `GET /health` en release phase opcional |
| Worker | Dyno separado para bot polling **o** webhook en web |

---

## Base de datos staging

- [ ] Instancia PostgreSQL 16+ dedicada (no compartir con producción)
- [ ] Usuario/clave fuertes (`POSTGRES_*` ≠ producción)
- [ ] `DATABASE_URL` con driver `postgresql+psycopg://`
- [ ] Backup inicial: `./scripts/backup_staging.sh`
- [ ] Migraciones: `alembic upgrade head` (en deploy P72 o manual)
- [ ] Verificar: `docker compose -f docker-compose.staging.yml exec db psql -U ... -c '\dt'`
- [ ] Retención backups: carpeta `backups/` en VPS, rotación 7–14 días

## Variables de entorno

Plantilla: **`.env.staging.example`** → `.env` en servidor.

| Grupo | Variables críticas |
|-------|-------------------|
| Core | `ENVIRONMENT=staging`, `LOG_LEVEL`, `APP_VERSION` |
| DB | `POSTGRES_*`, `DATABASE_URL` |
| Web | `WEB_SESSION_SECRET`, `WEB_DEBUG=false`, `WEB_RBAC_RELAXED=false` |
| Telegram | `TELEGRAM_BOT_TOKEN` (secret manager) |
| Graph | `MS_*` si se prueba SharePoint en staging |
| P70 | `METRICS_ENABLED=true`, `SECURE_COOKIES` según HTTPS |

**Nunca** subir `.env` al repositorio.

## Dominio / subdominio staging

- [ ] DNS `staging.tudominio.com` → IP o CNAME del host
- [ ] Certificado TLS (Let's Encrypt / proveedor)
- [ ] `STAGING_URL` en GitHub Secrets = URL pública con `https://`
- [ ] `WEBHOOK_BASE_URL` (P74) = misma base si bot en webhook
- [ ] Nginx escucha `NGINX_HTTP_PORT` (8080 host) o 443 terminado afuera
- [ ] Smoke: `./scripts/smoke_health.sh https://staging.tudominio.com`

## Migraciones

```bash
docker compose -f docker-compose.staging.yml exec -T web alembic current
docker compose -f docker-compose.staging.yml exec -T web alembic upgrade head
```

- [ ] Revisar una migración pendiente en ventana de mantenimiento
- [ ] Backup antes de migración con datos reales de prueba

## Rollback

1. **Código:** workflow P72 con `git_ref` anterior o SSH:

```bash
cd $STAGING_APP_PATH
git checkout <rama-estable>
docker compose -f docker-compose.staging.yml up -d --build web nginx
```

2. **BD:** restaurar dump (`scripts/restore_db.sh`) — ver `docs/P77_BACKUP_RESTORE.md`

3. **Validar:** `./scripts/smoke_health.sh $STAGING_URL`

## Validación final staging real

- [ ] `/health` → 200
- [ ] `/health/full` → 200 o 503 documentado (Graph/storage)
- [ ] Login web con usuario de prueba
- [ ] Bot responde (polling o webhook según P74)
- [ ] Un flujo E2E manual (`docs/P79_E2E_BUSINESS_FLOW.md`)

## Referencias

- `docs/P71_STAGING_DEPLOY.md`
- `docs/P72_STAGING_DEPLOY_AUTOMATION.md`
- `docker-compose.staging.yml`
