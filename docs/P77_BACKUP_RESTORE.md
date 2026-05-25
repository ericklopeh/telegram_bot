# P77 — Backup and restore validation

Respaldos reales de **PostgreSQL** y validación de integridad. Sin secretos en scripts.

## Scripts

| Script | Entorno | Descripción |
|--------|---------|-------------|
| `scripts/backup_db.sh` | Genérico | `pg_dump` vía compose → `backups/pg_*.sql.gz` |
| `scripts/backup_staging.sh` | Staging | Wrapper con `COMPOSE_FILE=docker-compose.staging.yml` |
| `scripts/prod_backup.sh` | Producción | PG + `storage.tar.gz` + manifest |
| `scripts/restore_db.sh` | Genérico | Restaura `.sql.gz` a BD compose |
| `scripts/prod_restore.sh` | Producción | Restaura bundle P70 |
| `scripts/prod_verify_backup.sh` | Producción | Valida manifest + gzip + tar |
| `scripts/restore_check_db.sh` | Cualquiera | Solo verifica gzip sin restaurar |

## Backup local (desarrollo)

```bash
cp .env.example .env   # si no existe
docker compose up -d db
./scripts/backup_db.sh
./scripts/restore_check_db.sh backups/pg_*.sql.gz
```

## Backup staging (VPS)

```bash
cd /opt/sistema_gaman
./scripts/backup_staging.sh
ls -lh backups/
```

Programar cron (ejemplo diario 02:00 UTC):

```cron
0 2 * * * cd /opt/sistema_gaman && ./scripts/backup_staging.sh >> logs/backup.log 2>&1
```

## Backup producción

Ver `docs/P70_BACKUPS.md` y `scripts/prod_backup.sh`.

## Checklist — prueba de restore

- [ ] Crear backup en entorno de prueba
- [ ] `./scripts/restore_check_db.sh <archivo.sql.gz>` → OK
- [ ] Restaurar en BD **vacía de prueba** (no sobre producción sin ventana)
- [ ] `alembic current` coherente post-restore
- [ ] Login web y un caso visible
- [ ] Documentar RTO/RPO internos (ej. RPO 24h, RTO 2h)

Restore staging (destructivo — solo mantenimiento):

```bash
./scripts/restore_db.sh backups/pg_gaman_staging_YYYYMMDD_HHMMSS.sql.gz
```

## Retención

- Variable `BACKUP_RETENTION_DAYS` (default 14) — limpieza manual/cron según política
- Rotar backups viejos del disco VPS

## Referencias

- `docs/P70_BACKUPS.md`
- `docs/P73_REAL_STAGING_ENVIRONMENT.md`
