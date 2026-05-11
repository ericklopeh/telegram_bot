# Módulo SNTE - Documentación Oficial

## 1. Resumen del módulo
El módulo SNTE permite la generación automatizada de documentos requeridos para las autorizaciones de crédito/venta a trabajadores del Sindicato Nacional de Trabajadores de la Educación (SNTE). 
Genera automáticamente dos archivos a partir de los datos ingresados:
- El **Excel Master de Autorización**.
- La **Orden de Descuento SNTE en PDF**.

Se utiliza directamente desde la aplicación web (Sistema Gaman), incrustado en la vista de detalle de cada caso que requiera autorización.

---

## 2. Flujo completo
El ciclo de vida del módulo sigue esta secuencia:
1. **Web:** El usuario entra a la vista de detalle de un caso.
2. **Modal:** Se abre el modal `Generar Autorización SNTE` y se capturan los datos (cliente, quincenas, productos, etc.).
3. **AuthorizationService:** Recibe el formulario web y orquesta la inyección de datos en las plantillas.
4. **Excel/PDF:** Se escriben los datos en el Excel y el PDF utilizando ReportLab/PyPDF y OpenPyXL, calculando automáticamente totales y aplicando la lógica de negocio.
5. **Document:** Se guardan físicamente en el disco local y se registran en PostgreSQL como entidades `Document`. Si ya existían documentos previos, la versión vieja se desactiva (`is_active=False`).
6. **SharePoint Background:** Se dispara un *Background Task* de FastAPI que sube los dos archivos de forma asíncrona a Microsoft SharePoint.
7. **Estado del Caso:** Se hace la transición del caso a `ST_PED_AUT_GENERADA`.
8. **Telegram:** En otro *Background Task*, el sistema localiza al vendedor y a los administradores activos y les envía una notificación vía Telegram indicando el éxito de la generación.

---

## 3. Archivos principales
La arquitectura del módulo se apoya en los siguientes archivos clave:
- `app/services/authorization_service.py`: Controlador principal que orquesta la generación dual y manipula el Excel de Autorización (calcula sumas, mapea celdas y filas dinámicas de productos).
- `app/services/pdf_orden_service.py`: Encargado exclusivamente de inyectar el texto en coordenadas específicas sobre el PDF de la Orden de Descuento utilizando `pypdf` y `reportlab`.
- `app/web/routes/authorizations.py`: Endpoint (Controlador Web) que recibe el `POST` del modal, dispara el servicio, cambia el estado del caso, hace *rollback* si algo falla, y manda la subida a SharePoint/Telegram a segundo plano.
- `app/web/templates/case_detail.html`: Interfaz web de usuario. Contiene el modal de captura, el historial de generaciones (`AuthorizationJob`) y las validaciones visuales (Doble-submit prevention, Regex en fechas).
- `storage/templates/plantilla_master_autorizaciones.xlsx`: Archivo fuente base para el Excel de autorización.
- `storage/templates/plantilla_orden_snte.pdf`: Archivo fuente base para el PDF de la Orden de Descuento.

---

## 4. Plantillas requeridas
- **Ubicación:** `storage/templates/`
- **Nombres exactos esperados:** 
  - `plantilla_master_autorizaciones.xlsx`
  - `plantilla_orden_snte.pdf`
- **¿Qué pasa si faltan?**: El `AuthorizationService` lanzará una excepción controlada `TemplateNotFoundError`. El endpoint web (`authorizations.py`) la atrapará, ejecutará un `db.rollback()` para proteger la BD, y regresará al usuario a la pantalla del caso mostrando una alerta roja indicando qué archivo falta.

---

## 5. Campos del modal
La vista captura datos temporales ("al vuelo") que no mutan el modelo de BD actual (por ahora):
- **Cliente:** Nombre completo del agremiado.
- **RFC:** Con homoclave.
- **Categoría:** Nivel o categoría laboral.
- **Domicilio:** Dirección completa.
- **Teléfonos:** Datos de contacto.
- **Correo:** Email.
- **Fecha venta:** Formato `DD/MM/AAAA`.
- **Qna inicial:** Quincena de inicio. Formato `QQ-AAAA` (ej. `10-2026`).
- **Plazo:** Quincenas totales.
- **Descuento:** Monto de retención quincenal.
- **Monto:** Calculado automáticamente si el usuario lo deja en blanco (suma el total de los productos de las 5 filas permitidas).

---

## 6. Estados y documentos
- **Estado antes:** `En preparación de autorización` (`ST_PED_PREP_AUT`).
- **Estado después:** `Autorización generada` (`ST_PED_AUT_GENERADA`).
- **Tipos de Document generados:**
  1. `DOC_AUTORIZACION_SNTE` (Excel)
  2. `DOC_ORDEN_SNTE_PDF` (PDF)
