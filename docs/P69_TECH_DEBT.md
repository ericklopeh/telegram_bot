# P69 — Deuda técnica restante

| Item | Prioridad | Notas |
|------|-----------|-------|
| RBAC endurecido | Post-P69 | No implementado por regla |
| OCR P26 | Post-P69 | Endpoints existen; no activar |
| LLM externo copilot | Media | Briefing heurístico hoy |
| Redis obligatorio multi-worker | Media | Opcional; fallback memoria |
| RQ worker dedicado | Media | Thread local por defecto |
| Drag-drop editor workflow | Baja | Visual pipeline only |
| Tests E2E browser | Baja | Smoke HTTP parcial |

## Resuelto en P69

- Ruta `/activity` duplicada (platform vs cohesion)
- Jobs zombie `running` (reconcile_stale_jobs)
- Realtime sin heartbeat/cleanup
- Logs sin scrub de secretos
- Índices activity/jobs
