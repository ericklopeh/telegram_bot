# P82 — Real data QA validation

Validación con **datos reales de negocio** antes de producción completa.

## Checklist QA general

- [ ] Entorno staging con `.env` real (fuera del repo)
- [ ] Usuarios por rol: admin, supervisor, vendedor, readonly
- [ ] Backup previo (`scripts/backup_staging.sh`)
- [ ] `GET /health/full` → 200 o 503 documentado
- [ ] Ejecutar `python -m pytest -q` en CI verde

## Casos de negocio

### Mueble

| Paso | Validación |
|------|------------|
| Crear pedido/caso mueble | Folio y semana correctos |
| Subir pedido + orden + carátula | Checklist verde |
| Generar autorización | PDF SNTE en storage/SharePoint |
| Compulsa | Estado `EN_COMPULSA` |
| Venta vinculada | Excel ventas generado |

### Préstamo

| Paso | Validación |
|------|------------|
| Tipo préstamo en captura | Campos obligatorios |
| Documentos específicos | Sin error upload |
| Timeline | Eventos en detalle caso |

### Refinanciamiento

| Paso | Validación |
|------|------------|
| Flujo refinanciamiento | Autorización refi generada |
| Contrato/financiero | Coherencia montos |

### Rechazo

| Paso | Validación |
|------|------------|
| Rechazar en revisión/autorización | Estado y motivo persistidos |
| Vendedor no puede re-aprobar sin permiso | RBAC P81 |

### Corrección

| Paso | Validación |
|------|------------|
| Estado corrección pedido | Re-subida documento permitida |
| Historial | Case events actualizados |

## Validación transversal

| Área | Qué revisar |
|------|-------------|
| Excel generado | Abre en Excel, hojas y fórmulas |
| PDF generado | Legible, folio correcto |
| Storage local | Ruta `storage/cases/.../documents/` |
| SharePoint | `sharepoint_web_url` si Graph configurado |
| Relación contratos | Export contratos y vínculo caso |
| Ventas | Registro definitivo y descarga RBAC |
| Timeline | Orden cronológico eventos |
| Estados | Workflow coherente con checklist |

## Matriz de errores esperados

| Error | Causa esperada | Acción |
|-------|----------------|--------|
| 403 dashboard | RBAC readonly | Usar rol correcto |
| Upload rechazado | Checklist o permiso CREATE | Completar docs previos |
| 503 /health/full | Graph o storage | Config env o ignorar en QA parcial |
| Export no disponible | Sin permiso EXPORT | Supervisor/admin |
| SharePoint PENDING | Graph caído | Retry job / manual |
| Telegram sin respuesta | Polling vs webhook | Ver P74 |

## Rollback manual QA

1. Restaurar BD: `scripts/restore_db.sh` + dump previo
2. Revertir código: deploy P72 con `git_ref` anterior
3. Limpiar casos de prueba en staging si aplica

## Referencias

- `docs/P79_E2E_BUSINESS_FLOW.md`
- `docs/P81_RBAC_AND_AUDIT.md`
