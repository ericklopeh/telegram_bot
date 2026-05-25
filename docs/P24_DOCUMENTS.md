# P24 — Gestión documental avanzada

## Resumen

Cada pedido/caso gestiona documentos con **revisión**, **versionado**, **checklist por tipo de venta** e integración con el **workflow P22**. Los archivos se guardan bajo `storage/cases/` (nunca en `storage/excel_masters/`).

## Modelo de datos

Se extendió la tabla existente **`documents`** (modelo `Document`, alias `CaseDocument` en código). No se creó `case_documents` para evitar duplicar la lógica de SharePoint, OCR y ActionGuard.

### Campos P24 añadidos

| Campo | Descripción |
|-------|-------------|
| `review_status` | `PENDING_REVIEW`, `VALID`, `INVALID`, `REPLACED` |
| `version` | Número de versión por reemplazo |
| `size_bytes` | Tamaño del archivo |
| `uploaded_by` / `validated_by` / `validated_at` | Auditoría humana |
| `rejection_reason` | Motivo si `INVALID` |
| `ocr_status` | `OCR_PENDING`, `OCR_DONE`, `OCR_FAILED` (sin motor OCR aún) |
| `ocr_extracted_data` | JSON preparado |
| `ocr_confidence` | Float preparado |
| `created_at` / `updated_at` | Marcas de tiempo |

`file_path` equivale a `storage_path` (propiedad `storage_path` en el modelo).

## Tipos de documento

| Constante | Uso |
|-----------|-----|
| `pedido` | DOC_PEDIDO |
| `orden_descuento` | DOC_ORDEN_DESCUENTO |
| `autorizacion_snte` | DOC_AUTORIZACION_SNTE (mueble) |
| `orden_snte_pdf` | DOC_ORDEN_SNTE_PDF (préstamo) |
| `autorizacion_refi` | Refinanciamiento |
| `caratula_bancaria` | Legacy préstamo (checklist antiguo) |
| `ine` / `estado_cuenta` / `otro` | Opcionales |

## Checklist obligatorio (workflow P24)

- **Mueble:** pedido, orden de descuento, autorización SNTE (Excel).
- **Préstamo:** pedido, orden de descuento, orden SNTE PDF.
- **Con refinanciamiento:** pedido, orden de descuento, orden SNTE PDF, autorización refi.

Para avanzar a estados como `PREP_AUTORIZACION`, `EN_COMPULSA`, `APROBADO`, `SHAREPOINT_OK`, `REGISTRO_*` los tipos requeridos deben estar **presentes y en estado `VALID`**.

## Storage local

```
storage/cases/{year}/SEM_{week}/{seller_safe}/FOLIO_{folio}_{cliente_safe}/documents/
```

Nombres sanitizados; archivos con timestamp y versión para evitar sobrescritura.

## Servicio

`app/services/case_document_service.py`

- `upload_document`, `replace_document`, `validate_document`, `reject_document`
- `build_checklist`, `missing_required_types`, `missing_valid_types`
- `assert_workflow_documents` / `missing_for_workflow_target`

## Rutas web

| Método | Ruta (español) | Alias inglés |
|--------|----------------|--------------|
| GET | `/casos/{id}/documentos` | `/cases/{id}/documents` |
| POST | `/casos/{id}/documentos/upload` | `/cases/{id}/documents/upload` |
| POST | `/casos/{id}/documentos/{doc_id}/validate` | `.../validate` |
| POST | `/casos/{id}/documentos/{doc_id}/reject` | `.../reject` |
| POST | `/casos/{id}/documentos/{doc_id}/replace` | `.../replace` |

Vista: `case_documents.html`. Resumen en detalle de caso → botón **Gestionar documentos**.

## Eventos de timeline

| Evento | Significado |
|--------|-------------|
| `CASE_DOCUMENT_UPLOADED` | Carga P24 |
| `CASE_DOCUMENT_REPLACED` | Reemplazo versionado |
| `CASE_DOCUMENT_VALIDATED` | Aprobación revisión |
| `CASE_DOCUMENT_REJECTED` | Rechazo con motivo |
| `DOCUMENT_MISSING_BLOCKED` | Bloqueo workflow por faltantes |

(`DOCUMENT_UPLOADED` sigue reservado para sincronización SharePoint.)

## Migración

```bash
docker compose exec web alembic upgrade head
```

Revisión: `g3h4i5j6k7l8` (después de `f2a3b4c5d6e7`).

## Upload legacy (P24.1)

`POST /casos/{id}/upload-document` delega en `upload_document_legacy_web` (misma storage y eventos P24). Detalle: [P24_1_LEGACY_UPLOAD.md](P24_1_LEGACY_UPLOAD.md).

## Compatibilidad P19–P23

- Rutas `/ventas` sin cambios.
- Maestros Excel: solo lectura en `storage/excel_masters/`.
- Exports Excel: solo `storage/excel_exports/`.
- Workflow P22: dependencias enriquecidas con checklist P24 en `workflow_transition_service`.
