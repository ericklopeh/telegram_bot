# Bot Pedidos Gaman

Bot interno de Telegram para revisiones y pedidos de una mueblería, con **persistencia en PostgreSQL**, historial de estados, documentos versionados y arquitectura por capas.

## Stack

- Python 3.11+
- python-telegram-bot
- PostgreSQL + SQLAlchemy 2 + Alembic
- Docker Compose
- pydantic-settings, python-dotenv

## Estructura del proyecto

```text
app/
  main.py              # Arranque, logging, registro de handlers
  config.py            # Variables de entorno tipadas
  domain/constants.py  # Estados, tipos de documento, checklist
  db/                  # Base declarativa, engine, session_scope
  bot/
    handlers.py        # Handlers Telegram (delegan en servicios)
    keyboards.py       # Teclados reply e inline
  models/              # Case, CaseHistory, Document, OcrResult, AuthorizationJob
  repositories/        # Acceso a datos
  services/
    case_service.py    # Reglas de negocio de casos
    telegram_file_service.py
    storage/           # LocalStorageBackend (preparado para S3)
    ocr_service.py     # Placeholder OCR
    authorization_service.py  # Placeholder Excel
  utils/               # naming, logging_config
migrations/            # Alembic
```

## Flujo resumido

1. **Revisión**: nombre → archivo → caso en BD, carpeta `REVISIONES/...`, documento `revision_evidencia`.
2. **Pedido**: nombre → tipo (Mueble / Préstamo) → botones por **tipo de documento** (Pedido, Orden de descuento, Carátula si aplica) → adjuntar cada uno (reemplazo permitido) → **confirmación antes de enviar** → notificación al grupo de pedidos.
3. **Grupos**: botones inline actualizan estado en BD e historial; rechazo/corrección pide motivo obligatorio; compulsa es editable y permite reabrir estado.
4. **Recordatorios compulsa**: casos en `Pendiente de compulsa` generan alertas periódicas al grupo de compulsas.
5. **Vendedor**: `Consultar estatus` con **botones de casos recientes** o búsqueda por nombre/folio, `Mi estatus` con resumen, y `Mis ventas de hoy` (etiqueta *Nombre — dd/mm/aaaa hh:mm*).
6. **Dictamen de revisión**: flujo de resolución (`Liquidez a favor` / `Sin liquidez`) con imagen de evidencia (captura de Excel).

## Configuración

1. Copia el ejemplo de entorno: `copy .env.example .env` (PowerShell: `Copy-Item .env.example .env`).
2. Edita `.env`: al menos `TELEGRAM_BOT_TOKEN`, `DATABASE_URL`, `POSTGRES_*` (misma contraseña en `POSTGRES_PASSWORD` y en la URL), `CHAT_ID_*`, `DISPLAY_TIMEZONE`, `SEMANA_ACTIVA_AUTO=true` (semana *SEM WW-AAAA* por calendario ISO; desactívalo y usa `SEMANA_ACTIVA` solo si quieres fijarla a mano), y rutas si usas Windows (`RUTA_BASE_*`).
3. **PostgreSQL en Docker**: el servicio se llama `db` (imagen `postgres:16`), con volumen persistente `pg_data` y `healthcheck` con `pg_isready`.

### DATABASE_URL

Usa el driver **psycopg v3** en la URL (ya incluido en el proyecto):

- **Alembic / bot en Windows con Postgres en Docker:** en `.env` usa **`localhost:5433`** (el `docker-compose` publica `5433→5432` para no chocar con un PostgreSQL nativo en `:5432`).
- **Servicio `bot` en Compose:** no hace falta tocar nada: el compose **sobrescribe** `DATABASE_URL` a host **`db:5432`** dentro de la red del stack.

**`UnicodeDecodeError` con `postgresql+psycopg2://` en Windows:** algunas instalaciones de PostgreSQL devuelven mensajes de error en español con codificación que libpq/psycopg2 decodifica mal. Usar `postgresql+psycopg://` evita ese fallo y muestra un error SQLAlchemy/psycopg habitual (p. ej. contraseña incorrecta).