- **Upload Status esperado:** Inicialmente quedan como `PENDING_UPLOAD`. A los pocos segundos (gracias al *background task*) pasan a `UPLOADED`. Si falla SharePoint, pasarán a `UPLOAD_FAILED`.

---

## 7. SharePoint
- **Subida en Background:** Usando `fastapi.BackgroundTasks`, el sistema ejecuta `SharePointDocumentService().upload_document(payload)` sin bloquear la respuesta web.
- **¿Qué pasa si falla?**: Se hace un `catch` interno. El `document_status` pasa a `UPLOAD_FAILED`. La integridad de la autorización local queda intacta.
- **Retry Queue:** Al fallar, el archivo se empuja a la tabla `sharepoint_retry_queue`. Un Cron Job periódico en el bot reintentará subirlo hasta un máximo de configurado de intentos.

---

## 8. Telegram
- **Notificaciones:** 
  1. **Al vendedor** que inició el caso: *"✅ Tu autorización SNTE fue generada y está en proceso de carga a SharePoint."*
  2. **A los administradores** activos (Roles: ADMIN, SISTEMAS, AUTORIZACION): *"📄 Autorización SNTE generada para el folio [PED-XXX] - [Nombre]."*
- **¿Qué pasa si falla?**: El intento de envío (`bot.send_message`) está dentro de un bloque `try-except` propio. Si la API de Telegram cae, o el bot no tiene permisos, se escribirá un error en el Log (`log.exception`) pero **no afectará** la generación de los documentos ni el estado del caso en el sistema web.

---

## 9. Checklist de pruebas manuales
Antes de liberar este módulo en producción, verifique:
- [ ] **Generación exitosa:** Llenar el formulario y recibir "Success". Aparecen los archivos para descarga y el Excel y PDF coinciden.
- [ ] **Plantilla faltante:** Renombrar `plantilla_orden_snte.pdf`, intentar generar, debe rebotar con error rojo. El estado no cambia.
- [ ] **Doble submit:** Dar doble clic o Enter rápidamente en el botón "Generar Archivos". El botón debe deshabilitarse, ponerse gris y mostrar el spinner "Generando...".
- [ ] **Regeneración:** Entrar a un caso que ya tenga documentos. El botón será Naranja ("Regenerar..."). Al darle, los documentos viejos desaparecen de la UI activa y salen los nuevos.
- [ ] **SharePoint success/fail:** Probar con/sin internet. Sin internet debe quedar el documento en amarillo/rojo ("Pendiente/Error"). Con internet, recargar al segundo y debe salir "Subido" (verde) con el botón a SharePoint.
- [ ] **Telegram success/fail:** Validar la recepción del mensaje en el celular del vendedor. Luego, poner un Token falso temporal en el `.env` y probar: no debe romperse el flujo web, solo generar logs.
- [ ] **Descarga local:** Probar el botón azul ("Descargar") de la tabla de documentos, que abra el Excel y el PDF en su PC local sin daño (archivo corrupto).
- [ ] **Historial:** En la sección "Historial de Autorizaciones SNTE", cada generación debe reflejar fecha, estatus, nombre del archivo y la acción.

---

## 10. Limitaciones actuales
- **Refinanciamientos no soportados:** La Fase 7 se restringió únicamente a "Venta Nueva / Mueble".
- **Sin validación OCR:** La lectura de recibos de nómina (talones) no interactúa aún para prellenar o validar los datos de la Autorización.
- **Parámetros no persistidos:** Los datos tecleados (dirección, RFC, etc.) se escriben al archivo y se evaporan de la base de datos (se captura "al vuelo").
- **Historial básico:** `AuthorizationJob` actualmente solo registra la ruta del archivo, template y estatus, pero no guarda quién fue el usuario que dio el clic (la columna existe en logs pero no en la tabla `authorization_jobs`), ni el JSON de parámetros usados.

---

## 11. Próximas fases recomendadas
- **Fase 7.8 - Persistir parámetros de generación:** Migración para agregar la columna `parameters (JSONB)` y `action_user (String)` en `AuthorizationJob`. Esto permitirá re-popular el modal y tener una auditoría perfecta.
- **Fase 8 - Refinanciamientos:** Lógica para cruzar saldos anteriores y usar plantillas de liquidación, alterando el descuento y la quincena.
- **Fase 9 - OCR:** Usar las métricas de la herramienta de escaneo de Talon/Nómina y cruzar el RFC tecleado vs el del recibo.
