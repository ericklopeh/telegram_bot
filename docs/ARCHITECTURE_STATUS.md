# Estado de Arquitectura - sistema_gaman

Fecha de corte: 2026-05-10  
Rama actual de trabajo: `feature/web-demo`

## 1. Resumen Ejecutivo

`sistema_gaman` es un sistema Python que combina:

- Bot de Telegram para captura operativa de pedidos, revisiones y documentos.
- Web FastAPI para login, tablero, consulta de casos, carga documental y revision de talon.
- PostgreSQL como persistencia principal.
- SQLAlchemy como ORM.
- Alembic para migraciones.
- Docker Compose para despliegue de base de datos y bot.
- Integracion Microsoft Graph / SharePoint para respaldo documental remoto.

El proyecto se ha movido de un bot con permisos y sesion en memoria/.env hacia una arquitectura incremental basada en PostgreSQL, servicios de dominio y repositorios.

## 2. Arquitectura Actual

### Capas

- `app/bot`: entrada/salida Telegram, handlers, teclados y persistencia conversacional.
- `app/web`: aplicacion FastAPI web, templates, rutas y auth web centralizado.
- `app/services`: logica de dominio e integraciones.
- `app/repositories`: acceso a datos con SQLAlchemy.
- `app/models`: modelos SQLAlchemy.
- `app/domain`: constantes y reglas simples de negocio.
- `app/db`: engine, sesiones y base declarativa.
- `migrations`: migraciones Alembic.

### Principio actual

Los handlers siguen siendo orquestadores. La logica se ha extraido gradualmente a servicios:

- Notificaciones: `notification_service.py`
- Casos/reglas: `case_service.py`
- Documentos locales/versionado: `document_service.py`
- Upload remoto SharePoint: `sharepoint_document_service.py`

No se ha reescrito el flujo conversacional completo; se mantiene compatibilidad funcional.

## 3. Modulos Principales

### Bot

- `app/main.py`
  - Arranca el bot Telegram.
  - Carga `.env`.
  - Configura `PostgresPersistence`.
  - Registra handlers y jobs.

- `app/bot/handlers.py`
  - Orquestador Telegram.
  - Maneja `/start`, `/sessions`, texto, archivos y callbacks.
  - Conserva estado conversacional en `context.chat_data`.
  - Delegaciones actuales:
    - permisos contra PostgreSQL
    - notificaciones
    - reglas de casos
    - rutas/prefijos documentales
    - upload SharePoint background

- `app/bot/keyboards.py`
  - Reply keyboards e inline keyboards.

- `app/bot/persistence.py`
  - Persistencia `chat_data` en PostgreSQL JSONB.
  - Tabla: `bot_chat_data`.

### Web

- `app/web/main.py`
  - Instancia FastAPI real: `web_app`.
  - Comando correcto:
    ```powershell
    python -m uvicorn app.web.main:web_app --reload
    ```
  - Login web con usuarios reales de DB.
  - Session middleware con `WEB_SESSION_SECRET`.

- `app/web/auth.py`
  - `get_current_user(request, db)`
  - `require_login(request, db)`
  - `require_roles(request, db, roles)`
  - Valida sesion contra DB en cada ruta protegida.
  - Si el usuario no existe o esta inactivo, limpia sesion.

- `app/web/routes/dashboard.py`
  - Dashboard protegido.

- `app/web/routes/cases.py`
  - Lista/detalle de casos.
  - Upload documental web.
  - Ver documentos.
  - OCR manual desde web para talon.

- `app/web/routes/revision_talon.py`
  - Formulario y guardado de revision de talon.

### API

- `app/api/main.py`
  - Instancia FastAPI separada para API del bot: `app`.
  - No es la entrada web principal.

## 4. Modelos y Persistencia

### Modelos principales

- `Case`
  - Tabla: `cases`
  - Campos clave:
    - `public_id`
    - `case_type`
    - `order_type`
    - `client_name`
    - `current_status`
    - `visible_status`
    - `seller_telegram_chat_id`
    - `week_code`
    - `folder_path`

