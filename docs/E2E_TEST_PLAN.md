# Plan de pruebas manuales end-to-end (E2E)

**Proyecto:** sistema_gaman  
**Fase:** P10-C5  
**Alcance:** flujo operativo Bot Telegram + Web FastAPI + PostgreSQL + SharePoint (opcional) + auditoría.

Este documento describe **pruebas manuales**; no sustituye tests automatizados. Refleja el estado del código a la fecha de elaboración del plan.

---

## 0. Comandos útiles (antes de ejecutar escenarios)

Desde la raíz del repositorio (`sistema_gaman`):

```bash
git status
```

Base de datos y migraciones (requiere entorno virtual y `.env` configurado):

```bash
alembic current
alembic upgrade head
```

Comprobación rápida de entorno (imports, plantillas críticas, variables sin exponer secretos, `SELECT 1` si hay DB):

```bash
docker compose up -d db
python scripts/smoke_check.py
```

Comprobación de solo conexión:

```bash
python scripts/test_db_connection.py
```

Opcional (Graph / SharePoint, según credenciales):

```bash
python scripts/test_graph_upload.py
```

Arranque típico en desarrollo:

- **Web:** `python -m uvicorn app.web.main:web_app --reload` (ver `docs/ARCHITECTURE_STATUS.md`).
- **Bot:** `python -m app.main` (token Telegram y PostgreSQL válidos).

### Smoke check y entorno local

- **Script:** `python scripts/smoke_check.py` (desde la raíz del repo, con venv activo).
- **Plantilla Excel SNTE:** debe existir `storage/templates/plantilla_master_autorizaciones.xlsx` (no se versiona si es propiedad interna; copiar desde el repo de referencia de autorización SNTE; ver `docs/SNTE_MODULE.md`). Rutas típicas en equipos de desarrollo pueden ser como `E:\dev\autorizacion_snte` — copiar el archivo conservando el nombre exacto.
- **DATABASE_URL en Docker vs local:** en `docker-compose` el servicio Postgres se llama `db`; dentro de la red Compose la URL usa host `db`. En **PowerShell local** (fuera de Docker) ese host **no resuelve**; usa `localhost` y el puerto publicado (p. ej. `5433` según `README.md` y `docker-compose.yml`).
- **Alembic:** si la DB no responde, el smoke omite `alembic current` con un `WARN` breve; `alembic heads` se intenta igual (no requiere DB).

---

## Convenciones comunes

| Ámbito | Dónde mirar |
|--------|-------------|
| **UI Web** | Navegador: login, `/casos`, detalle de caso, formularios SNTE/refi, timeline de eventos. |
| **UI Bot** | Telegram: menús, teclados, mensajes de confirmación / error. |
| **DB** | PostgreSQL: tablas `cases`, `documents`, `case_history`, `case_events`, `users`, `authorization_jobs`, etc. |
| **Cola SharePoint** | Archivo JSON bajo almacenamiento configurado: `sharepoint_retry_queue.json` (ver `app/services/sharepoint_retry_queue.py`). |
| **Logs** | Salida consola del proceso web/bot; buscar trazas de servicios (`authorization`, `sharepoint`, `case_event`, `web.auth`). |

**Criterio de aprobación general:** el escenario se cumple sin errores no documentados, los datos en DB son coherentes con la UI y los eventos/logs esperados son visibles (o justificables si el entorno no tiene Graph/SharePoint).

---

## 1. Pedido mueble (venta nueva)

### Precondiciones

- Bot y DB operativos; usuario Telegram **vendedor** registrado en `users` con `telegram_id` coincidente.
- Usuario(s) **admin** en Telegram para grupo de pedidos (según `notification_service` / settings).
- Semana activa configurada (`effective_semana_activa`).

### Pasos

1. En Telegram: iniciar flujo **Pedido** → tipo **Mueble**.
2. Capturar cliente y cargar documentos obligatorios: **pedido**, **orden de descuento** (según checklist del bot).
3. Confirmar envío del pedido cuando el checklist esté completo.
4. En grupo de pedidos (admin): **Aprobar** (`ped_aprobar`) cuando el caso esté listo (documentos + autorización SNTE en web si el flujo exige compulsa con docs generados — ver escenario 4 si aplica).
5. (Web) Usuario rol **autorización** / **admin**: generar autorización SNTE si aún no existe.
6. Repetir aprobación a compulsa si falló antes por documentos faltantes.

### Resultado esperado en UI

- Bot: mensajes de checklist, confirmación de envío, notificación al grupo pedidos.
- Tras aprobar: estado visible coherente con compulsa / teclado de compulsas según `handlers` y `keyboards`.

### Resultado esperado en DB

