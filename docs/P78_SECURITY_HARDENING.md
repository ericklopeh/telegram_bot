# P78 — Security hardening (sin permisos avanzados)

Endurecimiento general **sin** implementar matriz RBAC avanzada (reservado para fase final).

## Checklist de secretos

- [ ] `.env` en `.gitignore` (nunca commitear)
- [ ] `.env.*` ignorado salvo `!.env.example` y `!.env.staging.example`
- [ ] Tokens Telegram solo en secret manager / `.env` servidor
- [ ] `MS_CLIENT_SECRET`, `WEB_SESSION_SECRET` rotados si hubo exposición
- [ ] GitHub Actions: secrets `STAGING_*` (P72), no en YAML
- [ ] Revisar historial git si algún secreto se subió por error (`git log -p`)

## Headers HTTP (ya en web)

Middleware `_security_headers_middleware` en `app/web/main.py` para `staging` y `production`:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Strict-Transport-Security` si `ENVIRONMENT=production`

## Rate limiting

- `API_RATE_LIMIT_PER_MIN` (default 120) en `app/web/middleware/production.py`
- Excluye: `/static`, `/health`, `/ping`, `/metrics`, `/telegram/webhook`
- `API_RATE_LIMIT_PER_MIN=0` desactiva límite (solo debug)
- **No** endurecer más sin medir impacto en tests y UX

## Cookies y sesión

| Variable | Staging | Producción |
|----------|---------|------------|
| `SECURE_COOKIES` | `false` sin HTTPS estricto | `true` |
| `WEB_RBAC_RELAXED` | `false` | `false` |
| `WEB_DEBUG` | `false` | `false` |

## `.gitignore` revisado (P78)

- Ignora `storage/`, `.env`, logs, IDE
- Permite plantillas `.env.example`, `.env.staging.example`
- Permite código `app/services/storage/` (no confundir con carpeta `storage/` datos)

## Plantillas sin secretos reales

| Archivo | Placeholders |
|---------|--------------|
| `.env.example` | `your_telegram_bot_token_here`, `replace-me` MS_* |
| `.env.staging.example` | `change_me_staging_db_password` |

Validación automática: `tests/test_p78_security_hardening.py`.

## Uploads

- `MAX_UPLOAD_BYTES` (default 128 MB) — rechazo 413 en middleware

## Fuera de alcance (esta fase)

- Matriz granular de permisos por módulo
- RBAC por recurso dinámico
- OAuth SSO enterprise

## Referencias

- `docs/SECRETS_LOCAL.md`
- `docs/P70_PRODUCTION_DEPLOY.md`
