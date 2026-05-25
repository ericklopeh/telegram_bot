# P60 — Multi-tenant SaaS

- Modelos: `tenant_settings`, `tenant_storage_paths` (ligados a `companies`)
- Servicio: `app/services/saas_tenant_service.py`
- Aislamiento lógico por `company_id`; storage `storage/tenants/{id}/`
- Panel: `/admin/tenants`
- Compatible con instalación single-tenant (slug `default`).
