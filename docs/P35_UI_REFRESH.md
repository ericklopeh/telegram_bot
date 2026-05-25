# P35 — Renovación visual del dashboard operacional

## Objetivo

Rediseño híbrido del dashboard principal (`GET /dashboard`) inspirado en ERP modernos, centros de operaciones y dashboards SaaS, **sin cambiar lógica de negocio** ni rutas existentes.

## Decisiones visuales

| Área | Decisión |
|------|----------|
| Jerarquía | KPIs hero arriba → pipeline Kanban centro → centro de operaciones → detalle colapsable |
| Densidad | Menos cards pequeñas duplicadas; chips compactos para métricas secundarias |
| Navegación | Sidebar agrupada (Operación, ERP, BI, Recovery, Admin) + tabs de módulo |
| Tema | Dark sidebar + contenido claro; sombras y spacing ampliados (P35) |
| Animaciones | Hover en cards, pulse en SLA crítico, transiciones CSS ligeras |

## Layout nuevo (P35 denso)

```
┌─────────────────────────────────────────────────────────┐
│ Sidebar │ Tabs · Hero KPIs (6) · Pipeline Kanban       │
│         │ Ops tabla compacta · strip P16               │
│         │ Gráficas 2×2 + SLA inline                    │
│         │ Casos recientes │ Timeline actividad         │
│         │ Tablas P14 / vendedores / estados            │
└─────────────────────────────────────────────────────────┘
```

## Secciones

1. **Hero KPIs** — `build_hero_kpis()` en `dashboard_ui_service.py`
2. **Pipeline operacional** — `build_pipeline_columns()` (PREP AUT → COMISIÓN)
3. **Centro de operaciones** — `build_ops_center_items()` + alertas P16 (top 6)
4. **Detalle operativo** — SLA, distribución por estado, seguimiento P14, vendedores, por estado interno (sin cambios de datos)

## Componentes reutilizables

| Partial | Uso |
|---------|-----|
| `partials/dash_sidebar_p35.html` | Sidebar agrupada |
| `partials/dash_module_tabs.html` | Tabs Operación / ERP / BI / Recovery |
| `partials/dash_hero_kpis.html` | KPIs ejecutivos |
| `partials/dash_workflow_kanban.html` | Pipeline horizontal |
| `partials/dash_ops_center.html` | Alertas operativas |

Servicio de presentación: `app/web/services/dashboard_ui_service.py`

Estilos: `app/web/static/css/dashboard.css` (bloque `/* P35 UI refresh */`)

## Rutas principales

| Ruta | Descripción |
|------|-------------|
| `/dashboard` | Dashboard renovado P35 |
| `/erp/dashboard` | ERP (tab) |
| `/bi/dashboard` | BI (tab) |
| `/ops` | Recovery (tab + badge incidentes) |

`GET /` sigue redirigiendo según flujo existente (no modificado).

## Compatibilidad

- Métricas: mismas fuentes en `dashboard.py` (`_build_metrics`, P14, P16)
- Filtros `?filter=` en tabla de pendientes: intactos
- No se modificó `excel_masters`, workflow ERP ni SharePoint

## Pulido visual (P35 polish)

- KPIs con fondo degradado por severidad, iconos destacados y mini-tendencias.
- Pipeline Kanban con header de color por etapa, máx. 3 casos, badges SLA (24h+ / 12h+ / OK).
- Centro de ops en lista compacta (no cards gigantes) + chips resumen.
- Layout split: ops + gráficas 2×2 en la misma fila (desktop).
- Resumen P16 en grid de pills con número + etiqueta separados.
- Tabs estilo pill (sin links azules subrayados).

## Futuras mejoras

- Reutilizar sidebar P35 en `ops_dashboard.html` y paneles BI/ERP
- KPI ventas semana/QNA con datos reales del módulo comercial (hoy proxy: autorizaciones generadas)
- Gráficas BI embebidas en tab BI (vista dedicada `/bi/dashboard`)
- Modo compacto / personalización de columnas Kanban
- Soporte móvil refinado

## Verificación

```bash
python -m pytest tests/test_p35_ui.py -q
python -m pytest -q
```