- `cases`: `case_type = pedido`, `order_type = mueble`, transición de estados acorde al flujo (`case_history`).
- `documents`: versiones activas de tipos `pedido`, `orden_descuento` (y posteriores SNTE si se generaron en web).

### Logs / eventos esperados

- Historial en `case_history` por cambios de estado.
- Posibles `case_events` si la acción pasó por web con auditoría (p. ej. generación SNTE).

### Criterio de aprobación

- Caso creado y cerrado hasta compulsa sin `ValueError` de transición ni de documentos faltantes cuando corresponda; notificaciones sin traza de error crítica en consola del bot.

---

## 2. Pedido dinero / préstamo (venta nueva)

### Precondiciones

- Mismas que escenario 1; flujo **Préstamo** en el bot.

### Pasos

1. Pedido → **Préstamo**.
2. Cargar **pedido**, **orden de descuento**, **carátula bancaria** (el bot valida tipo préstamo para carátula).
3. Enviar pedido completo al grupo.
4. (Web) Generar SNTE; (Bot/Grupo) aprobar a compulsa cuando cumpla reglas documentales.

### Resultado esperado en UI

- Checklist en bot muestra carátula para préstamo; no permite carátula en mueble.

### Resultado esperado en DB

- `order_type = prestamo`; `documents` incluye tipo normalizado `caratula_bancaria` (o legacy migrado por `normalize_doc_type` en validaciones).

### Logs / eventos esperados

- Igual que escenario 1; mensajes de validación de documentos en logs si se intenta compulsa sin SNTE.

### Criterio de aprobación

- Flujo completo equivalente al mueble pero con tercer documento obligatorio satisfecho antes de compulsa (según `DocumentService.validate_active_documents_for_compulsa`).

---

## 3. Refinanciamiento

### Precondiciones

- Caso pedido en estado compatible (p. ej. **En preparación de autorización**) y datos de negocio válidos.
- Usuario web con rol **admin**, **sistemas** o **autorizacion**.
- Plantillas Excel/PDF presentes en rutas esperadas por `RefinanciamientoService` / `AuthorizationService` (ver código y `storage/templates`).

### Pasos

1. Web: abrir detalle del caso.
2. Enviar formulario **Generar refinanciamiento** (`POST /casos/{id}/generar-refinanciamiento`) con payload válido (campos requeridos según `_validate_refi_payload` en `authorizations.py`).
3. Verificar documentos generados y timeline.

### Resultado esperado en UI

- Redirección con mensaje de éxito o error acotado en query string (`?success=` / `?error=`).
- En detalle: presencia de documentos tipo refinanciamiento / PDF orden SNTE según generación.

### Resultado esperado en DB

- `documents`: activos `autorizacion_refi` y `orden_snte_pdf` (constantes `DOC_AUTORIZACION_REFI`, `DOC_ORDEN_SNTE_PDF`).
- `cases.current_status` actualizado a **Autorización generada** si el flujo lo persiste tras generación.
- `case_events`: eventos `REFI_GENERATED`, `DOCUMENT_CREATED`, `STATUS_CHANGED` (según `authorizations.py` y `case_event_service`).

### Logs / eventos esperados

- Logs de generación y persistencia de estatus; evento de notificación Telegram encolada (`TELEGRAM_NOTIFIED`) cuando aplique.

### Criterio de aprobación

- Generación exitosa sin rollback parcial; eventos de auditoría presentes y sin duplicados incoherentes en la misma transacción.

---

## 4. Documento faltante antes de compulsa

### Precondiciones

- Caso pedido en **En preparación de autorización** (o equivalente) **sin** `autorizacion_snte` activa (mueble) o sin carátula (préstamo), o refinanciamiento sin par refi/pdf.
- Admin en Telegram con acceso a botones de grupo `ped_aprobar`.

### Pasos

1. Intentar **Aprobar** envío a compulsa desde el grupo **sin** completar documentación exigida por `validate_active_documents_for_compulsa`.

### Resultado esperado en UI

- Bot: mensaje genérico de error al actualizar (handlers capturan excepción); no debe dejar el caso en estado inconsistente en UI del vendedor.

### Resultado esperado en DB

- **No** debe existir transición a **En compulsa** si la validación lanzó `ValueError` antes de persistir el nuevo estado (revisar último registro en `case_history`).

### Logs / eventos esperados

- Log de advertencia desde `document_service` con `missing` / `active` en extra.
- Posible traza `Error en callback de grupo` en bot.

### Criterio de aprobación

- La regla de negocio bloquea compulsa; tras subir/generar lo faltante, la misma acción **sí** debe poder completarse.

---

## 5. SharePoint fallido / reintento (retry)

