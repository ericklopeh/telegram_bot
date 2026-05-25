# P85 — Production rollout readiness

Checklist **go-live** para rollout completo post-piloto.

## Go-live general

- [ ] Piloto P84 cerrado con go
- [ ] `pytest -q` y CI verdes
- [ ] `WEB_RBAC_RELAXED=false`
- [ ] `WEB_DEBUG=false`
- [ ] `ENVIRONMENT=production`
- [ ] Plan comunicación usuarios

## DNS / dominio

- [ ] DNS producción → VPS/load balancer
- [ ] TLS válido (Let's Encrypt o comercial)
- [ ] `SECURE_COOKIES=true`
- [ ] `WEBHOOK_BASE_URL` HTTPS si bot webhook

## Backups

- [ ] `scripts/prod_backup.sh` en cron
- [ ] Retención `BACKUP_RETENTION_DAYS`
- [ ] Copia off-site (S3/rsync)

## Restore

- [ ] Restore probado en entorno aislado (P77)
- [ ] RTO/RPO acordados con negocio
- [ ] Contacto on-call definido

## Monitoring

- [ ] Uptime en `/health`
- [ ] Alertas disco/memoria
- [ ] `METRICS_ENABLED=true` + scraping opcional
- [ ] Sentry `SENTRY_DSN` si aplica

## Secrets

- [ ] Todos en vault/.env servidor
- [ ] GitHub Actions secrets producción (si aplica)
- [ ] Rotación tokens expuestos
- [ ] `.env` nunca en git

## Telegram webhook

- [ ] Decisión polling vs webhook documentada (P74)
- [ ] `telegram_set_webhook.sh` ejecutado si webhook
- [ ] Un solo modo activo por token

## Workers / jobs

- [ ] `JOBS_ASYNC_ENABLED` según arquitectura
- [ ] Redis si workers distribuidos
- [ ] JobQueue bot para compulsa/SharePoint SLA
- [ ] `SCHEDULER_ENABLED` según compose prod

## DB migrations

- [ ] `alembic upgrade head` en ventana
- [ ] Backup pre-migración
- [ ] `alembic current` documentado

## Rollback

- [ ] Tag git release anterior identificado
- [ ] Script deploy con `git_ref` previo
- [ ] Restore BD probado
- [ ] Comunicación usuarios plantilla

## Referencias

- `docs/P70_GO_LIVE_CHECKLIST.md`
- `docs/P72_STAGING_DEPLOY_AUTOMATION.md`
- `docs/P76_OBSERVABILITY_MONITORING.md`