- `Document`
  - Tabla: `documents`
  - Versionado documental por `case_id + document_type`.
  - Campos clave:
    - `document_type`
    - `stored_filename`
    - `file_path`
    - `mime_type`
    - `is_active`
    - `replaced_document_id`
    - `upload_status`
    - `sharepoint_web_url`
    - `upload_error`
    - `upload_attempts`

- `CaseHistory`
  - Historial de cambios de estado y acciones.

- `User`
  - Tabla: `users`
  - Campos clave:
    - `username`
    - `hashed_password`
    - `telegram_id`
    - `role`
    - `is_active`

- `BotChatData`
  - Tabla: `bot_chat_data`
  - Persistencia `chat_data` con `JSONB`.

### Migraciones existentes

- `20260421_000001_create_cases_table.py`
- `20260422_000002_cases_documents_history_ocr_auth.py`
- `20260426_000003_document_upload_tracking.py`
- `da1114d8475c_create_talon_reviews_table.py`
- `daf28a31f8c6_create_users_table.py`
- `e232f501bee0_create_bot_chat_data.py`

## 5. Repositories

- `CaseRepository`
  - Folios.
  - Busquedas globales y por vendedor.
  - Listados recientes.
  - Casos pendientes.
  - Resumen de estados.
  - Consultas para SLA.

- `DocumentRepository`
  - Versionado documental.
  - Desactivacion de documento activo previo.
  - Consulta de tipos activos.
  - Upload status:
    - `PENDING_UPLOAD`
    - `UPLOADED`
    - `UPLOAD_FAILED`

- `HistoryRepository`
  - Insercion de entradas en historial.

- `UserRepository`
  - Usuarios por id, username y telegram_id.
  - `get_active_by_telegram_id`.
  - `list_active_admins_with_telegram_id`.

## 6. Servicios Existentes

### `auth_service.py`

- Hash y verificacion de passwords.
- Usa `bcrypt`.

### `case_service.py`

Responsabilidades actuales:

- Crear caso de revision.
- Crear skeleton de pedido.
- Registrar documentos.
- Validar checklist.
- Finalizar pedido si esta completo.
- Cambiar estados.
- Resolver reglas de acciones de grupo.

Funciones destacadas:

- `create_revision_case`
- `create_pedido_case_skeleton`
- `register_pedido_document`
- `pedido_has_all_documents`
- `get_pedido_checklist`
- `finalize_pedido_if_complete`
- `transition_case_status`
- `group_action_requires_reason`
- `group_action_transition`

### `document_service.py`

Responsabilidades actuales:

- Prefijos de archivos.
- Directorios documentales por caso.
- Contenedor de metadatos `StoredIncomingFile`.
- Registro/versionado documental de bajo riesgo.
- Marcar upload pendiente.

Funciones destacadas:

- `revision_evidence_prefix`
- `revision_dictamen_prefix`
- `pedido_document_prefix`
- `pedido_evidencias_dir`
- `revision_dictamen_dir`
- `register_document_version`
- `mark_document_pending_upload`
- `register_pedido_document_upload`
- `register_revision_dictamen_upload`

### `sharepoint_document_service.py`

Responsabilidades actuales:

- Upload remoto documental.
- Lectura de archivo local.
- Llamada a Microsoft Graph.
- Actualizacion de estado documental.
- Enqueue de retry si falla.

Clases:

- `SharePointUploadPayload`
- `SharePointDocumentService`

Metodo principal:

```python
upload_document(payload) -> dict
```

No envia mensajes Telegram.

### `notification_service.py`

Responsabilidades actuales:

- Mensajes a grupo pedidos.
- Mensajes a grupo compulsas.
- Mensajes al vendedor.
- Alertas admin desde usuarios activos en DB.
- Jobs de recordatorio y SLA.

Funciones destacadas:

- `notificar_grupo_pedidos`
- `notificar_grupo_compulsas`
- `notificar_vendedor_estado`
- `notificar_admin_alertas`
- `run_compulsa_reminder_job`
- `run_sla_watchdog_job`

### `microsoft_graph.py`

Responsabilidades:

- Token Microsoft Graph.
- Site/drive resolution.
- Crear/asegurar carpetas.
- Sanitizacion de nombres Graph.
- Upload de archivo pequeno.
- Construccion de carpeta SharePoint:
  - `MS_ROOT_FOLDER / semana / vendedor / cliente / subcarpeta_tipo`