### Precondiciones

- Bot con `job_queue` habilitado y job `sharepoint_retry_job` activo (`app/main.py`).
- Escenario previo que encole subida a SharePoint (generación web SNTE/refi dispara tareas en background).

### Pasos

1. Forzar fallo de subida (Graph caído, ruta local inexistente, token inválido, etc.) según entorno de prueba.
2. Observar creación/actualización de entrada en `sharepoint_retry_queue.json`.
3. Esperar ciclos del job de retry o revisar logs del handler `sharepoint_retry_job` en `handlers.py`.

### Resultado esperado en UI

- Documento puede mostrar `upload_status` distinto de `UPLOADED` en detalle web según modelo.

### Resultado esperado en DB

- `documents.upload_status` / `upload_error` reflejan fallo o éxito tras reintento.
- Cola JSON con `attempts` y `last_error` actualizados.

### Logs / eventos esperados

- Logs de excepción en upload; líneas del job de reintento al procesar ítems.

### Criterio de aprobación

- Tras recuperar Graph/ruta, el ítem se procesa o se descarta según `sharepoint_retry_max_attempts` sin corromper la cola.

---

## 6. Usuario sin permiso (web)

### Precondiciones

- Usuarios de prueba con roles distintos: **vendedor**, **consulta**, **compras**, **autorizacion**, **admin/sistemas**.
- Sesión web válida.

### Pasos

1. Como **vendedor** o **consulta**: intentar `POST /casos/{id}/generar-autorizacion` (forzar desde herramienta HTTP o devtools) aunque el botón no esté visible.
2. Como rol no permitido: `GET /casos/{id}/revision-talon` o `POST .../procesar-ocr`.
3. Como **autorizacion**: confirmar que **sí** puede generar SNTE/refi pero **no** revisión de talón ni OCR si el rol no está en la lista permitida.

### Resultado esperado en UI

- Redirección a `/dashboard` (o equivalente) cuando `require_roles` rechaza.
- Botones deshabilitados u ocultos en plantillas alineados a roles.

### Resultado esperado en DB

- Sin filas nuevas indebidas en `case_events` / `documents` por esa sesión.

### Logs / eventos esperados

- `Acceso web denegado: rol no autorizado para la ruta` en logger `app.web.auth` con `path`, `rol`, `allowed_roles`.

### Criterio de aprobación

- Ninguna acción sensible queda expuesta a roles incorrectos; el log de denegación es verificable.

---

## 7. Doble submit / doble generación

### Precondiciones

- Caso con documento SNTE o refi **activo** ya generado.

### Pasos

1. Web: pulsar rápidamente dos veces **Generar** (o reenviar el POST manualmente) antes de que redirija.
2. Alternativa: segundo POST deliberado con herramienta HTTP.

### Resultado esperado en UI

- Redirección con mensaje de error tipo “Ya existe … activa” (ver `_redirect_if_active_document_exists` en `authorizations.py`).

### Resultado esperado en DB

- Un solo documento activo del tipo bloqueado; sin segunda generación completa.

### Logs / eventos esperados

- `Generacion bloqueada por documento activo existente` (warning) con `case_id` y `document_type`.

### Criterio de aprobación

- No hay duplicados activos ni doble encolado inconsistente de notificaciones para el mismo tipo.

---

## 8. Notificación Telegram

### Precondiciones

- `TELEGRAM_BOT_TOKEN`, chats de grupo/vendedor configurados en settings según `notification_service`.

### Pasos

1. Completar una acción que dispare notificación (p. ej. aprobación a compulsa, generación SNTE desde web con background `notify_snte_generation_from_web`).
2. Verificar recepción en chat del vendedor o grupo según función invocada.

### Resultado esperado en UI

- Mensaje Telegram con resumen de caso y estado.

### Resultado esperado en DB

- Evento `TELEGRAM_NOTIFIED` u otro registrado en `case_events` cuando el flujo web lo persista.

### Logs / eventos esperados

- Sin `InvalidToken`; logs de encolado de background en web.

### Criterio de aprobación

- Mensaje recibido o error documentado por entorno (token/chat inválido) fuera de alcance de bug de código.

---

## 9. Timeline / auditoría

### Precondiciones

- Caso con actividad mixta (web + posibles eventos sistema).

### Pasos

1. Web: abrir detalle del caso y sección de **eventos** / timeline (`case_events` en plantilla).
2. SQL opcional: `SELECT event_type, message, source, created_at FROM case_events WHERE case_id = ? ORDER BY created_at DESC;`

### Resultado esperado en UI

- Lista ordenada con tipos legibles (`STATUS_CHANGED`, `AUTH_GENERATED`, etc.) y metadatos relevantes.

