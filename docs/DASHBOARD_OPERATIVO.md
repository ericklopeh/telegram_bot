# Dashboard operativo (Fase 11)

Vista web en `/dashboard` que concentra métricas del flujo de casos, pendientes operativos, resumen por vendedor e indicadores de tiempo (SLA aproximado). Implementación principal: `app/web/routes/dashboard.py` y plantilla `app/web/templates/dashboard.html`.

---

## Métricas disponibles (tarjetas superiores)

Todas se calculan sobre casos visibles según el rol (ver [Visibilidad por rol](#reglas-de-visibilidad-por-rol)).

| Métrica | Significado breve |
|--------|-------------------|
| **Casos abiertos** | Casos cuyo `current_status` **no** está en el conjunto operativo de “cerrados” (ver código: `_CERRADOS_OPERATIVOS` en `dashboard.py`). |
| **Pendientes de autorización** | Casos en estado de preparación de autorización (`ST_PED_PREP_AUT`). |
| **Autorizaciones generadas** | Casos en `ST_PED_AUT_GENERADA`. |
| **Pendientes de compulsa** | Casos en `ST_PED_PEND_COMPULSA`. |
| **Compulsa OK** | Casos en `ST_PED_COMPULSA_OK`. |
| **Prep. aut. sin Excel SNTE** | Pedidos en preparación de autorización **sin** documento activo de tipo autorización SNTE. |
| **Docs UPLOAD_FAILED** | Documentos activos con error de subida (SharePoint). |
| **Docs PENDING_UPLOAD** | Documentos activos con subida pendiente. |
| **Pedidos checklist incompleto** | Pedidos en recibido o corrección de pedido, con tipo de pedido definido, evaluados contra el checklist documental (hasta **150** casos más recientes por `updated_at`; si se alcanza el tope, la métrica puede subestimar y se marca “tope alcanzado”). |

**Casos por estado interno** (tabla inferior): conteo agrupado por `current_status` para los mismos casos visibles.

Los **nombres de estado** mostrados son los valores internos almacenados en base de datos; el detalle del flujo está en `app/domain/constants.py`.

---

## Filtros rápidos (pendientes operativos)

Los filtros son **solo enlaces HTTP** (sin JavaScript): query `filter` en la URL del dashboard.

| Valor de `filter` | URL de ejemplo | Efecto |
|-------------------|----------------|--------|
| *(omitido o inválido)* | `/dashboard` | Equivalente a **Todos** (`all`). |
| `all` | `/dashboard?filter=all` | Incluye todos los orígenes de pendientes descritos abajo. |
| `prep_aut` | `/dashboard?filter=prep_aut` | Solo casos en preparación de autorización. |
| `compulsa` | `/dashboard?filter=compulsa` | En compulsa o pendiente de compulsa. |
| `sp_pending` | `/dashboard?filter=sp_pending` | Casos con documento activo `PENDING_UPLOAD`. |
| `sp_failed` | `/dashboard?filter=sp_failed` | Casos con documento activo `UPLOAD_FAILED`. |
| `correction` | `/dashboard?filter=correction` | Corrección o rechazo (pedido o revisión). |
| `missing_docs` | `/dashboard?filter=missing_docs` | Pedidos con checklist incompleto (recibido/corrección). |

En la interfaz aparecen como “pills” que enlazan a estas URLs.

---

## Tabla de pendientes operativos

- **Objetivo:** listar casos con al menos un “problema” operativo deduplicado por caso.
- **Orden:** por `updated_at` del caso (más reciente primero).
- **Límite final de filas:** **30** (`_PENDING_TABLE_LIMIT`).
- **Por cada origen** (cada estado o consulta de documentos): como máximo **12** casos (`_PENDING_LIMIT_PER_SOURCE`) antes de deduplicar y ordenar. Por tanto, la tabla **no garantiza** exhaustividad de todos los pendientes del sistema, solo una ventana operativa manejable.
- **Faltan documentos del checklist:** se consideran hasta **40** pedidos más recientes en recibido/corrección; se evalúa el checklist vía servicio de dominio (puede implicar más trabajo por fila que un simple `COUNT`).

Si un caso encaja en varias categorías, en la columna de problema se concatenan las etiquetas separadas por ` · `.

---

## Resumen por vendedor

Tabla **“Resumen operativo por vendedor”** con agregados por `seller_name` del caso:

- Casos **abiertos** (misma noción de “no cerrados operativamente” que en las tarjetas).
- **Pendientes de autorización** (`ST_PED_PREP_AUT`).
- **Compulsa / pendiente compulsa** (`ST_PED_EN_COMPULSA`, `ST_PED_PEND_COMPULSA`).
- **Corrección / rechazados** (pedido y revisión: rechazados y corrección; ver `_CORRECCION_RECHAZO_STATUSES` en `dashboard.py`).
- **Documentos con error SharePoint:** documentos activos `UPLOAD_FAILED`, contados por vendedor del caso (una consulta con `JOIN` y `GROUP BY`, sin recorrer todos los documentos en Python).

**Roles no vendedor:** se listan hasta **25** vendedores con “actividad” (suma de contadores anteriores &gt; 0), ordenados priorizando más casos abiertos y luego mayor actividad total.

**Vendedor:** solo ve **una fila** con su `nombre` de usuario (debe coincidir con `Case.seller_name`); si no hay nombre en sesión, no se muestra filas.

---

## Métricas SLA / tiempo (&gt; 24 h y edad)

Segunda fila de tarjetas bajo el título **“Tiempo operativo / SLA (indicadores)”**. Se basan en **`updated_at`** y **`created_at`** del caso; **no** usan `CaseHistory` ni `CaseEvent`.

| Indicador | Criterio |
|-----------|----------|
| **Abiertos sin actualización &gt; 24 h** | Caso abierto operativamente y `updated_at` anterior a **ahora (UTC) − 24 h** al momento de cargar el dashboard. |
| **Prep. autorización &gt; 24 h** | `ST_PED_PREP_AUT` y `updated_at` anterior al mismo umbral. |
| **Compulsa / pend. compulsa &gt; 24 h** | Estados en compulsa o pendiente de compulsa y `updated_at` anterior al umbral. |
| **Edad media casos abiertos** | Promedio en horas de `now() − created_at` en SQL (`EXTRACT(epoch …) / 3600`) sobre casos abiertos. Si no hay casos abiertos: **Sin datos**. |
| **Caso abierto más antiguo (alta)** | `MIN(created_at)` entre casos abiertos. Si no hay: **Sin datos**. |

**Nota:** el umbral de 24 h para los conteos se calcula en **Python (UTC)**; la edad media usa **`now()` del motor SQL**. En condiciones normales la diferencia es despreciable, pero no son el mismo “reloj” literal.

---

## Reglas de visibilidad por rol

- El dashboard exige **sesión iniciada** (`require_login`). Cualquier usuario autenticado puede abrir `/dashboard` si la ruta no está restringida adicionalmente en el enrutador.
- **Filtro de datos por vendedor:** si el rol del usuario en sesión es **`vendedor`**, casi todas las consultas parten de `_cases_query`, que restringe a `Case.seller_name == usuario["nombre"]` (coincidencia con el nombre del usuario web, no con el username).
- **Roles distintos de vendedor** (`admin`, `sistemas`, `autorizacion`, `compras`, `consulta`, etc.): ven **todos** los casos (sin filtro por `seller_name`) en métricas, pendientes, SLA y resumen global de vendedores.

Si un vendedor no tiene casos con `seller_name` igual a su `nombre`, verá ceros y tablas vacías salvo la fila propia del resumen por vendedor cuando aplique.

---

## Limitaciones conocidas

1. **Pendientes y checklist:** topes por origen (12/40) y tabla final (30); no sustituye un listado completo de casos ni un reporte batch.
2. **Resumen por vendedor:** máximo **25** vendedores con actividad para roles no vendedor; vendedores sin `seller_name` en casos no aparecen en agregados globales.
3. **SLA:** “sin actualización” se infiere solo de **`updated_at`** (cualquier cambio al caso mueve el reloj); no distingue “sin avance de negocio” vs “tocó un campo técnico”.
4. **Edad media:** depende de `EXTRACT`/`now()` en PostgreSQL; si no hay casos abiertos, la UI muestra “Sin datos”.
5. **Alineación vendedor:** el filtro usa **`nombre`** del usuario frente a **`seller_name`** del caso; discrepancias de texto (espacios, mayúsculas, homónimos) pueden hacer que un vendedor no vea sus casos aunque existan.
6. **Rendimiento:** se priorizan consultas agregadas y límites acotados; rutas muy costosas no forman parte de esta vista, pero el checklist incompleto puede ser más pesado por caso.

---

## Cómo probarlo manualmente

1. **Arranque:** tener la aplicación web y la base de datos accesibles (por ejemplo según `README.md` / `DATABASE_URL`).
2. **Usuario administrador o sistemas:** iniciar sesión, abrir `https://<host>/dashboard` (o `http://localhost:<puerto>/dashboard`).
   - Comprobar que las tarjetas numéricas y la tabla “Casos por estado” reflejan datos globales.
   - Pulsar cada filtro rápido (o escribir `?filter=prep_aut`, etc.) y verificar que la tabla de pendientes cambia y la leyenda “Mostrando solo…” es coherente.
   - Revisar resumen por vendedor (varias filas si hay actividad).
   - Revisar bloque SLA: tras crear o dejar casos de prueba con `updated_at` antiguo, los conteos &gt; 24 h deberían incrementarse; sin casos abiertos, edad media y fecha más antigua muestran “Sin datos”.
3. **Usuario vendedor:** iniciar sesión con un usuario cuyo `nombre` coincida con `seller_name` de casos de prueba.
   - Confirmar subtítulo o textos que indican alcance “solo tus casos”.
   - Verificar que métricas, pendientes, SLA y resumen (una sola fila) solo incluyen esos casos.
4. **Sin sesión:** abrir `/dashboard` en ventana privada; debe redirigir al flujo de login.
5. **Filtro inválido:** `/dashboard?filter=no_existe` debe comportarse como `all` (filtro normalizado a valor permitido).

---

## Referencias en código

| Tema | Ubicación |
|------|-----------|
| Ruta y lógica | `app/web/routes/dashboard.py` |
| Plantilla | `app/web/templates/dashboard.html` |
| Estados de caso | `app/domain/constants.py` |
| Modelo `Case` (`created_at`, `updated_at`, `seller_name`, `current_status`) | `app/models/case.py` |
| Roles | `app/models/user.py` (`UserRole`) |
