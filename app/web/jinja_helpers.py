"""Filtros y globals Jinja compartidos (P31)."""

from __future__ import annotations

from fastapi.templating import Jinja2Templates

from app.web.services.user_friendly_errors import friendly_error_message


def register_web_template_filters(templates: Jinja2Templates) -> None:
    templates.env.filters["friendly_error"] = friendly_error_message
