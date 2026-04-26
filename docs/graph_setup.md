# Microsoft Graph + SharePoint setup

## 1) Crear App Registration en Microsoft Entra

1. Ve a `Microsoft Entra ID` -> `App registrations` -> `New registration`.
2. Asigna nombre (ej. `telegram-bot-sharepoint`).
3. Deja tipo de cuenta organizacional según tu tenant.
4. Crea la app.

## 2) Datos que debes copiar

- **Tenant ID** (Directory ID) -> `MS_TENANT_ID`
- **Application (client) ID** -> `MS_CLIENT_ID`
- **Client Secret VALUE** -> `MS_CLIENT_SECRET`

> Importante: usa el **valor** del secreto, no el ID del secreto ni Object ID.

## 3) Permisos requeridos

En `API permissions` agrega (Application permissions):

- `Files.ReadWrite.All`
- `Sites.ReadWrite.All`

`User.Read` puede quedar, pero para client credentials no es necesario para esta integración.

## 4) Conceder consentimiento de administrador

En la misma pantalla de permisos:

- Click en `Grant admin consent`.
- Verifica estado `Granted for <tenant>`.

## 5) Variables en `.env`

```env
MS_TENANT_ID=
MS_CLIENT_ID=
MS_CLIENT_SECRET=
MS_SITE_HOSTNAME=mgaman.sharepoint.com
MS_SITE_PATH=/sites/miunidad
MS_DRIVE_NAME=01_MIGRACIONgdrive
MS_ROOT_FOLDER=Mi unidad/Lingry Nuevo Leon/PEDIDOS
```

## 6) Probar Graph standalone

```bash
python scripts/test_graph_upload.py
```

Debe subir `test_graph_upload.txt` a:

`Mi unidad/Lingry Nuevo Leon/PEDIDOS/SEM 18-2026/TEST VENDEDOR/00000 - CLIENTE PRUEBA/02_PEDIDOS/`

## 7) Correr con Docker Compose

```bash
docker compose down
docker compose up --build -d
docker compose logs -f bot
```

## 8) Logs a revisar

Busca en logs del bot:

- `Obteniendo token de Microsoft Graph`
- `Site ID encontrado`
- `Drive ID encontrado`
- `Ruta final SharePoint`
- `Carpeta creada` / `Carpeta ya existente`
- `Archivo subido correctamente`

## 9) Evitar subir `.env` a GitHub

- Mantén `.env` en `.gitignore`.
- Usa `.env.example` sin secretos reales.
