# P23 — Flujo end-to-end operativo (hardening)

Documento de verificación manual del flujo completo P19–P22 en rama `feature/web-demo`.

## Prerrequisitos

- Docker: `docker compose up -d` (servicios `db` y `web`).
- Migraciones al día:

```bash
docker compose exec web alembic upgrade head
docker compose exec web alembic current   # debe mostrar f2a3b4c5d6e7 (head)
docker compose restart web
```

- Usuario **admin**, **sistemas** o **autorización** para registro, comisiones y workflow.
- Maestros presentes (solo lectura): `storage/excel_masters/ventas/` y `.../contratos/`.
- Anotar fecha/hora y tamaño de maestros **antes** del flujo (no deben cambiar al final).

## Flujo E2E (orden P22)

### 1. Caso / pedido — `PEDIDO_RECIBIDO`

| Paso | Acción | Verificación |
|------|--------|--------------|
| 1.1 | Crear caso pedido (web o Telegram) | Caso visible en `/casos` |
| 1.2 | Abrir `/casos/{id}` | Pipeline: **Pedido** = actual o completado |
| 1.3 | Workflow | `workflow_state` ≈ `PEDIDO_RECIBIDO` o recalcular |

### 2. Documentos mínimos — checklist

| Paso | Acción | Verificación |
|------|--------|--------------|
| 2.1 | Subir pedido, orden descuento, carátula (según tipo) | Checklist sin ❌ |
| 2.2 | Finalizar / enviar a preparación | `PREP_AUTORIZACION` o equivalente legacy |

### 3. OCR (si aplica)

| Paso | Acción | Verificación |
|------|--------|--------------|
| 3.1 | Procesar OCR en documentos elegibles | Timeline: `OCR_PROCESSED` |
| 3.2 | Pipeline | Paso **OCR** completado |

### 4. Compulsa y aprobación — `APROBADO`

| Paso | Acción | Verificación |
|------|--------|--------------|
| 4.1 | Enviar a compulsa (admin/sistemas) | `EN_COMPULSA` |
| 4.2 | Aprobar compulsa | `APROBADO` / `Compulsa OK` |
| 4.3 | Timeline | `COMPULSA_APPROVED` si aplica |

### 5. SNTE solo tras APROBADO (regla crítica)

| Paso | Acción | Verificación |
|------|--------|--------------|
| 5.1 | **Antes** de aprobar: abrir caso en `PREP_AUTORIZACION` | Botón **Generar SNTE** deshabilitado o mensaje que exige APROBADO |
| 5.2 | **Después** de aprobar | Botón SNTE visible (ActionGuard) |
| 5.3 | Generar autorización SNTE | Excel + PDF en EVIDENCIAS del caso |
| 5.4 | Timeline | `SNTE_GENERADO`, opcional `SNTE_UNLOCKED_AFTER_APPROVAL` |
| 5.5 | Pipeline | Paso **SNTE** completado |

### 6. SharePoint — `SHAREPOINT_OK`

| Paso | Acción | Verificación |
|------|--------|--------------|
| 6.1 | Documentos críticos con estado `UPLOADED` | Sin `UPLOAD_FAILED` bloqueantes |
| 6.2 | Recalcular estado (admin) | `SHAREPOINT_OK` si dependencias OK |
| 6.3 | Pipeline | Paso **SharePoint** completado |

### 7. Registro venta Excel — cola P20

| Paso | Acción | Verificación |
|------|--------|--------------|
| 7.1 | `/ventas/nueva` vinculado al caso (`?case_id=`) o captura existente | Checklist venta OK |
| 7.2 | **Sin** SharePoint OK: botón Registrar no debe habilitarse | Mensaje menciona `SHAREPOINT_OK` |
| 7.3 | Con SharePoint OK: **Registrar definitivo** | Cola: `QUEUED` → `PROCESSING` → `REGISTERED` |
| 7.4 | Timeline caso | `SALE_CAPTURE_REGISTRATION_QUEUED`, `PROCESSING`, `REGISTERED` |
| 7.5 | Archivos export | Solo bajo `storage/excel_exports/operations/{sale_id}/` y `daily/` |
| 7.6 | Descargas | `/ventas/{id}/descargar/ventas` y `/contratos` funcionan |

### 8. Comisión automática — P21

| Paso | Acción | Verificación |
|------|--------|--------------|
| 8.1 | Tras registro exitoso | `/comisiones` muestra fila `pending` |
| 8.2 | Porcentaje | 46% general; 60% si vendedor Juan Manuel |
| 8.2 | Timeline | `COMMISSION_CREATED` |
| 8.3 | Sin duplicar | Una comisión por `sale_capture_id` |

### 9. Cierre operativo (opcional)

| Paso | Acción | Verificación |
|------|--------|--------------|
| 9.1 | Marcar comisión pagada | `COMMISSION_PAID` en timeline |
| 9.2 | Recalcular → `CERRADO` si todas las dependencias finales OK | Pipeline **Cerrado** |

## Verificación de maestros Excel (obligatorio)

```powershell
# PowerShell — antes y después del flujo
Get-Item storage\excel_masters\ventas\*.xlsx | Select Name, Length, LastWriteTime
Get-Item storage\excel_masters\contratos\*.xlsx | Select Name, Length, LastWriteTime
```

| Check | Esperado |
|-------|----------|
| Maestros | Sin cambio de tamaño/fecha tras registro |
| Nuevos archivos | Solo en `storage/excel_exports/` |
| `commercial_report` (P18) | Solo **lectura** de maestros |

## Rutas que no deben romperse

- `GET /ventas`
- `GET` / `POST /ventas/nueva`
- `GET /ventas/{id}`
- `GET /ventas/{id}/descargar/ventas`
- `GET /ventas/{id}/descargar/contratos`

## Vistas adicionales P20–P22

| Ruta | Rol | Qué validar |
|------|-----|-------------|
| `/ventas/pendientes` | admin/sistemas/autorización | Errores de registro y reintento |
| `/control/conciliacion` | admin/sistemas/autorización | Inconsistencias BD vs archivos |
| `/comisiones` | según alcance | Dashboard y export Excel/PDF |
| `/admin/workflow` | admin/sistemas | Transiciones y bloqueos recientes |

## Automatizado (P23)

```bash
python -m pytest -q
docker compose run --rm web python scripts/smoke_check.py
```

Tests relevantes:

- `tests/test_excel_masters_safety.py`
- `tests/test_p23_registration_commission_chain.py`
- `tests/test_p23_workflow_register_gate.py`

## Checklist final

- [ ] SNTE bloqueado antes de APROBADO
- [ ] SNTE generado después de APROBADO
- [ ] Registro bloqueado sin SharePoint OK
- [ ] Registro OK con SharePoint OK
- [ ] Comisión creada sin duplicar
- [ ] Maestros Excel intactos
- [ ] Dashboard carga sin error `workflow_state`
- [ ] Pipeline visual coherente en caso y venta
- [ ] Timeline con eventos de venta, comisión y workflow
- [ ] `pytest -q` en verde

## Commit sugerido (solo P23)

```
docs(test): P23 hardening E2E y pruebas de seguridad Excel
```
