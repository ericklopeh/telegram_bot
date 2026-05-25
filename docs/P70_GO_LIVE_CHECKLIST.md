# P70 — Go-live checklist

## Pre-deploy

- [ ] `.env` completo sin valores `replace-me`
- [ ] `WEB_DEBUG=false`, `ENVIRONMENT=production`
- [ ] `WEB_SESSION_SECRET` ≥ 32 caracteres aleatorios
- [ ] `WEB_RBAC_RELAXED=false`
- [ ] Microsoft Graph configurado (SharePoint)
- [ ] `alembic upgrade head` probado
- [ ] `python scripts/go_live_check.py` → LISTO
- [ ] `python scripts/smoke_check_web.py --base-url http://<host>` 

## Infra

- [ ] Docker + Compose instalados
- [ ] Firewall: solo 80/443 públicos
- [ ] HTTPS (certbot o proxy externo) + `SECURE_COOKIES=true`
- [ ] Redis profile activo si multi-worker
- [ ] Worker + scheduler profiles si jobs pesados

## Post-deploy

- [ ] `GET /health` → 200
- [ ] `GET /health/full` → 200
- [ ] `GET /metrics` contiene `gaman_up 1`
- [ ] WebSocket `/ws/activity` conecta tras nginx
- [ ] Login web operativo
- [ ] `./scripts/prod_backup.sh` + verify OK
- [ ] Cron backup diario

## Rollback plan

- [ ] Backup previo al deploy verificado
- [ ] `prod_restore.sh` probado en staging
- [ ] Contacto on-call documentado

## Troubleshooting

| Síntoma | Acción |
|---------|--------|
| 502 nginx | `docker logs gaman_prod_web` |
| WS cae | Revisar `app.prod.conf` upgrade headers |
| Jobs atascados | `reconcile_stale_jobs` vía worker restart |
| DB llena | Vacuum + ampliar volumen `pg_data_prod` |
