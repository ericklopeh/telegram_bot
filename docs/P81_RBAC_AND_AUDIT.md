# P81 — Advanced permissions and RBAC

Control de permisos por **acción** con auditoría en `audit_entries` (ComplianceService).

## Perfiles RBAC

| Perfil | Roles BD mapeados |
|--------|-------------------|
| **admin** | `admin`, `sistemas` |
| **supervisor** | `supervisor`, `autorizacion`, `autorizaciones`, `compras`, `compulsa` |
| **vendedor** | `vendedor` |
| **readonly** | `consulta`, `readonly` |

## Permisos por acción

| Permiso | admin | supervisor | vendedor | readonly |
|---------|:-----:|:----------:|:--------:|:--------:|
| create | ✓ | ✓ | ✓ | |
| edit | ✓ | ✓ | ✓ | |
| approve | ✓ | ✓ | | |
| compulsa | ✓ | ✓ | | |
| export | ✓ | ✓ | | |
| delete | ✓ | | | |
| download | ✓ | ✓ | ✓ | ✓ |
| view_audit | ✓ | | | |

## Código central

| Módulo | Uso |
|--------|-----|
| `app/security/rbac.py` | Matriz y normalización de roles |
| `app/services/rbac_service.py` | `has_permission`, `record_audit` |
| `app/web/rbac_helpers.py` | `require_permission`, flags UI |
| `app/web/routes/rbac_admin.py` | `GET /admin/audit` |

## Guards en rutas (ejemplos)

- Subida documento → `Permission.CREATE`
- Ver/descargar documento → `Permission.DOWNLOAD`
- Generar autorización SNTE → `Permission.APPROVE`
- Descargar Excel ventas → `Permission.EXPORT`
- Ventas UI → overlay en `sale_action_guard_service`

## Bloqueo visual (Jinja)

```jinja
{% if rbac_can(request, 'export') %}
  <a href="...">Descargar</a>
{% endif %}
```

`request.state.rbac_flags` se llena en middleware (`app/web/main.py`).

## Auditoría

Cada denegación y subidas críticas registran fila en `audit_entries`:

- `actor_label`: `user:{id}:{username} ({rol}/{perfil})`
- `action`, `entity_type`, `entity_id`
- `after_json`: `{allowed, permission, detail}`

Consulta: **Admin →** `/admin/audit` (requiere `view_audit`).

## Desarrollo local

`WEB_RBAC_RELAXED=true` en `.env` desactiva restricciones (como antes). **No usar en staging/producción.**

## Tests

```bash
python -m pytest -q tests/test_p81_rbac.py
```

## Compatibilidad

- Dashboards, ventas, Telegram y exports siguen operando; vendedor conserva alcance por caso propio.
- `require_roles` legacy coexiste con `require_permission` + `roles_fallback`.
