# P79 — End-to-end business flow validation

Validación del flujo operativo completo del negocio (manual + smoke automatizado donde aplica).

## Flujo documentado

```mermaid
flowchart LR
  A[Pedido / Caso] --> B[Documentos]
  B --> C[Compulsa]
  C --> D[Venta / Autorización]
  D --> E[Relación contratos / Cierre]
```

### 1. Pedido → Caso

- Vendedor inicia caso (web o Telegram según canal)
- Folio temporal / oficial asignado
- Semana activa (`SEMANA_ACTIVA` / auto ISO)

### 2. Documentos

- Carga INE, comprobantes, talón, etc.
- Ruta local: `storage/cases/{year}/SEM_*/{seller}/FOLIO_*/documents/`
- Opcional: cola SharePoint (`upload_status`, retry job)

### 3. Compulsa

- Estados workflow hacia compulsa
- Recordatorios bot (`compulsa_reminder_job`)
- Chat compulsa si `CHAT_ID_COMPULSAS` configurado

### 4. Venta / Autorización

- Revisión talón, autorizaciones comerciales
- Rutas web: `revision_talon`, `authorizations`, `approved_authorizations`, `sales`

### 5. Relación de contratos / cierre

- Reportes comerciales, conciliación, comisiones según módulo activo
- ERP/BI si habilitado en entorno

## Checklist manual E2E (staging)

| # | Paso | Esperado |
|---|------|----------|
| 1 | Login web usuario vendedor | Dashboard carga |
| 2 | Crear o abrir caso de prueba | Folio visible |
| 3 | Subir 1 documento PDF | Archivo en listado, path en BD |
| 4 | Avanzar estado hacia compulsa | Sin error 500 |
| 5 | Rol revisión/autorización aprueba | Estado actualizado |
| 6 | Registrar venta o cierre según flujo | Datos persistidos |
| 7 | Consultar reporte o lista contratos | Coherente con caso |
| 8 | `/health/full` | 200 o 503 documentado |
| 9 | Backup post-prueba | `backup_staging.sh` OK |

## Smoke automatizado (sin servicios externos)

Tests en `tests/test_p79_e2e_business_flow.py`:

- Rutas críticas registradas en `web_app`
- Docs P79 presente
- Health liveness OK

No ejecuta Telegram ni Graph real en CI.

## Telegram E2E (manual)

- [ ] `/start` responde
- [ ] Envío foto/documento asociado a flujo pedido
- [ ] Callback compulsa si aplica

## Referencias

- `docs/P24_DOCUMENTS.md`
- `docs/P71_STAGING_DEPLOY.md`
- `scripts/smoke_check_web.py` (P69)
