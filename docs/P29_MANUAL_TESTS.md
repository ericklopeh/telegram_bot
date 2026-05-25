# P29 — Pruebas manuales BI

## 1. Acceso y navegación

1. Iniciar sesión (admin o vendedor).
2. Verificar enlaces en navbar: **BI Dashboard**, **Reportes BI**, **Alertas operativas**.
3. Abrir `/bi/dashboard` y confirmar carga sin error 500.

## 2. KPIs y drill-down

1. Revisar tarjetas superiores (ventas, saldo, recovery, comisiones, etc.).
2. Clic en **Ventas totales** → debe ir a `/ventas` con filtros si aplican.
3. Clic en **Saldo pendiente** → `/erp/dashboard`.
4. Clic en **Casos atorados** → `/dashboard?filter=stale_24h`.

## 3. Filtros globales

1. Elegir vendedor y semana → **Aplicar**.
2. Confirmar que KPIs y gráficas cambian.
3. **Limpiar** y verificar restablecimiento.

## 4. Gráficas

1. Validar barras en ventas por vendedor/semana/sección/tipo.
2. Validar doughnut SharePoint (OK / Fallidos / Otros).
3. Validar recovery por vendedor (barras %).

## 5. Rankings

1. Revisar top vendedores, recovery, pendientes, refinanciado.
2. Clic en fila → navegación a ventas, comisiones, ERP o cliente.

## 6. Alertas operativas

1. Ir a `/bi/alertas` o pestaña Alertas.
2. Verificar filas: sin comisión, SharePoint fallido, Excel fallido, etc. si hay datos.
3. Clic **Ver** en cada alerta.

## 7. Exportaciones BI

1. Pestaña **Reportes BI** o sección exports.
2. Generar cada Excel (resumen, vendedor, recovery, pendientes).
3. Confirmar mensaje de éxito con nombre de archivo.
4. Verificar archivos en `storage/excel_exports/bi/`.
5. Confirmar que **no** hay escritura en `storage/excel_masters/`.

## 8. Regresión P19–P27

- `/dashboard`, `/ventas`, `/erp/dashboard`, documentos, SharePoint, comisiones operativos.