## Base de datos (Docker + prueba de conexión)

Levantar Postgres y esperar a que esté sano:

```bash
docker compose up -d db
```

Instalar dependencias y migrar (en tu máquina, con `DATABASE_URL` apuntando a `localhost:5433`):

```bash
pip install -r requirements-docker.txt
alembic upgrade head
```

(`requirements-docker.txt` es el mismo conjunto mínimo que instala la imagen Docker. El archivo `requirements.txt` grande es un *freeze* opcional de entorno de desarrollo.)

Probar conexión (desde la raíz del proyecto):

```bash
python scripts/test_db_connection.py
```

### Smoke check (`scripts/smoke_check.py`)

Comprueba sin levantar servidores: imports (`app.main`, web, API, servicios SNTE/refi/caso/documentos/notificaciones), variables obligatorias **sin imprimir secretos**, existencia de plantillas bajo `storage/templates/`, y `SELECT 1` si `DATABASE_URL` está definida.

```bash
docker compose up -d db
python scripts/smoke_check.py
```

**Plantilla Excel SNTE:** debe existir `storage/templates/plantilla_master_autorizaciones.xlsx`. No siempre se versiona en el repo: cópiala desde tu fuente de verdad (otro repo de autorización SNTE o una ruta local de equipo como `E:\dev\autorizacion_snte`), conservando el nombre del archivo. Detalle: `docs/SNTE_MODULE.md`.

**DATABASE_URL Docker vs local:** dentro de Docker Compose el host del servicio Postgres suele ser `db` (solo resuelve en la red del stack). Desde **PowerShell en Windows** fuera de Docker, usa **`localhost`** y el puerto mapeado (p. ej. **`5433`**, ver sección [DATABASE_URL](#database_url) arriba). El smoke no modifica `.env`.

Si la base no responde, el script intenta `alembic heads` y **omite** `alembic current` con un `WARN` breve (evita trazas largas cuando la DB no está levantada).

## SharePoint (Microsoft Graph)

La integración para subir archivos de revisión/pedido a SharePoint está documentada en:

- `docs/graph_setup.md`

Prueba standalone de Graph (sin Telegram):

```bash
python scripts/test_graph_upload.py
```

Si el contenedor `bot` ya está arriba:

```bash
docker compose exec bot python scripts/test_db_connection.py
```

Migraciones:

- `20260421_000001`: tabla `cases`
- `20260422_000002`: `public_id`, `seller_telegram_chat_id`, `case_history`, `documents` (índice único parcial un activo por tipo), `ocr_results`, `authorization_jobs`

## Ejecutar el bot

```bash
python -m app.main
```

O con Docker (espera a que `db` esté healthy antes de arrancar el bot). El `Dockerfile` usa **`requirements-docker.txt`** para que `pip install` sea rápido y fiable en `python:3.11-slim` (el `requirements.txt` completo incluye paquetes pesados que suelen romper el build).

```bash
docker compose up --build -d db
docker compose up --build -d bot
```

## Cómo probar (manual)

1. Migraciones aplicadas y Postgres arriba.
2. `/start` → Revisión → nombre → un archivo: ver fila en `cases` y `documents`.
3. Pedido → tipo → elegir documento con botón → enviar archivo → repetir hasta checklist completo → **Enviar pedido**.
4. En el grupo de pedidos, pulsar Aprobar / Rechazar / Corrección y comprobar `case_history` en BD.
5. Consultar estatus con un fragmento del nombre o `PED-00001` / `REVTMP-...`.

## Roadmap

- Webhook + despliegue AWS (ECS, RDS, S3).
- OCR real y tabla `ocr_results`.
- Generación Excel (`authorization_service`).
- API FastAPI separada del bot.
- CI/CD.
