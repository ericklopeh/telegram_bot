# P70 — Backups

## Crear backup

```bash
chmod +x scripts/prod_backup.sh
./scripts/prod_backup.sh
```

Incluye:

- PostgreSQL (`pg_*.sql.gz`)
- Storage: cases, excel_exports, attachments, tenants, imports
- **Excluye** escritura en `excel_masters/`

Salida: `backups/prod_YYYYMMDD_HHMMSS/`

## Verificar

```bash
./scripts/prod_verify_backup.sh backups/prod_YYYYMMDD_HHMMSS
```

## Restaurar

```bash
./scripts/prod_restore.sh backups/prod_YYYYMMDD_HHMMSS
# Confirmar escribiendo RESTORE
```

## Retención

`BACKUP_RETENTION_DAYS=14` en `.env` (default).

Programar cron en VPS:

```cron
0 3 * * * cd /opt/sistema_gaman && ./scripts/prod_backup.sh >> logs/backup.log 2>&1
```
