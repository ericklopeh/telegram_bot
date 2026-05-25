# P27 — Consolidación ERP operacional/comercial

## Objetivo

Centralizar contratos, pagos, refinanciamientos, saldos, cobranza, historial de cliente, conciliación y KPIs reutilizando tablas históricas sin duplicar lógica paralela.

## Modelos

| Tabla | Modelo | Uso |
|-------|--------|-----|
| `customers_customer` | `ErpCustomer` | Cliente consolidado |
| `sales_sale` | `ErpSale` | Venta histórica |
| `sales_saleitem` | `ErpSaleItem` | Partidas |
| `payments_payment` | `ErpPayment` | Pagos |
| `payments_installment` | `ErpInstallment` | Cuotas origen |
| `contracts` | `Contract` | Contrato consolidado |
| `contract_installments` | `ContractInstallment` | Cuotas contrato |
| `refinance_operations` | `RefinanceOperation` | Refinanciamientos |

## Servicios

- `ContractFinancialService` — saldo, recovery, pagos, refin.
- `ErpConsolidationService` — vincula `sale_captures` y ventas ERP a contratos.
- `ErpReconciliationService` — inconsistencias (saldos negativos, pagos huérfanos, refin duplicado, etc.).
- `ErpSearchService` — búsqueda por nombre, RFC, CURP, folio, contrato.
- `ErpExportService` — Excel solo en `storage/excel_exports/erp/`.

## Rutas web

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/erp/dashboard` | KPIs, búsqueda, pagos recientes |
| GET | `/erp/conciliacion` | Conciliación (admin/sistemas) |
| GET | `/clientes/{id}` | Vista cliente consolidada |
| POST | `/erp/export/*` | Ejecutivo, cobranza, vendedores, recovery, refin, conciliación |

## Timeline financiero

Eventos: `PAYMENT_REGISTERED`, `REFINANCE_CREATED`, `BALANCE_ADJUSTED`, `CONTRACT_CLOSED`.

## Migración

`i5j6k7l8m9n0_p27_erp_consolidation.py` (revises `h4i5j6k7l8m9`).

```bash
docker compose exec web alembic upgrade head
```

## Protecciones

- No escribe en `storage/excel_masters/`.
- Mantiene P19–P25.1 (casos, workflow, documentos, SharePoint, comisiones, exports previos).

## Pruebas

```bash
python -m pytest tests/test_p27_erp.py -q
python -m pytest -q
```
