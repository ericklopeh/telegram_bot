# P69 — Stabilization Freeze

Fase de estabilización enterprise antes de RBAC/OCR/producción final.

## Alcance

- Smoke system (`scripts/smoke_check_web.py`)
- Consolidación rutas (activity unificado en `cohesion.py`)
- Hardening realtime (rate limit, heartbeat WS, cleanup)
- Hardening jobs (stale reset, cancel, idempotencia running)
- Performance summary: `GET /admin/performance/summary`
- Logging separado: `realtime.log`, `jobs.log`, `compliance.log`, scrub de secretos
- Migración índices: `o1p2q3r4s5t6_p69_stabilization`
- UX unificado vía `cohesion.css` / `cohesion.js`

## Deploy

```bash
alembic upgrade head
python scripts/smoke_check_web.py
python -m pytest -q
```

Opcional con servidor local:

```bash
python scripts/smoke_check_web.py --base-url http://127.0.0.1:8000
```
