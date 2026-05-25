"""P54 — plantillas dinámicas."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enterprise_advanced import DynamicTemplate, TemplateVersion

_VAR_RE = re.compile(r"\{\{\s*(\w+)\s*\}\}")


class TemplateService:
    def get_template(self, db: Session, template_key: str) -> DynamicTemplate | None:
        return db.scalar(select(DynamicTemplate).where(DynamicTemplate.template_key == template_key))

    def get_active_content(self, db: Session, template_key: str) -> str | None:
        tpl = self.get_template(db, template_key)
        if not tpl:
            return None
        ver = db.scalar(
            select(TemplateVersion).where(
                TemplateVersion.template_id == tpl.id,
                TemplateVersion.version == tpl.active_version,
            )
        )
        return ver.content if ver else None

    def render(self, content: str, variables: dict[str, Any]) -> str:
        def repl(match: re.Match) -> str:
            key = match.group(1)
            return str(variables.get(key, match.group(0)))

        return _VAR_RE.sub(repl, content)

    def preview(self, db: Session, template_key: str, variables: dict[str, Any]) -> str:
        content = self.get_active_content(db, template_key) or ""
        return self.render(content, variables)

    def upsert_template(
        self,
        db: Session,
        *,
        template_key: str,
        name: str,
        template_type: str,
        content: str,
        variables: dict[str, Any] | None = None,
        created_by: str | None = None,
    ) -> DynamicTemplate:
        tpl = self.get_template(db, template_key)
        if not tpl:
            tpl = DynamicTemplate(template_key=template_key, name=name, template_type=template_type)
            db.add(tpl)
            db.flush()
        ver = TemplateVersion(
            template_id=tpl.id,
            version=tpl.active_version,
            content=content,
            variables_json=variables,
            created_by=created_by,
        )
        db.add(ver)
        db.flush()
        try:
            from app.services.platform_cohesion_service import safe_cohesion_emit

            safe_cohesion_emit(
                db,
                action="template_updated",
                title=f"Plantilla: {name}",
                entity_type="template",
                entity_id=tpl.id,
                actor_label=created_by,
                source="templates",
            )
        except Exception:
            pass
        return tpl
