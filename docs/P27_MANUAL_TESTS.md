# P27 — Pruebas manuales ERP

## Pre-requisitos

- Migración `i5j6k7l8m9n0` aplicada.
- Usuario admin o sistemas para conciliación y exports.

## 1. Dashboard ERP

1. Iniciar sesión en la web.
2. Ir a **ERP** en el menú o `/erp/dashboard`.
3. Verificar tarjetas: contratos activos, saldo total, refinanciado, recovery.
4. Buscar un cliente por nombre o RFC (mínimo 2 caracteres).
5. Abrir un resultado y confirmar redirección a `/clientes/{id}`.

## 2. Vista cliente

1. Desde búsqueda o enlace directo, abrir `/clientes/{id}`.
2. Verificar tabla de contratos (venta, pagado, saldo, recovery).
3. Revisar lista de pagos y documentos (si hay `case_id` vinculado).
4. Confirmar timeline con eventos financieros si existen.

## 3. Conciliación

1. Como admin/sistemas, ir a `/erp/conciliacion`.
2. Revisar tabla de issues (o mensaje sin inconsistencias).
3. Exportar Excel y confirmar archivo bajo `storage/excel_exports/erp/`.

## 4. Exportaciones

Desde dashboard ERP (admin/sistemas):

- Export ejecutivo
- Export cobranza
- Export vendedores / recovery / refin (POST)

Confirmar que **no** se crean archivos en `storage/excel_masters/`.

## 5. Registro financiero (opcional API/servicio)

- Registrar pago vía `ContractFinancialService.register_payment`.
- Crear refin vía `create_refinance`.
- Verificar eventos en timeline del caso vinculado.

## 6. Regresión P19–P25.1

- `/dashboard`, `/casos`, `/ventas`, documentos P24, SharePoint P25 siguen operativos.
- Exports comerciales previos sin cambios de ruta.
