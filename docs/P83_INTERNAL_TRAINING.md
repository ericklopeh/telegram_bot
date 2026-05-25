# P83 — Internal training and SOP

Documentación operativa para usuarios internos.

## Manual vendedor

1. Iniciar sesión web con usuario asignado.
2. Revisar dashboard: casos pendientes y compulsas.
3. Abrir caso → subir documentos en orden (pedido, orden descuento, carátula).
4. Esperar autorización SNTE (no generar si no tiene permiso).
5. Atender correcciones si el estado lo indica.
6. Captura de ventas: completar checklist antes de enviar a validación.
7. Telegram: enviar fotos/PDF solo al bot oficial; verificar semana activa.

**Límites RBAC:** crear/editar sus casos; no aprobar ni exportar Excel global.

## Manual supervisor

1. Bandeja de autorizaciones y revisión talón.
2. Aprobar/generar SNTE y refinanciamiento.
3. Gestionar compulsa y estados workflow.
4. Exportar Excel ventas/contratos cuando estén listos.
5. Revisar `/admin/audit` si es admin; supervisores usan reportes operativos.

## Manual admin

1. Usuarios y roles en BD (semilla: `scripts/seed_web_demo_users.py` solo dev).
2. Configuración `.env` en servidor (secretos).
3. Deploy staging/prod vía P72 / scripts.
4. Backups diarios y restore de prueba (P77).
5. Auditoría RBAC en `/admin/audit`.
6. Métricas `/metrics` y health monitors (P76).

## Qué hacer si…

| Problema | Pasos |
|----------|--------|
| **Falla upload** | Verificar tamaño archivo, permiso CREATE, checklist; revisar logs web |
| **Falla compulsa** | Estado caso, permiso compulsa (supervisor), chat Telegram |
| **Falla export** | Permiso EXPORT, `ventas_export_path` existe, reintento registro |
| **Falta documento** | Subir tipo faltante; revisar timeline |
| **Telegram no responde** | Token válido; polling activo o webhook P74; `deleteWebhook` si conflicto |

## SOP diario

- [ ] Revisar `/health` y alertas
- [ ] Casos en corrección/compulsa
- [ ] Cola SharePoint PENDING
- [ ] Backup OK
- [ ] Incidencias abiertas (ops)

## SOP semanal

- [ ] Restore de prueba en entorno no prod
- [ ] Revisión métricas piloto
- [ ] Rotación secretos si hubo incidente
- [ ] Actualizar usuarios inactivos

## Checklist apertura (lunes)

- [ ] Servicios Docker up
- [ ] Semana activa correcta
- [ ] Smoke `./scripts/smoke_health.sh`

## Checklist cierre (viernes)

- [ ] Backup ejecutado
- [ ] Casos críticos documentados
- [ ] Log errores 5xx revisado

## Referencias

- `docs/P80_PILOT_PRODUCTION_PLAN.md`
- `docs/P81_RBAC_AND_AUDIT.md`
