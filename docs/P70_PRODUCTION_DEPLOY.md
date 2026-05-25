# P70 — Despliegue producción

## Requisitos VPS

- Ubuntu 22.04+ / Debian 12+
- Docker 24+ y Docker Compose v2
- 4 GB RAM mínimo (8 GB recomendado)
- Disco: PostgreSQL + `storage/` (casos, exports, attachments)

## Setup inicial

```bash
git clone <repo> /opt/sistema_gaman
cd /opt/sistema_gaman
cp .env.example .env
# Editar .env: secretos, Graph, WEB_SESSION_SECRET, POSTGRES_PASSWORD
mkdir -p backups logs storage
```

## Deploy

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml run --rm web python -m alembic upgrade head
docker compose -f docker-compose.prod.yml --profile with-redis --profile with-worker up -d
```

## Variables críticas

| Variable | Producción |
|----------|------------|
| ENVIRONMENT | production |
| WEB_DEBUG | false |
| WEB_RBAC_RELAXED | false |
| REDIS_URL | redis://redis:6379/0 |
| SECURE_COOKIES | true (HTTPS) |

## Rollback

```bash
docker compose -f docker-compose.prod.yml down
# Restaurar backup: scripts/prod_restore.sh backups/prod_YYYYMMDD_HHMMSS
docker compose -f docker-compose.prod.yml up -d
```

## Puertos

- Nginx: `${NGINX_HTTP_PORT:-80}`
- PostgreSQL: solo red interna (no publicar en VPS sin firewall)
