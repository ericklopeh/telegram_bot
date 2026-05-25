# P24 — Pruebas manuales (gestión documental)

## Preparación

```bash
docker compose exec web alembic upgrade head
docker compose restart web
docker compose exec web pytest -q
```

Abrir `http://localhost:8010` (o el puerto configurado).

## 1. Checklist mueble

1. Iniciar sesión como admin o vendedor dueño del caso.
2. Abrir un **pedido mueble** en `/casos/{id}`.
3. Clic en **Gestionar documentos** → `/casos/{id}/documentos`.
4. Verificar checklist: Pedido, Orden de descuento, Autorización SNTE.
5. Subir solo el pedido → resumen: 1 pendiente, 2 faltantes.
6. Validar el pedido (rol admin/autorización/compras) → contador “Completos” sube.

## 2. Checklist préstamo

1. Caso `order_type=prestamo`.
2. Checklist debe pedir **Orden SNTE PDF** en lugar de Excel SNTE.
3. Subir los tres tipos y validarlos.

## 3. Rechazo y reemplazo

1. Rechazar un documento con motivo “ilegible”.
2. Comprobar badge **INVALID** y motivo visible.
3. **Reemplazar** con otro PDF → nueva versión y evento en timeline del caso.

## 4. Bloqueo workflow

1. Caso pedido sin documentos validados.
2. Intentar transición manual a **EN_COMPULSA** o **APROBADO** (formulario workflow en detalle).
3. Debe mostrar error con tipos faltantes y evento `DOCUMENT_MISSING_BLOCKED` en timeline.

## 5. SharePoint / rutas legacy (P24.1)

1. Subida desde detalle de caso (`/casos/{id}/upload-document`) guarda en `storage/cases/...` y aparece en gestión documental.
2. Subir el mismo tipo dos veces incrementa versión y registra reemplazo en timeline.
2. Vista detalle lista documentos y enlace `/documentos/{id}/ver`.

## 6. Seguridad Excel

1. Tras subir documentos, confirmar que **no** aparecen archivos nuevos en `storage/excel_masters/`.
2. Solo bajo `storage/cases/.../documents/`.

## 7. Pruebas automatizadas

```bash
docker compose exec web pytest -q tests/test_p24_case_documents.py
```

Cubre: rutas storage, checklist mueble/préstamo/refi, upload/validate/reject/replace, bloqueo, eventos (mocks).
