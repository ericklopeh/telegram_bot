"""P65 — command palette global (CTRL+K)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.global_search_service import GlobalSearchService


class CommandPaletteService:
    QUICK_ACTIONS = [
        {"id": "dash", "label": "Dashboard operativo", "href": "/dashboard", "type": "action"},
        {"id": "cases", "label": "Ver casos", "href": "/casos", "type": "action"},
        {"id": "task", "label": "Crear tarea", "href": "/tasks", "type": "action"},
        {"id": "cockpit", "label": "Supervisor cockpit", "href": "/supervisor/cockpit", "type": "action"},
        {"id": "activity", "label": "Actividad global", "href": "/activity", "type": "action"},
        {"id": "workflow", "label": "Workflow visual", "href": "/workflow/visual", "type": "action"},
        {"id": "copilot", "label": "AI Copilot", "href": "/ai/copilot", "type": "action"},
        {"id": "ops", "label": "Recovery / Ops", "href": "/ops", "type": "action"},
    ]

    def search(self, db: Session, query: str) -> dict[str, Any]:
        q = (query or "").strip().lower()
        actions = [a for a in self.QUICK_ACTIONS if not q or q in a["label"].lower()]
        results = {"query": query, "actions": actions, "groups": []}
        if len(q) >= 2:
            gs = GlobalSearchService().search(db, query)
            results["groups"] = gs.get("groups", [])
            results["total"] = gs.get("total", 0)
        return results
