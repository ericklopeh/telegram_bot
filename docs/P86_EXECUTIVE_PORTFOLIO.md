# P86 — Executive portfolio and CV packaging

Caso de éxito profesional — **Sistema Gaman** (español + bullets CV en inglés).

---

## Arquitectura (high-level)

Monolito modular **FastAPI + Jinja + PostgreSQL + Docker**, bot **Telegram** operativo, integración **Microsoft Graph/SharePoint**, jobs en background, observabilidad P70, RBAC P81, CI/CD staging P72.

```text
[Telegram / Web] → [FastAPI] → [Services] → [PostgreSQL]
                      ↓              ↓
                 [Storage local]  [SharePoint]
                      ↓
                 [Workers / Jobs / Redis opcional]
```

## Stack tecnológico

| Capa | Tecnología |
|------|------------|
| Backend | Python 3.11+, FastAPI, SQLAlchemy, Alembic |
| Frontend | Jinja2, Bootstrap |
| Bot | python-telegram-bot 22.x |
| Datos | PostgreSQL 16 |
| Infra | Docker Compose, Nginx, GitHub Actions |
| Integraciones | MS Graph, Prometheus metrics, Sentry opcional |

## Flujo E2E negocio

Pedido → documentos → compulsa → autorización SNTE → venta → relación contratos / Excel, con timeline y auditoría.

## Impacto esperado

| Área | Beneficio |
|------|-----------|
| Retrabajo | Checklist y guards reducen subidas inválidas |
| Automatización | Bot + jobs compulsa/SharePoint/SLA |
| Trazabilidad | case_events + audit_entries RBAC |
| Documentación | Rutas semana/vendedor/folio + SharePoint |

## Métricas estimadas (post go-live)

- **−30–50%** tiempo búsqueda documentos (centralización)
- **−20%** rechazos por checklist incompleto (guards)
- **99%+** uptime objetivo en horario laboral (`/health`)
- **< 5%** uploads fallidos tras estabilización SharePoint

---

## CV bullet points — English

**Data Engineer**

- Designed PostgreSQL schemas and Alembic migrations for an operational lending/furniture workflow platform with full audit trails.
- Built structured document storage paths (`year/week/seller/folio`) and SharePoint Graph integration with retry jobs.
- Implemented backup/restore procedures and staging QA checklists for real business data validation.

**Automation Engineer**

- Delivered Telegram bot flows (polling + webhook-ready) for order capture, compulsa reminders, and SLA watchdog jobs.
- Automated GitHub Actions staging deploy with secret validation, full test suite, and post-deploy health smoke.
- Reduced manual ops via Docker Compose stacks for dev, staging, and production profiles.

**Backend Engineer**

- Built FastAPI web platform with enterprise RBAC (action-level permissions), compliance audit log, and rate-limited production middleware.
- Integrated sale capture, authorization PDF generation, OCR hooks, and Excel export pipelines without breaking legacy flows.
- Exposed Prometheus metrics, liveness/readiness health endpoints, and pilot-to-production rollout documentation.

---

## CV bullet points — Español

**Ingeniero de datos:** modelado PostgreSQL, migraciones Alembic, rutas documentales e integración SharePoint con reintentos.

**Ingeniero de automatización:** bot Telegram 24/7, CI/CD staging, jobs de compulsa y despliegue smoke automatizado.

**Backend:** FastAPI, RBAC por acción, auditoría, captura de ventas, exports Excel y preparación go-live enterprise.

---

## Referencias internas

- `docs/P79_E2E_BUSINESS_FLOW.md`
- `docs/P81_RBAC_AND_AUDIT.md`
- `docs/P85_PRODUCTION_ROLLOUT.md`
