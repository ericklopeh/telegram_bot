# P30 — Operaciones diarias

## Logs

| Archivo | Contenido |
|---------|-----------|
| `logs/app.log` | Aplicación general (rotación 10 MB × 5) |
| `logs/sharepoint.log` | Cliente Graph / sync |
| `logs/workflow.log` | Transiciones workflow |
| `logs/errors.log` | ERROR y superior |
| `logs/nginx` | Dentro del contenedor nginx (`docker logs gaman_staging_nginx`) |

Configuración: `config/logging.yaml`, cargada al arranque web.

Cada request HTTP incluye header `X-Request-ID` para correlación.

## Storage

Estructura creada al arranque (`ensure_runtime_directories`):

- `storage/cases/` — documentos por caso
- `storage/excel_exports/` — única zona de escritura Excel operativa
- `storage/excel_masters/` — **solo lectura** en operación
- `storage/commission_exports/`

## Comandos frecuentes

```bash
# Estado
docker compose -f docker-compose.staging.yml ps

# Logs web
docker compose -f docker-compose.staging.yml logs -f web --tail=100

# Migraciones
./scripts/run_migrations.sh

# Backup
./scripts/backup_db.sh

# Deploy actualizado
git pull && ./scripts/deploy_staging.sh
```

## Seguridad básica (sin P28 RBAC)

- `WEB_DEBUG=false` en staging
- `WEB_RBAC_RELAXED=false` en producción
- `TELEGRAM_DEV_FALLBACK_ANY_SENDER=false`
- Errores 500 genéricos al usuario (sin stack trace)
- Headers: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`

## Checklist post-deploy VPS

- [ ] `.env` con secretos fuertes
- [ ] `storage/excel_masters/` presente
- [ ] `curl /health` y `/health/full` OK
- [ ] Migraciones al head
- [ ] Login web funcional
- [ ] Backup cron configurado
- [ ] Puerto firewall solo 80/443 (nginx)
- [ ] `DEMO_MODE=false`, `ENVIRONMENT=staging`

## Limitaciones P30

- Sin TLS/HTTPS automático (añadir certbot o proxy externo)
- Sin Kubernetes / HA
- Bot opcional vía profile `with-bot`
