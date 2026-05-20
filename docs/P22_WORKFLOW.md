# P22 — Máquina de estados y dependencias operativas

## Flujo objetivo

```
PEDIDO_RECIBIDO → OCR_PROCESADO → PREP_AUTORIZACION → EN_COMPULSA
→ APROBADO → SNTE_PENDIENTE → SNTE_GENERADO → SHAREPOINT_PENDIENTE
→ SHAREPOINT_OK → REGISTRO_PENDIENTE → REGISTRADO → CONTRATOS_PENDIENTE
→ CONTRATOS_OK → COMISION_PENDIENTE → COMISION_OK → CERRADO
```

Ramas: `CORRECCION`, `RECHAZADO` desde compulsa.

## Regla SNTE

- **No** generar SNTE en `PREP_AUTORIZACION` ni antes de `APROBADO`.
- SNTE habilitado solo con workflow `APROBADO` o `SNTE_PENDIENTE` (tras compulsa/aprobación).
- Evento `SNTE_UNLOCKED_AFTER_APPROVAL` al pasar a `SNTE_PENDIENTE`.

## Servicios

| Servicio | Rol |
|----------|-----|
| `workflow_state_service.py` | Constantes, etiquetas, mapeo legacy |
| `workflow_transition_service.py` | Transiciones permitidas y recálculo |
| `workflow_dependency_service.py` | Dependencias por estado y acciones |
| `workflow_visualization.py` | Pipeline visual web |

## Compatibilidad

- `cases.current_status` / `visible_status` se sincronizan al recalcular o transicionar.
- Dashboards existentes siguen usando estados legacy mapeados.

## Rutas

- `POST /casos/{id}/recalcular-estado` — admin/sistemas
- `POST /casos/{id}/workflow/transition` — admin/sistemas
- `GET /admin/workflow` — documentación operativa y últimos bloqueos

## Campo BD

- `cases.workflow_state` (migración `f2a3b4c5d6e7`)