### `sharepoint_retry_queue.py`

- Cola JSON local para reintentos.
- Archivo:
  - `${BASE_STORAGE_PATH}/sharepoint_retry_queue.json`
- Operaciones:
  - `enqueue_failed_upload`
  - `list_retry_items`
  - `update_retry_item`
  - `remove_retry_item`

## 7. Auth y Roles

### Roles definidos

En `UserRole`:

- `admin`
- `sistemas`
- `autorizacion`
- `compras`
- `vendedor`
- `consulta`

### Bot

El bot ya no usa funcionalmente `ADMIN_USER_IDS` ni `SELLER_USER_IDS` para permisos.

Permisos:

- Admin operativo:
  - `admin`
  - `sistemas`

- Vendedor:
  - `vendedor`

Validaciones:

- `users.telegram_id` debe coincidir con el usuario Telegram.
- `users.is_active` debe ser `true`.
- Usuario inexistente o inactivo no tiene acceso.

### Web

- Login con `username` y password hasheado.
- Sesion en cookie firmada por `SessionMiddleware`.
- `WEB_SESSION_SECRET` configurable.
- Cada ruta protegida valida usuario contra DB.
- Si el usuario ya no existe o esta inactivo, la sesion se limpia.

## 8. Persistencia Conversacional

La persistencia conversacional del bot esta en PostgreSQL:

- Clase: `PostgresPersistence`
- Tabla: `bot_chat_data`
- Campo: `data JSONB`

Solo se persiste:

- `chat_data`

No se persiste:

- `bot_data`
- `user_data`
- `callback_data`
- `conversations`

El proyecto no usa `ConversationHandler` formal; los estados conversacionales se manejan mediante claves en `context.chat_data`, por ejemplo:

- `state`
- `flow`
- `cliente`
- `order_type`
- `case_public_id`
- `pending_doc_type`

## 9. Flujo Telegram -> DB -> SharePoint

### Revision inicial

1. Vendedor elige `Revision`.
2. Bot pide cliente.
3. Usuario adjunta archivo/foto.
4. `save_incoming_file` descarga a disco.
5. `CaseService.create_revision_case` crea:
   - `Case`
   - `CaseHistory`
   - `Document` con `DOC_REVISION_EVIDENCIA`
6. Se marca `PENDING_UPLOAD`.
7. Se agenda `_upload_document_background`.
8. `SharePointDocumentService.upload_document` sube a SharePoint.
9. Se actualiza:
   - `UPLOADED` con `sharepoint_web_url`, o
   - `UPLOAD_FAILED` y retry JSON.
10. Se alerta a admins.

### Dictamen de revision

1. Admin elige revision pendiente.
2. Admin selecciona dictamen.
3. Admin adjunta evidencia.
4. `DocumentService.register_revision_dictamen_upload` registra `DOC_REVISION_DICTAMEN`.
5. `CaseService.transition_case_status` cambia estado.
6. Se notifica al vendedor.

Actualmente este flujo no agenda SharePoint background para dictamen.

### Pedido

1. Vendedor elige `Pedido`.
2. Bot pide cliente.
3. Vendedor elige tipo:
   - `mueble`
   - `prestamo`
4. Se crea skeleton de caso al elegir primer documento.
5. Cada archivo:
   - se descarga localmente
   - se registra con versionado documental
   - se marca `PENDING_UPLOAD`
   - se registra historia de carga/reemplazo
   - se actualiza checklist
   - se agenda upload SharePoint
6. Al completar documentos requeridos, vendedor puede finalizar.
7. `CaseService.finalize_pedido_if_complete` valida checklist y cambia a preparacion de autorizacion.
8. Se notifica grupo pedidos, admins y vendedor.

## 10. Tipos Documentales

### Pedido

- `pedido`
- `orden_descuento`
- `caratula_bancaria`

Reglas:

- `mueble`: `pedido`, `orden_descuento`
- `prestamo`: `pedido`, `orden_descuento`, `caratula_bancaria`

### Revision

- `revision_evidencia`
- `revision_dictamen`

### SharePoint

Mapeo remoto actual:

