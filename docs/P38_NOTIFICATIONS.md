# P38 — Notificaciones enterprise

## Servicio
`app/services/enterprise_notification_service.py`

## Canales
- `telegram` (log / integración con alertas operativas)
- `email` (SMTP si `SMTP_HOST` configurado)
- `webhook` (`NOTIFICATION_WEBHOOK_URL`)
- `slack` (`NOTIFICATION_SLACK_WEBHOOK`)

## Eventos
`sharepoint_failed`, `case_stale_24h`, `checklist_incomplete`, `import_finished`, `commission_generated`, `workflow_approved`, `critical_incident`

## Tablas
- `notification_preferences`
- `notification_deliveries` (historial + throttling 5 min)

## Prueba
`GET /admin/notifications/test` (admin)
