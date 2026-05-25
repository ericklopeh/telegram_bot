# P30 — Backups PostgreSQL

## Exportar

```bash
./scripts/backup_db.sh
```

Genera `backups/pg_<DB>_<timestamp>.sql.gz` usando el servicio `db` de staging.

Variables opcionales:

- `COMPOSE_FILE=docker-compose.staging.yml` (default)
- `BACKUP_DIR=./backups`

## Restaurar

```bash
./scripts/restore_db.sh ./backups/pg_telegram_bot_20260519_120000.sql.gz
```

**Advertencia:** sobrescribe la base actual. Detener tráfico o poner app en mantenimiento antes.

## Cron en VPS (ejemplo)

```cron
0 3 * * * cd /opt/sistema_gaman && ./scripts/backup_db.sh >> logs/backup.log 2>&1
```

## Retención

Rotar manualmente o con política del proveedor (S3, etc.). No incluido en P30.

## Verificación

```bash
gunzip -c backups/archivo.sql.gz | head -20
```

Debe mostrar cabecera SQL de `pg_dump`.
