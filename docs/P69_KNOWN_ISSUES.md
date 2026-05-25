# P69 — Known issues

1. **Smoke HTTP sin auth**: rutas protegidas devuelven 302/401 — marcado OK/WARN, no FAIL.
2. **WebSocket smoke**: requiere `websockets` y servidor activo con `--base-url`.
3. **Host `db` en DATABASE_URL**: smoke DB falla fuera de Docker; usar `localhost:5433`.
4. **Rate limit realtime**: 120 msg/s global; burst alto puede descartar publishes.
5. **Job `cancelled`**: estado nuevo; UI jobs puede mostrar como texto libre.

## Workarounds

- Staging: `SMOKE_BASE_URL=http://web:8000` dentro de compose.
- Performance: revisar `/admin/performance` y API `/admin/performance/summary`.
