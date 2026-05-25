# P72 — Staging deploy automation (GitHub Actions)

Despliegue **manual** y seguro a staging mediante `workflow_dispatch`. No incluye secretos en el repositorio.

## Workflow

Archivo: `.github/workflows/deploy-staging.yml`

| Job | Descripción |
|-----|-------------|
| `validate-and-test` | Valida secrets, compose, build Docker, `pytest -q` |
| `deploy-staging` | SSH al VPS, `git checkout`, compose up, migraciones, `smoke_health.sh` |

**Trigger:** solo manual (Actions → Deploy Staging → Run workflow).

### Inputs

| Input | Default | Descripción |
|-------|---------|-------------|
| `git_ref` | `feature/web-demo` | Rama o tag a desplegar en el servidor |
| `dry_run` | `false` | Si `true`, solo tests/validación (sin SSH) |

## Secrets requeridos (GitHub)

Configurar en: **Repository → Settings → Secrets and variables → Actions → New repository secret**

| Secret | Descripción | Ejemplo (no real) |
|--------|-------------|-------------------|
| `STAGING_SSH_HOST` | IP o hostname del VPS | `staging.example.com` |
| `STAGING_SSH_USER` | Usuario SSH | `deploy` |
| `STAGING_SSH_PRIVATE_KEY` | Clave privada SSH (PEM completa) | `-----BEGIN OPENSSH PRIVATE KEY-----...` |
| `STAGING_APP_PATH` | Ruta del clone en el servidor | `/opt/sistema_gaman` |
| `STAGING_URL` | URL pública HTTP(S) del nginx staging | `https://staging.example.com` |

**Nunca** commitear `.env`, tokens de Telegram ni `MS_CLIENT_SECRET`.

### Environment opcional

El job `deploy-staging` usa `environment: staging` para aprobaciones manuales en GitHub (opcional: crear environment **staging** con required reviewers).

## Cómo ejecutar el workflow manual

1. Asegura que el VPS tiene:
   - Docker + Compose v2
   - Clone del repo en `STAGING_APP_PATH`
   - Archivo `.env` **solo en el servidor** (desde `.env.staging.example`)
   - `storage/`, `logs/`, `backups/` creados

2. En GitHub: **Actions** → **Deploy Staging** → **Run workflow**.

3. Elige:
   - **Branch** del workflow (normalmente `feature/web-demo` o `main`)
   - **git_ref**: rama a desplegar en el servidor (debe existir en `origin`)
   - **dry_run**: marcar solo para probar CI sin tocar el servidor

4. Espera:
   - Job verde `validate-and-test`
   - Job verde `deploy-staging`
   - Paso **Smoke health on staging URL** con HTTP 200 en `/health`

## Checklist de validación post-workflow

- [ ] `validate-and-test` pasó (`pytest -q` completo)
- [ ] `deploy-staging` pasó sin errores SSH
- [ ] `GET {STAGING_URL}/health` → 200
- [ ] Login web en staging
- [ ] `GET {STAGING_URL}/health/full` revisado (503 → corregir checks)
- [ ] Migraciones aplicadas (`alembic current` en servidor)
- [ ] Logs en servidor: `docker compose -f docker-compose.staging.yml logs web --tail 50`

Comando local equivalente al smoke del workflow:

```bash
./scripts/smoke_health.sh https://tu-staging.example.com
```

## Rollback básico

1. En GitHub, ejecutar de nuevo el workflow con **git_ref** apuntando al commit/rama anterior estable.

2. O por SSH en el servidor:

```bash
cd /opt/sistema_gaman   # STAGING_APP_PATH
git fetch --all
git checkout <rama-o-commit-anterior>
docker compose -f docker-compose.staging.yml build web nginx
docker compose -f docker-compose.staging.yml up -d db web nginx
docker compose -f docker-compose.staging.yml exec -T web alembic downgrade -1   # solo si migración falló
./scripts/smoke_health.sh http://localhost:8080
```

3. Si el deploy rompió BD: restaurar backup (`scripts/prod_restore.sh` / `backup_db.sh`) según `docs/P70_BACKUPS.md`.

## Scripts relacionados

| Script | Uso |
|--------|-----|
| `scripts/ci_validate_staging_deploy.sh` | Valida secrets en el runner |
| `scripts/gh_deploy_staging_remote.sh` | Deploy SSH (llamado por Actions) |
| `scripts/smoke_health.sh` | Smoke `/health` post-deploy |
| `scripts/deploy_staging.sh` | Deploy manual en el mismo servidor |

## Compatibilidad

- Desarrollo local: `docker-compose.yml` sin cambios
- CI: `.github/workflows/ci.yml` independiente
- No se modifica lógica de negocio (solo CI/docs/scripts)

## Referencias

- `docs/P71_STAGING_DEPLOY.md`
- `docs/P30_STAGING_DEPLOY.md`
- `.env.staging.example`
