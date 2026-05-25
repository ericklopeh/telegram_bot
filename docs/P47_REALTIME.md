# P47 — Realtime / Live Updates

- Servicio: `app/services/realtime_service.py` (hub en memoria).
- WebSockets: `/ws/activity`, `/ws/jobs`, `/ws/ops`
- Polling fallback: `GET /api/realtime/poll?channels=activity,jobs,ops`
- Canales: `activity`, `jobs`, `ops`, `pipeline`, `sharepoint`, `dashboard`
- Escalado futuro: Redis pub/sub entre instancias uvicorn.
