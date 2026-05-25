# P80 — Pilot production plan (1 vendedor)

Plan de **piloto controlado** con un vendedor durante **1 semana** antes de escalar.

## Objetivo

Validar operación real con volumen bajo, detectar fricción y estabilizar antes de rollout completo.

## Alcance del piloto

| Incluye | Excluye (fase posterior) |
|---------|-------------------------|
| 1 vendedor + 1 supervisor | Todos los vendedores |
| Casos reales limitados (≤ 20/semana) | Migración masiva histórica |
| Horario laboral monitoreado | RBAC granular avanzado |
| Canal web + Telegram del piloto | Nuevos módulos no probados |

## Plan semana 1

| Día | Actividad |
|-----|-----------|
| Lunes | Deploy staging→prod o prod piloto; smoke `/health`; capacitación 30 min |
| Martes | Primeros 3–5 casos reales; revisión documentos |
| Miércoles | Flujo compulsa + autorización con supervisor |
| Jueves | Ventas/cierre; backup manual verificado |
| Viernes | Retrospectiva; métricas; decisión go/no-go |

## Métricas de éxito

| Métrica | Meta |
|---------|------|
| Uptime `/health` | ≥ 99% en horario laboral |
| Errores 500 web | 0 críticos sin workaround |
| Tiempo carga dashboard | < 3 s p95 |
| Documentos subidos OK | ≥ 95% sin reintento manual |
| Compulsas atendidas < SLA | ≥ 90% |
| Satisfacción vendedor (1–5) | ≥ 4 |

## Qué revisar diario

- [ ] `GET /health` y `/health/full`
- [ ] Logs `web` y `bot` (últimas 24h)
- [ ] Cola SharePoint / `upload_status=PENDING`
- [ ] Backup del día (`backups/`)
- [ ] Incidencias del vendedor (chat/grupo soporte)
- [ ] Contador casos abiertos vs cerrados

## Riesgos

| Riesgo | Mitigación |
|--------|------------|
| Token Telegram inválido | Secret rotado; webhook/polling documentado P74 |
| SharePoint caído | Storage local + retry; operar sin Graph temporalmente |
| BD llena / disco | Monitoreo disco; retención backups |
| Error humano en datos | Beta safe mode; no borrado masivo |
| Pico fuera de horario | Comunicar horario piloto |

## Rollback manual

1. Comunicar pausa al vendedor
2. Git: desplegar tag/rama anterior (`docs/P72`, `deploy_staging` equivalente prod)
3. Restaurar BD si migración falló (`docs/P77`)
4. `deleteWebhook` + polling si bot afectado
5. Post-mortem 24h

## Go / no-go (fin semana)

**Go** si: métricas en meta, sin incidente P1 abierto, backup restore probado una vez.

**No-go** si: pérdida datos, RBAC bypass accidental, o > 2 incidentes P1.

## Referencias

- `docs/P70_GO_LIVE_CHECKLIST.md`
- `docs/P79_E2E_BUSINESS_FLOW.md`
- `docs/P76_OBSERVABILITY_MONITORING.md`