### Resultado esperado en DB

- Filas coherentes con acciones realizadas; `actor_user_id` / `actor_role` poblados cuando la acción es web con usuario.

### Logs / eventos esperados

- No errores de plantilla por `metadata_json` nulo.

### Criterio de aprobación

- La línea de tiempo refleja fielmente las acciones de prueba sin huecos inexplicables.

---

## 10. Descarga / ver documentos

### Precondiciones

- Caso con `documents` con `file_path` existente en servidor de pruebas.

### Pasos

1. Web: en detalle, **Ver / Descargar** (`GET /documentos/{id}/ver`).
2. Probar como **vendedor dueño** y como **vendedor de otro caso** (documento de caso ajeno).

### Resultado esperado en UI

- Dueño: archivo servido inline.
- Ajeno: **403** o redirección según implementación actual de permisos en `cases.py`.

### Resultado esperado en DB

- Sin cambios obligatorios; solo lectura.

### Logs / eventos esperados

- Log de denegación para vendedor sin titularidad del caso.

### Criterio de aprobación

- No hay fuga de archivos entre vendedores; roles administrativos conservan acceso acorde al diseño.

---

## 11. Revisión de talón / OCR (opcional)

### Precondiciones

- Usuario web **admin** o **sistemas**.
- Caso con documento tipo talón o evidencia de revisión cargada.

### Pasos

1. `GET /casos/{id}/revision-talon`: revisar formulario y datos precargados desde OCR si existen.
2. `POST .../procesar-ocr` sobre documento elegible (solo roles admin/sistemas).
3. Guardar revisión talón (`POST /casos/{id}/revision-talon`).

### Resultado esperado en UI

- Formulario carga; OCR devuelve estado en UI; guardado redirige al detalle del caso.

### Resultado esperado en DB

- Tabla `talon_reviews` (modelo `TalonReview`) con fila nueva; `ocr_results` actualizados si aplica.

### Logs / eventos esperados

- Logs del servicio OCR / revisión sin stacktrace no controlado.

### Criterio de aprobación

- Roles no admin/sistemas no pueden abrir revisión ni lanzar OCR (redirección a dashboard y log de rol).

---

## 12. Vendedor intentando ver caso ajeno

### Precondiciones

- Dos casos con distintos `seller_name`; usuario web vendedor igual al vendedor del caso A solamente.

### Pasos

1. Login como vendedor A.
2. Navegar a `/casos/{id_B}` manualmente (ID del caso B ajeno).

### Resultado esperado en UI

- Redirección a `/casos` sin mostrar datos del caso B.

### Resultado esperado en DB

- Sin lecturas destructivas; solo comprobación de autorización en ruta.

### Logs / eventos esperados

- Opcional: ningún log obligatorio; puede añadirse verificación manual de que no hay 200 con cuerpo HTML del caso ajeno.

### Criterio de aprobación

- Confidencialidad entre vendedores mantenida en listado y detalle.

---

## Checklist de release interno

Usar antes de entregar a QA o producción controlada.

- [ ] `git status` limpio o cambios revisados y etiquetados.
- [ ] `alembic current` coincide con revisión desplegada; `alembic upgrade head` aplicado en el entorno objetivo.
- [ ] Variables críticas en `.env`: DB, `WEB_SESSION_SECRET`, Telegram, rutas de almacenamiento, Graph/SharePoint si aplica.
- [ ] `python scripts/smoke_check.py` sin fallos críticos (plantillas bajo `storage/templates/` y `DATABASE_URL` alcanzable desde ese entorno).
- [ ] **Escenarios 1 y 2** ejecutados al menos una vez en entorno con datos reales o semilla (`scripts/seed_admin.py`, `scripts/create_demo_case.py` si se usan).
- [ ] **Escenario 3** (refi) con plantillas presentes.
- [ ] **Escenario 4** (bloqueo compulsa) verificado tras cambios recientes de validación documental.
- [ ] **Escenario 5** (retry SharePoint) verificado o marcado N/A si Graph no está disponible en el entorno.
- [ ] **Escenario 6** (roles web) cubre rutas sensibles actuales.
- [ ] **Escenario 7** (doble generación) sin duplicados activos.
- [ ] **Escenario 8** (Telegram) con token y chats válidos o N/A documentado.
- [ ] **Escenario 9** (timeline) revisado en UI para un caso de prueba largo.
- [ ] **Escenario 10** (ver documento) sin IDOR entre vendedores.
- [ ] **Escenario 11** (talon/OCR) N/A o OK según despliegue.
- [ ] **Escenario 12** (aislamiento vendedor) OK.
- [ ] Registro de incidencias y capturas adjuntas al ticket de release.
