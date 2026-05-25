"""Capa de presentación UI del dashboard (P35) — solo mapea métricas y filas existentes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.domain import constants as C
from app.web.services.operational_tracking import (
    ACCION_AUT_GENERADA,
    ACCION_ERROR_SP,
    ACCION_FALTA_CARATULA,
    ACCION_FALTA_ORDEN,
    ACCION_FALTA_PEDIDO,
    ACCION_LISTO_AUT,
    ACCION_PENDIENTE_COMPULSA,
    ACCION_PENDIENTE_OCR,
)

_PIPELINE_LIMIT = 3
_OPS_ALERT_LIMIT = 8
_RECENT_CASES_LIMIT = 10
_ACTIVITY_LIMIT = 8


_STAGE_LABELS: dict[str, str] = {
    "prep_aut": "PREP AUT",
    "docs": "DOCS",
    "compulsa": "COMPULSA",
    "sharepoint": "SHAREPOINT",
    "registro": "REGISTRO",
    "comision": "COMISIÓN",
}

_STAGE_TONES: dict[str, str] = {
    "prep_aut": "amber",
    "docs": "violet",
    "compulsa": "cyan",
    "sharepoint": "red",
    "registro": "blue",
    "comision": "emerald",
}

_SPARK_BY_TONE: dict[str, tuple[str, str]] = {
    "blue": ("#3b82f6", "rgba(59, 130, 246, 0.2)"),
    "amber": ("#f59e0b", "rgba(245, 158, 11, 0.2)"),
    "red": ("#ef4444", "rgba(239, 68, 68, 0.2)"),
    "emerald": ("#10b981", "rgba(16, 185, 129, 0.2)"),
    "violet": ("#8b5cf6", "rgba(139, 92, 246, 0.2)"),
    "orange": ("#f97316", "rgba(249, 115, 22, 0.2)"),
    "slate": ("#64748b", "rgba(100, 116, 139, 0.15)"),
}


@dataclass(frozen=True)
class HeroKpi:
    key: str
    label: str
    value: str | int
    hint: str
    href: str
    tone: str
    icon: str
    trend: str = ""
    trend_dir: str = "neutral"  # up | down | neutral | warn
    spark_value: int = 0
    spark_color: str = "#3b82f6"
    spark_fill: str = "rgba(59, 130, 246, 0.2)"


@dataclass(frozen=True)
class PipelineCasePreview:
    case_id: int
    public_id: str
    client_name: str
    sla_badge: str
    sla_tone: str  # danger | warn | success
    href: str


@dataclass
class PipelineColumn:
    key: str
    label: str
    short_label: str
    count: int
    sla_count: int
    critical_count: int
    href: str
    tone: str
    icon: str
    states_hint: str
    recent_cases: list[PipelineCasePreview] = field(default_factory=list)


def _format_time_ago(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    mins = int((now - dt).total_seconds() // 60)
    if mins < 1:
        return "Ahora"
    if mins < 60:
        return f"Hace {mins} min"
    hours = mins // 60
    if hours < 24:
        return f"Hace {hours} h"
    days = hours // 24
    return f"Hace {days} d"


def stage_label_for_row(row: dict[str, Any]) -> tuple[str, str]:
    key = _pipeline_stage_for_row(row)
    return _STAGE_LABELS.get(key, "SEGUIMIENTO"), _STAGE_TONES.get(key, "muted")


def _hero_spark(tone: str, value: int) -> tuple[int, str, str]:
    color, fill = _SPARK_BY_TONE.get(tone, _SPARK_BY_TONE["blue"])
    return int(value or 0), color, fill


def _trend(current: int, daily: int | None, *, invert: bool = False) -> tuple[str, str]:
    d = int(daily or 0)
    if d <= 0 and current <= 0:
        return "Sin cambio", "neutral"
    if d > 0:
        label = f"+{d} hoy"
        if invert:
            return label, "warn" if current > 0 else "down"
        return label, "up"
    return f"{current} activos", "neutral"


def build_hero_kpis(metricas: dict[str, Any], daily_summary: dict[str, Any]) -> list[HeroKpi]:
    sla = int(metricas.get("sla_abiertos_sin_act_24h") or 0)
    ds = daily_summary or {}
    t_abiertos, d_abiertos = _trend(
        int(metricas.get("total_abiertos") or 0), ds.get("nuevos_casos")
    )
    t_prep, d_prep = _trend(
        int(metricas.get("pendientes_autorizacion") or 0), ds.get("listos_autorizacion")
    )
    t_sp, d_sp = _trend(
        int(metricas.get("docs_upload_failed") or 0),
        ds.get("sharepoint_fallidos"),
        invert=True,
    )
    t_sla_label = f"↑ {ds.get('stale_24h', 0)} hoy" if sla else "En rango"
    t_sla_dir = "warn" if sla else "down"
    abiertos = int(metricas.get("total_abiertos") or 0)
    prep = int(metricas.get("pendientes_autorizacion") or 0)
    sp_f = int(metricas.get("docs_upload_failed") or 0)
    aut_gen = int(metricas.get("autorizaciones_generadas") or 0)
    return [
        HeroKpi(
            "abiertos",
            "Casos activos",
            abiertos,
            "Operación abierta",
            "/casos",
            "blue",
            "briefcase",
            f"↑ {ds.get('nuevos_casos', 0)} hoy" if ds.get("nuevos_casos") else t_abiertos,
            d_abiertos,
            *_hero_spark("blue", abiertos),
        ),
        HeroKpi(
            "prep_aut",
            "Pend. autorización",
            prep,
            "Prep. SNTE",
            "/dashboard?filter=prep_aut",
            "amber",
            "file-clock",
            f"↑ {prep} críticos" if prep else t_prep,
            "warn" if prep else d_prep,
            *_hero_spark("amber", prep),
        ),
        HeroKpi(
            "sp_failed",
            "SharePoint failed",
            sp_f,
            "UPLOAD_FAILED",
            "/dashboard?filter=sp_failed",
            "red",
            "cloud-off",
            t_sp,
            d_sp,
            *_hero_spark("red", sp_f),
        ),
        HeroKpi(
            "comisiones",
            "Comisiones pend.",
            "—",
            "Panel comisiones",
            "/comisiones",
            "emerald",
            "wallet",
            "Ver panel",
            "neutral",
            *_hero_spark("emerald", 0),
        ),
        HeroKpi(
            "ventas",
            "Ventas (semana)",
            aut_gen,
            "Registro comercial",
            "/reportes/comercial",
            "violet",
            "trending-up",
            f"+{ds.get('nuevos_casos', 0)} hoy" if ds.get("nuevos_casos") else "Sin nuevos",
            "up" if ds.get("nuevos_casos") else "neutral",
            *_hero_spark("violet", aut_gen),
        ),
        HeroKpi(
            "sla",
            "SLA crítico (>24h)",
            sla,
            "Sin avance prolongado",
            "/dashboard?filter=stale_24h",
            "orange" if sla else "slate",
            "alarm-clock",
            t_sla_label,
            t_sla_dir,
            *_hero_spark("orange" if sla else "slate", sla),
        ),
    ]


def _pipeline_stage_for_row(row: dict[str, Any]) -> str:
    case = row["case"]
    action = row["siguiente_accion"]
    status = case.current_status

    if row.get("sharepoint_estado") == "fallido" or action == ACCION_ERROR_SP:
        return "sharepoint"
    if row.get("sharepoint_estado") == "pendiente":
        return "sharepoint"
    if status in (C.ST_PED_EN_COMPULSA, C.ST_PED_PEND_COMPULSA) or action == ACCION_PENDIENTE_COMPULSA:
        return "compulsa"
    if action == ACCION_AUT_GENERADA or status == C.ST_PED_AUT_GENERADA:
        return "registro"
    if action in (ACCION_FALTA_PEDIDO, ACCION_FALTA_ORDEN, ACCION_FALTA_CARATULA) or not row.get(
        "checklist_ok", True
    ):
        return "docs"
    if status == C.ST_PED_PREP_AUT or action in (ACCION_LISTO_AUT, ACCION_PENDIENTE_OCR):
        return "prep_aut"
    if row.get("autorizacion_generada"):
        return "comision"
    return "prep_aut"


def _sla_for_row(row: dict[str, Any]) -> tuple[str, str]:
    if row.get("sin_avance_24h"):
        return "24h+", "danger"
    hours = row.get("antiguedad_horas")
    if hours is not None and hours >= 12:
        return "12h+", "warn"
    return "OK", "success"


def _row_to_preview(row: dict[str, Any]) -> PipelineCasePreview:
    case = row["case"]
    sla_label, sla_tone = _sla_for_row(row)
    return PipelineCasePreview(
        case_id=case.id,
        public_id=case.public_id,
        client_name=(case.client_name or "—")[:28],
        sla_badge=sla_label,
        sla_tone=sla_tone,
        href=f"/casos/{case.id}",
    )


def build_pipeline_columns(metricas: dict[str, Any]) -> list[PipelineColumn]:
    """Pipeline operacional — conteos desde metricas."""
    return [
        PipelineColumn(
            "prep_aut",
            "Prep. autorización",
            "PREP AUT",
            int(metricas.get("pendientes_autorizacion") or 0),
            int(metricas.get("sla_prep_aut_mas_24h") or 0),
            int(metricas.get("sla_prep_aut_mas_24h") or 0),
            "/dashboard?filter=prep_aut",
            "amber",
            "file-spreadsheet",
            f"Sin Excel SNTE: {metricas.get('prep_sin_excel_snte', 0)}",
        ),
        PipelineColumn(
            "docs",
            "Documentación",
            "DOCS",
            int(metricas.get("pedidos_checklist_incompleto") or 0),
            0,
            0,
            "/dashboard?filter=missing_docs",
            "violet",
            "folder-open",
            f"Pend. subida: {metricas.get('docs_pending_upload', 0)}",
        ),
        PipelineColumn(
            "compulsa",
            "Compulsa",
            "COMPULSA",
            int(metricas.get("pendientes_compulsa") or 0),
            int(metricas.get("sla_compulsa_mas_24h") or 0),
            int(metricas.get("sla_compulsa_mas_24h") or 0),
            "/dashboard?filter=compulsa",
            "cyan",
            "scale",
            f"OK: {metricas.get('compulsa_ok', 0)}",
        ),
        PipelineColumn(
            "sharepoint",
            "SharePoint",
            "SHAREPOINT",
            int(metricas.get("docs_upload_failed") or 0) + int(metricas.get("docs_pending_upload") or 0),
            0,
            int(metricas.get("docs_upload_failed") or 0),
            "/dashboard?filter=sp_failed",
            "red",
            "cloud-upload",
            f"Fallidos: {metricas.get('docs_upload_failed', 0)}",
        ),
        PipelineColumn(
            "registro",
            "Registro ventas",
            "REGISTRO",
            int(metricas.get("autorizaciones_generadas") or 0),
            0,
            0,
            "/ventas/pendientes",
            "blue",
            "clipboard-list",
            "Cola Excel",
        ),
        PipelineColumn(
            "comision",
            "Comisión",
            "COMISIÓN",
            0,
            0,
            0,
            "/comisiones",
            "emerald",
            "coins",
            "Post-registro",
        ),
    ]


def enrich_pipeline_with_cases(
    columns: list[PipelineColumn],
    pendientes_tabla: list[dict[str, Any]],
) -> list[PipelineColumn]:
    """Asigna hasta 3 casos recientes por columna desde pendientes_tabla (P14)."""
    buckets: dict[str, list[PipelineCasePreview]] = {c.key: [] for c in columns}
    seen: dict[str, set[int]] = {c.key: set() for c in columns}

    for row in pendientes_tabla:
        stage = _pipeline_stage_for_row(row)
        if stage not in buckets:
            continue
        cid = row["case"].id
        if cid in seen[stage]:
            continue
        if len(buckets[stage]) >= _PIPELINE_LIMIT:
            continue
        buckets[stage].append(_row_to_preview(row))
        seen[stage].add(cid)

    enriched: list[PipelineColumn] = []
    for col in columns:
        col.recent_cases = buckets.get(col.key, [])
        enriched.append(col)
    return enriched


def _severity_label(severity: str, alert_type: str) -> tuple[str, str]:
    sev = (severity or "").lower()
    if sev == "danger" or alert_type == "sharepoint_failed":
        return "Crítico", "danger"
    if sev == "success":
        return "OK", "success"
    if sev == "info":
        return "Info", "info"
    return "Advertencia", "warning"


def build_ops_alert_rows(
    operational_alerts: list[Any],
    metricas: dict[str, Any],
    daily_summary: dict[str, Any],
    *,
    limit: int = _OPS_ALERT_LIMIT,
) -> list[dict[str, Any]]:
    """Filas compactas para tabla del centro de operaciones."""
    rows: list[dict[str, Any]] = []
    for alert in operational_alerts[:limit]:
        at = getattr(alert, "alert_type", "alert")
        sev = getattr(alert, "severity", "warning")
        label, tone = _severity_label(sev, at)
        case_id = getattr(alert, "case_id", None)
        case = getattr(alert, "case", None)
        public_id = case.public_id if case else (f"#{case_id}" if case_id else "—")
        updated = getattr(alert, "updated_at", None)
        rows.append(
            {
                "severity_label": label,
                "severity_tone": tone,
                "type": at.replace("_", " ").title()[:20],
                "message": getattr(alert, "message", "")[:120],
                "case_label": public_id,
                "case_href": f"/casos/{case_id}" if case_id else None,
                "time_label": _format_time_ago(updated),
                "recovery_href": "/ops",
            }
        )

    if len(rows) < limit and int(metricas.get("docs_upload_failed") or 0) > 0:
        if not any(r["type"] == "sharepoint_failed" for r in rows):
            rows.append(
                {
                    "severity_label": "Crítico",
                    "severity_tone": "danger",
                    "type": "upload_failed",
                    "message": f"{metricas['docs_upload_failed']} documentos con UPLOAD_FAILED",
                    "case_label": "—",
                    "case_href": None,
                    "time_label": "Ahora",
                    "case_href": None,
                    "recovery_href": "/dashboard?filter=sp_failed",
                }
            )
    if len(rows) < limit and int(daily_summary.get("sharepoint_fallidos") or 0) > 0:
        rows.append(
            {
                "severity_label": "Crítico",
                "severity_tone": "danger",
                "type": "SharePoint",
                "message": f"{daily_summary['sharepoint_fallidos']} fallos SharePoint hoy (P16)",
                "case_label": "—",
                "case_href": None,
                "time_label": "Hoy",
                "recovery_href": "/ops",
            }
        )
    return rows[:limit]


def build_recent_cases_rows(
    pendientes_tabla: list[dict[str, Any]],
    *,
    limit: int = _RECENT_CASES_LIMIT,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in pendientes_tabla[:limit]:
        case = row["case"]
        sp = row.get("sharepoint_estado") or "—"
        sp_tone = (
            "danger"
            if sp == "fallido"
            else "warning"
            if sp == "pendiente"
            else "success"
            if sp == "sincronizado"
            else "muted"
        )
        stage_label, stage_tone = stage_label_for_row(row)
        updated = case.updated_at
        out.append(
            {
                "public_id": case.public_id,
                "client_name": case.client_name or "—",
                "seller_name": case.seller_name or "—",
                "status": case.current_status,
                "stage_label": stage_label,
                "stage_tone": stage_tone,
                "action": row.get("siguiente_accion", "—"),
                "age": row.get("antiguedad_label", "—"),
                "time_ago": _format_time_ago(updated),
                "sla_badge": "24h+" if row.get("sin_avance_24h") else "OK",
                "sla_tone": "danger" if row.get("sin_avance_24h") else "success",
                "href": f"/casos/{case.id}",
                "sp_tone": sp_tone,
                "sp_label": sp.upper() if sp != "—" else "—",
            }
        )
    return out


def build_activity_feed(
    operational_alerts: list[Any],
    pendientes_tabla: list[dict[str, Any]],
    *,
    limit: int = _ACTIVITY_LIMIT,
) -> list[dict[str, Any]]:
    _alert_icons = {
        "sharepoint_failed": ("cloud-off", "danger", "Fallo al subir documento"),
        "stale_case": ("clock", "warning", "Caso sin avance"),
        "ready_for_auth": ("check-circle", "success", "Listo para autorización"),
        "low_ocr": ("scan-text", "info", "Pendiente OCR"),
        "multiple_regen": ("refresh-cw", "warning", "Regeneración múltiple"),
    }
    feed: list[dict[str, Any]] = []
    for alert in operational_alerts:
        if len(feed) >= limit:
            break
        at = getattr(alert, "alert_type", "evento")
        case_id = getattr(alert, "case_id", None)
        case = getattr(alert, "case", None)
        icon, tone, title = _alert_icons.get(at, ("alert-circle", "warning", at.replace("_", " ").title()))
        detail = (getattr(alert, "message", "") or "")[:80]
        if case_id and case:
            detail = f"{case.public_id} · {detail}"
        feed.append(
            {
                "icon": icon,
                "tone": tone,
                "title": title,
                "detail": detail,
                "time": _format_time_ago(getattr(alert, "updated_at", None)),
                "href": f"/casos/{case_id}" if case_id else None,
            }
        )
    for row in pendientes_tabla:
        if len(feed) >= limit:
            break
        case = row["case"]
        feed.append(
            {
                "icon": "folder-clock",
                "tone": "info",
                "title": row.get("siguiente_accion", "Seguimiento"),
                "detail": f"{case.public_id} · {case.client_name or '—'}",
                "time": _format_time_ago(case.updated_at),
                "href": f"/casos/{case.id}",
            }
        )
    return feed[:limit]


def build_trend_charts(metricas: dict[str, Any], daily_summary: dict[str, Any]) -> list[dict[str, Any]]:
    """Datos para gráficas de tendencia (valores actuales; serie en JS)."""
    ds = daily_summary or {}
    sla_ok = max(
        0,
        100
        - min(
            100,
            (int(metricas.get("sla_abiertos_sin_act_24h") or 0) * 15)
            + (int(metricas.get("sla_prep_aut_mas_24h") or 0) * 10),
        ),
    )
    return [
        {
            "key": "casos",
            "title": "Casos creados",
            "value": ds.get("nuevos_casos", 0),
            "subtitle": "Hoy · P16",
            "color": "#3b82f6",
            "fill": "rgba(59, 130, 246, 0.15)",
            "chart_type": "line",
        },
        {
            "key": "ventas",
            "title": "Ventas (semana)",
            "value": metricas.get("autorizaciones_generadas", 0),
            "subtitle": "Autorizaciones generadas",
            "color": "#10b981",
            "fill": "rgba(16, 185, 129, 0.2)",
            "chart_type": "bar",
        },
        {
            "key": "comisiones",
            "title": "Comisiones generadas",
            "value": metricas.get("compulsa_ok", 0),
            "subtitle": "Indicador operativo",
            "color": "#8b5cf6",
            "fill": "rgba(139, 92, 246, 0.15)",
            "chart_type": "line",
        },
        {
            "key": "sla",
            "title": "SLA cumplimiento",
            "value": sla_ok,
            "subtitle": f"{sla_ok}% OK estimado",
            "color": "#22c55e",
            "fill": "rgba(34, 197, 94, 0.15)",
            "is_percent": True,
            "chart_type": "doughnut",
        },
    ]


def build_ops_center_items(metricas: dict[str, Any], daily_summary: dict[str, Any]) -> list[dict[str, Any]]:
    """Resumen numérico rápido del centro de ops (chips)."""
    items: list[dict[str, Any]] = []
    for key, title, count_key, sev, href, icon in (
        ("sp_failed", "SP fallidos", "docs_upload_failed", "danger", "/dashboard?filter=sp_failed", "cloud-off"),
        ("sp_pending", "Subidas pend.", "docs_pending_upload", "warning", "/dashboard?filter=sp_pending", "cloud-upload"),
        ("checklist", "Checklist", "pedidos_checklist_incompleto", "warning", "/dashboard?filter=missing_docs", "list-checks"),
        ("stale", "Atorados 24h", "sla_abiertos_sin_act_24h", "danger", "/dashboard?filter=stale_24h", "clock"),
    ):
        n = int(metricas.get(count_key) or 0)
        if n > 0:
            items.append(
                {"key": key, "title": title, "count": n, "severity": sev, "href": href, "icon": icon}
            )
    if int(daily_summary.get("sharepoint_fallidos") or 0) > 0:
        items.append(
            {
                "key": "sp_day",
                "title": "SP hoy",
                "count": daily_summary["sharepoint_fallidos"],
                "severity": "danger",
                "href": "/ops",
                "icon": "alert-triangle",
            }
        )
    return items[:6]
