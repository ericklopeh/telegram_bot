# Secretos locales (Telegram, DB, Graph)

## Dónde va cada secreto

| Secreto | Archivo | ¿En Git? |
|---------|---------|----------|
| `TELEGRAM_BOT_TOKEN` | `.env` | **No** (gitignore) |
| `WEB_SESSION_SECRET` | `.env` | **No** |
| `POSTGRES_PASSWORD` / `DATABASE_URL` | `.env` | **No** |
| `MS_CLIENT_SECRET` | `.env` | **No** |
| Plantilla sin valores reales | `.env.example` | Sí (`replace-me`) |

## Crear `.env` la primera vez

```bash
cp .env.example .env
# Editar .env con el token de BotFather
```

## GitHub

- **No** pegues el token en código, workflows ni `.env.example`.
- CI usa variables ficticias en `.github/workflows/*.yml`.
- En el VPS usa `.env` en el servidor (fuera del repo público) o secrets del proveedor.

## Si GitHub bloqueó un push

1. Quita el token del commit (no debe estar en archivos trackeados).
2. Rota el token en [@BotFather](https://t.me/BotFather) (`/revoke` o nuevo bot).
3. Pon el token nuevo solo en `.env`.

## Token expuesto por error

Si el token apareció en un chat, issue o commit público: **revócalo en BotFather** y genera uno nuevo.