- `REVISION*` -> `01_REVISIONES`
- `PEDIDO*` -> `02_PEDIDOS`
- `AUTORIZACION*` -> `03_AUTORIZACIONES`
- `COMPULSA*` -> `04_COMPULSA`

## 11. Estructura De Carpetas

### Local

Configuracion:

- `PEDIDOS_PATH`
- `REVISIONES_PATH`
- `RUTA_BASE_PEDIDOS` opcional con prioridad
- `RUTA_BASE_REVISIONES` opcional con prioridad

Pedido:

```text
PEDIDOS_PATH / SEM XX-YYYY / <folio> <cliente> /
  EVIDENCIAS/
  AUTORIZACION/
```

Revision:

```text
REVISIONES_PATH / SEM XX-YYYY / <folio_tmp> <cliente> /
  EVIDENCIAS/
  REVISION/
```

### SharePoint

```text
MS_ROOT_FOLDER / <semana> / <vendedor> / <cliente> /
  01_REVISIONES/
  02_PEDIDOS/
  03_AUTORIZACIONES/
  04_COMPULSA/
```

La carpeta de caso en SharePoint se normaliza por cliente, no por folio.

## 12. Jobs y Background Tasks

### Background task inmediata

- `_upload_document_background`
  - wrapper Telegram en `handlers.py`
  - llama `SharePointDocumentService`
  - manda mensaje de exito/error al usuario

### JobQueue

Registrados en `app/main.py`:

- `compulsa_reminder_job`
  - wrapper en handler
  - logica en `notification_service.run_compulsa_reminder_job`

- `sharepoint_retry_job`
  - todavia vive en `handlers.py`
  - reintenta items de `sharepoint_retry_queue.json`

- `sla_watchdog_job`
  - wrapper en handler
  - logica en `notification_service.run_sla_watchdog_job`

## 13. Variables `.env` Necesarias

### Telegram

```env
TELEGRAM_BOT_TOKEN=
```

### PostgreSQL

```env
POSTGRES_DB=
POSTGRES_USER=
POSTGRES_PASSWORD=
POSTGRES_HOST=
POSTGRES_PORT=
DATABASE_URL=
```

### Web

```env
WEB_SESSION_SECRET=
```

### Storage

```env
BASE_STORAGE_PATH=/app/storage
PEDIDOS_PATH=/app/storage/pedidos
REVISIONES_PATH=/app/storage/revisiones
RUTA_BASE_PEDIDOS=
RUTA_BASE_REVISIONES=
```

### Telegram groups

```env
CHAT_ID_PEDIDOS=
CHAT_ID_COMPULSAS=
CHAT_ID_ADMIN_ALERTS=
```

Nota: `CHAT_ID_ADMIN_ALERTS` existe, pero las alertas admin operativas del bot ya usan usuarios activos en DB con `telegram_id`.

### Legacy permissions

```env
SELLER_USER_IDS=
ADMIN_USER_IDS=
```

Siguen en config por compatibilidad, pero no se usan funcionalmente para permisos del bot.

### Horario

```env
DISPLAY_TIMEZONE=America/Mexico_City
BUSINESS_HOURS_ENABLED=false
BUSINESS_HOURS_START=09:00
BUSINESS_HOURS_END=18:30
```

### Semana activa

```env
SEMANA_ACTIVA_AUTO=true
SEMANA_ACTIVA=SEM 17-2026
```

### SharePoint / Microsoft Graph

```env
MS_TENANT_ID=
MS_CLIENT_ID=
MS_CLIENT_SECRET=
MS_SITE_HOSTNAME=
MS_SITE_PATH=
MS_SITE_ID=
MS_DRIVE_NAME=
MS_DRIVE_ID=
MS_ROOT_FOLDER=
```

### Jobs

```env
COMPULSA_REMINDER_MINUTES=60
SHAREPOINT_RETRY_INTERVAL_MINUTES=5
SHAREPOINT_RETRY_MAX_ATTEMPTS=8
SLA_ALERT_INTERVAL_MINUTES=120
SLA_REVISION_MINUTES=240
SLA_AUTORIZACION_MINUTES=240
SLA_COMPULSA_MINUTES=180
```

## 14. Como Correr El Proyecto

### Instalar dependencias localmente

