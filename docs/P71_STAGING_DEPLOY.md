# P71 — Staging deployment readiness

Preparación para desplegar en **staging** sin romper desarrollo local (`docker-compose.yml`) ni CI (`.env` temporal en workflows).

## Health endpoints (verificado)

| Ruta | Tipo | Auth |
|------|------|------|
| `GET /health` | Liveness — proceso web activo | No |
| `GET /health/full` | Readiness — BD, storage, Graph, plantillas | No |
| `GET /ping` | Identificación instancia | No |

Implementación: `app/web/routes/health.py`, registrado en `app/web/main.py`.

Smoke local:

```bash
curl -sf http://localhost:8080/health
python -m pytest -q tests/test_p71_staging.py
./scripts/smoke_health.sh http://localhost:8080
```

---

## Variables requeridas

### Obligatorias

| Variable | Descripción |
|----------|-------------|
| `ENVIRONMENT` | `staging` |
| `DATABASE_URL` | PostgreSQL (`postgresql+psycopg://...`) |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | Deben coincidir con `DATABASE_URL` y compose |
| `WEB_SESSION_SECRET` | ≥ 32 caracteres aleatorios |
| `TELEGRAM_BOT_TOKEN` | Token BotFather (app lo exige al cargar Settings) |
| `STORAGE_ROOT` / `BASE_STORAGE_PATH` | `/app/storage` en contenedor |

### SharePoint (operación documentos)

| Variable | Descripción |
|----------|-------------|
| `MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET` | App Entra ID |
| `MS_SITE_HOSTNAME`, `MS_SITE_PATH` | Sitio SharePoint |
| `MS_ROOT_FOLDER` | Carpeta raíz en drive |

### Staging recomendado

| Variable | Valor |
|----------|-------|
| `WEB_DEBUG` | `false` |
| `WEB_RBAC_RELAXED` | `false` |
| `TELEGRAM_DEV_FALLBACK_ANY_SENDER` | `false` |
| `NGINX_HTTP_PORT` | `8080` (host) |

Plantilla: **`.env.staging.example`** → copiar a `.env` (nunca commitear `.env`).

```bash
cp .env.staging.example .env
```

---

## VPS con Docker Compose (recomendado)

Mismo flujo que P30, alineado con este repo.

```bash
git clone <repo> && cd sistema_gaman
cp .env.staging.example .env
# Editar .env con secretos reales
mkdir -p storage logs backups
# Copiar storage/excel_masters/ y plantillas (no en git)
chmod +x scripts/*.sh
./scripts/deploy_staging.sh
```

Manual:

```bash
docker compose -f docker-compose.staging.yml up -d db web nginx
./scripts/run_migrations.sh
curl -sf http://localhost:${NGINX_HTTP_PORT:-8080}/health
curl -sf http://localhost:${NGINX_HTTP_PORT:-8080}/health/full
```

Ver también: `docs/P30_STAGING_DEPLOY.md`, `docker-compose.staging.yml`, `scripts/deploy_staging.sh`.

---

## Heroku

El proyecto está orientado a **Docker + nginx**. En Heroku puedes usar **container stack** o un **dyno web** con uvicorn directo (sin nginx del repo).

### Opción A — Container (Dockerfile.web)

1. Crear app Heroku, activar stack container.
2. `heroku.yml` o dashboard: imagen desde `Dockerfile.web`.
3. Add-on **Heroku Postgres** → copiar `DATABASE_URL` (ajustar driver si hace falta a `postgresql+psycopg://`).
4. Config vars (Settings → Config Vars):

   - `ENVIRONMENT=staging`
   - `WEB_DEBUG=false`
   - `WEB_SESSION_SECRET=<random>`
   - `TELEGRAM_BOT_TOKEN=<token>`
   - `STORAGE_ROOT=/app/storage` (ephemeral filesystem en dyno; para persistencia usar S3 o volumen externo)
   - Variables `MS_*` para SharePoint

5. **Procfile** (si no usas solo Docker CMD):

   ```
   web: python -m uvicorn app.web.main:web_app --host 0.0.0.0 --port $PORT
   ```

6. Health check en Heroku: path `/health`, esperado 200.

7. Migraciones: release phase o one-off:

   ```bash
   heroku run alembic upgrade head
   ```

**Nota:** `storage/` y OCR requieren disco persistente o adaptación; para staging ligero validar solo rutas sin masters Excel.

### Opción B — Buildpack Python

1. `requirements-web.txt` como dependencias.
2. Procfile con uvicorn y `$PORT`.
3. Mismas config vars que arriba.

---

## Render

1. **New → Web Service** → conectar repo.
2. **Environment:** Docker o Python.
   - Docker: Dockerfile `Dockerfile.web`, comando por defecto del Dockerfile.
   - Python: Build `pip install -r requirements-web.txt`, Start `python -m uvicorn app.web.main:web_app --host 0.0.0.0 --port $PORT`
3. **PostgreSQL** (Render Postgres): enlazar `DATABASE_URL` (convertir a `postgresql+psycopg://` si es necesario).
4. Environment variables (panel): mismas que tabla obligatoria + `ENVIRONMENT=staging`.
5. **Health Check Path:** `/health` (Render usa GET periódico).
6. **Disk** (opcional): montar persistent disk en `/app/storage` para documentos y exports.
7. Pre-deploy / post-deploy command:

   ```bash
   alembic upgrade head
   ```

8. Staging URL: `https://<service>.onrender.com/health`

**Bot Telegram:** servicio **Background Worker** separado con `python -m app.main` y mismas variables.

---

## Checklist post-deploy

- [ ] `GET /health` → 200, `status: ok`
- [ ] `GET /health/full` → 200 o 503 documentado (revisar checks fallidos)
- [ ] Login web (`/login`) con usuario seed o admin creado
- [ ] `alembic current` en head
- [ ] `storage/excel_exports` y `storage/cases` escribibles
- [ ] `/admin/sharepoint/health` OK (si Graph configurado)
- [ ] Subida documento + sync SharePoint en caso de prueba
- [ ] `WEB_DEBUG=false` (sin traceback en 500)
- [ ] Logs en `logs/app.log` sin secretos en claro
- [ ] Backup: `./scripts/prod_backup.sh` o `backup_db.sh` probado en entorno staging
- [ ] `python scripts/smoke_check_web.py --base-url https://<tu-host-staging>` (opcional)

---

## Compatibilidad local y CI

| Entorno | Compose / env |
|---------|----------------|
| Desarrollo local | `docker-compose.yml` + `.env` propio |
| Staging VPS | `docker-compose.staging.yml` + `.env` desde `.env.staging.example` |
| CI GitHub | `.env` dummy temporal en workflow; no afecta local |

No se modificó lógica de negocio en P71.

---

## Referencias

- `docs/P30_STAGING_DEPLOY.md`
- `docs/P70_GO_LIVE_CHECKLIST.md`
- `docs/SECRETS_LOCAL.md`
- `tests/test_p71_staging.py`
- `scripts/smoke_health.sh`
