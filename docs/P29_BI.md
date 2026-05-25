# P29 — BI / Dashboard ejecutivo operacional

## Objetivo

Visualización ejecutiva para supervisión de ventas, conciliación ERP (P27), workflow, SharePoint y comisiones, sin duplicar la lógica financiera de contratos.

## Arquitectura

| Componente | Rol |
|------------|-----|
| `BiFilters` | Filtros globales (fecha, semana, QNA, vendedor, sección, tipo, workflow) |
| `BiDashboardService` | KPIs, gráficas, rankings, alertas; delega saldos/recovery a `ContractFinancialService` |
| `BiExportService` | Excel en `storage/excel_exports/bi/` |
| `app/web/routes/bi.py` | Rutas HTTP |

## KPIs superiores

- Ventas totales / semana / QNA (desde `sale_captures` registradas)
- Saldo pendiente, recovery %, refinanciado (ERP P27)
- Comisiones, documentos pendientes, SharePoint fallidos, casos atorados >24h

## Gráficas (Chart.js)

- Ventas por vendedor, semana, sección, tipo
- Workflow por estado
- SharePoint OK vs fallidos vs otros
- Recovery % por vendedor (contratos activos ERP)

## Rutas

| Método | Ruta |
|--------|------|
| GET | `/bi/dashboard` |
| GET | `/bi/reportes` → tab reportes |
| GET | `/bi/alertas` → tab alertas |
| POST | `/bi/export/resumen` |
| POST | `/bi/export/ventas_vendedor` |
| POST | `/bi/export/recovery` |
| POST | `/bi/export/pendientes` |

## Exports

Archivos bajo `storage/excel_exports/bi/`:

- `dashboard_resumen_*.xlsx`
- `ventas_vendedor_*.xlsx`
- `recovery_*.xlsx`
- `pendientes_*.xlsx`

## Eventos

- `BI_REPORT_EXPORTED` — log al exportar
- `BI_DASHBOARD_VIEWED` — log de acceso (logger, no case_events masivo)

## Rendimiento

- Agregaciones SQL (`GROUP BY`, `SUM`)
- Caché en memoria 45s por combinación de filtros (`BiDashboardService.build_dashboard`)
- Contratos ERP: una pasada con `joinedload` para recovery por vendedor

## Migraciones

No requiere migración (solo lectura de tablas existentes).

## Pruebas

```bash
python -m pytest tests/test_p29_bi.py -q
python -m pytest -q
```

## Limitaciones actuales

- Sin RBAC estricto (acceso amplio para demo interna).
- Recovery por vendedor recalcula snapshots por contrato activo (coste acotado + caché).
- Filtros de fecha en casos usan `created_at`; ventas usan `sale_date`.
- P26 OCR y P28 permisos siguen pausados.

## Troubleshooting

| Síntoma | Acción |
|---------|--------|
| KPIs ERP en cero | Verificar tablas P27 y migración `i5j6k7l8m9n0` |
| Gráficas vacías | Revisar ventas con `registration_status=registered` |
| Export bloqueado | Confirmar ruta bajo `excel_exports`, no `excel_masters` |
| Datos “viejos” tras cambio | Esperar 45s o reiniciar web (caché BI) |