```powershell
python -m pip install -r requirements.txt
```

Para entorno minimo Docker/bot:

```powershell
python -m pip install -r requirements-docker.txt
```

### Levantar PostgreSQL con Docker

```powershell
docker compose up -d db
```

PostgreSQL se publica en host `localhost:5433`.

### Ejecutar migraciones

```powershell
alembic upgrade head
```

`migrations/env.py` usa `DATABASE_URL` desde `.env`.

### Correr bot

```powershell
python -m app.main
```

Con Docker:

```powershell
docker compose up -d --build
```

### Correr web

La instancia correcta es `web_app`:

```powershell
python -m uvicorn app.web.main:web_app --reload
```

URL:

```text
http://127.0.0.1:8010/login
```

### Crear usuario admin inicial

```powershell
python scripts/seed_admin.py
```

Asignar `telegram_id` a usuario existente:

```sql
UPDATE users
SET telegram_id = 123456789
WHERE username = 'admin';
```

## 15. TODOs Tecnicos

### Seguridad

- Endurecer `WEB_SESSION_SECRET` en ambientes reales.
- Definir matriz de roles web por ruta.
- Agregar auditoria de login fallido si se requiere.

### Bot / Dominio

- Seguir reduciendo `handlers.py`.
- Extraer mas queries de consulta/estatus a servicios.
- Evaluar cache de permisos por update para evitar consultar DB dos veces en algunos flujos.

### Documentos

- Mover `sharepoint_retry_job` a `sharepoint_document_service`.
- Evaluar mover la cola retry de JSON a PostgreSQL.
- Tipar payloads documentales de forma mas amplia.
- Revisar comportamiento de dictamen revision: actualmente no se sube a SharePoint en background.
- Unificar nombres: `register_pedido_document` tambien se usa para revision dictamen.

### SharePoint

- Implementar upload session para archivos grandes.
- Manejar renombrado/migracion de carpetas temporales a folio oficial si aplica.
- Mejorar observabilidad de Graph: errores, latencias, IDs remotos.

### OCR

- Disenar pipeline antes de implementar mas automatizacion.
- Separar extraccion, validacion, correccion manual y persistencia de resultados.
- Evitar acoplar OCR a handlers.

### Web

- Completar restriccion de roles por ruta.
- Reemplazar datos demo del dashboard por consultas reales.
- Mejorar manejo visual de errores.

## 16. Riesgos Conocidos

- `handlers.py` sigue siendo grande y contiene flujos complejos.
- Algunos textos aparecen con problemas de encoding en consola/archivos historicos.
- Retry SharePoint usa JSON local; en despliegues con multiples replicas podria duplicar o perder consistencia.
- Si archivo local se elimina antes del retry, el job solo incrementa intentos y eventualmente remueve.
- Dictamen de revision registra documento local/DB, pero no sigue aun el mismo pipeline SharePoint que pedido/revision inicial.
- `requirements.txt` es amplio; `requirements-docker.txt` es mas acotado.
- Algunos imports/repositorios siguen disponibles en handlers por flujos no refactorizados.
- `SELLER_USER_IDS` y `ADMIN_USER_IDS` aun existen en `.env.example`, aunque ya no gobiernan permisos del bot.

## 17. Proximos Pasos Recomendados

1. Fase 6.4: mover `sharepoint_retry_job` a `sharepoint_document_service` manteniendo wrapper en `handlers.py`.
2. Fase 6.5: decidir si `revision_dictamen` debe subir a SharePoint con el mismo pipeline.
3. Fase 6.6: introducir payload/resultado documental para reducir tuplas en `handle_files`.
4. Fase 7: disenar pipeline OCR antes de modificar implementacion.
5. Fase Web: completar matriz de roles y dashboard real.
6. Fase Observabilidad: logs estructurados para uploads, retries, permisos y transiciones.

## 18. Estado Git Reciente

Ultimos commits funcionales relevantes:

- `Unify bot permissions and centralize web auth`
- `Extract bot notification service`
- `Move bot notification jobs to service`
- `Move pedido finalization rules to case service`
- `Move group action rules to case service`
- `Add document service for file paths and prefixes`
- `Move document registration helpers to document service`
- `Extract SharePoint document upload service`

