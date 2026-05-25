# P75 — Real storage integration readiness

Preparación para almacenamiento **real** de documentos (OneDrive/SharePoint o S3-compatible) sin credenciales en el repo.

## Estrategia

### Primaria: Microsoft Graph / SharePoint

Ya implementado en `app/services/microsoft_graph.py` y campos SharePoint en `Document`.

| Requisito | Variable / doc |
|-----------|----------------|
| App Entra ID | `MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET` |
| Sitio | `MS_SITE_HOSTNAME`, `MS_SITE_PATH` |
| Drive | `MS_DRIVE_NAME`, `MS_DRIVE_ID`, `MS_ROOT_FOLDER` |
| Retry | Jobs en bot (`sharepoint_retry_job`) |

### Alternativa: S3-compatible (futuro)

| Paso | Acción |
|------|--------|
| 1 | Definir `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` en secret manager (no en git) |
| 2 | Implementar backend `S3StorageBackend` junto a `LocalStorageBackend` |
| 3 | Feature flag `STORAGE_PROVIDER=local|sharepoint|s3` |

## Estructura de carpetas (convención)

Ruta local documentada en `app/services/case_document_storage.py`:

```text
storage/cases/{year}/SEM_{week}/{seller}/FOLIO_{folio}_{cliente}/documents/
```

| Segmento | Fuente |
|----------|--------|
| `year` | `case.created_at` |
| `SEM_{week}` | `case.week_code` |
| `seller` | `case.seller_name` |
| `FOLIO_*` | `official_folio` / `temp_folio` + `client_name` |

SharePoint remoto: `case_documents_remote_relative_path()` — misma semántica.

## Abstracción existente

| Componente | Rol |
|------------|-----|
| `app/services/storage/local.py` | `LocalStorageBackend` |
| `app/services/storage/readiness.py` | Checklist P75 (`StorageReadinessChecklist`) |
| `app/services/case_document_service.py` | Persistencia BD + paths |
| `app/services/attachment_service.py` | Adjuntos en `storage/attachments/` |

## Checklist de integración real

- [ ] Cuenta Entra ID con permisos Graph (Files.ReadWrite.All o scoped)
- [ ] Secretos `MS_*` solo en `.env` servidor / vault
- [ ] Probar upload manual vía web en un caso de prueba
- [ ] Verificar `sharepoint_web_url` en fila `documents`
- [ ] Job retry configurado (`SHAREPOINT_RETRY_*`)
- [ ] Backup `storage/` en VPS (`docs/P77_BACKUP_RESTORE.md`)
- [ ] Política de retención y permisos de carpeta en SharePoint

## Qué no hacer

- No commitear `MS_CLIENT_SECRET` ni tokens
- No cambiar `storage/excel_masters/` (restricción proyecto)
- No activar S3 en producción sin prueba en staging

## Referencias

- `docs/P25_SHAREPOINT.md`
- `docs/P24_DOCUMENTS.md`
- `app/services/case_document_storage.py`
