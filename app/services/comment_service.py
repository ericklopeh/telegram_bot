"""P48 — comentarios y notas internas."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enterprise_advanced import CaseComment, CommentAttachment

_MENTION_RE = re.compile(r"@(\w+)")


class CommentService:
    def list_for_case(self, db: Session, case_id: int, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = list(
            db.scalars(
                select(CaseComment)
                .where(CaseComment.case_id == case_id)
                .order_by(CaseComment.created_at.desc())
                .limit(limit)
            ).all()
        )
        return [self._serialize(c) for c in rows]

    def add_comment(
        self,
        db: Session,
        case_id: int,
        *,
        body: str,
        author_user_id: int | None,
        author_label: str,
        entity_type: str = "case",
        entity_id: int | None = None,
        company_id: int = 1,
    ) -> CaseComment:
        mentions = _MENTION_RE.findall(body)
        comment = CaseComment(
            case_id=case_id,
            entity_type=entity_type,
            entity_id=entity_id or case_id,
            author_user_id=author_user_id,
            author_label=author_label,
            body=body.strip(),
            mentions_json=mentions or None,
            company_id=company_id,
        )
        db.add(comment)
        db.flush()
        from app.services.platform_cohesion_service import PlatformCohesionService

        PlatformCohesionService().emit(
            db,
            action="comment_created",
            title=f"Comentario de {author_label}",
            entity_type="case",
            entity_id=case_id,
            detail=body[:200],
            actor_user_id=author_user_id,
            actor_label=author_label,
            href=f"/casos/{case_id}",
            source="web",
            automation_trigger="comment_created",
            automation_context={"case_id": case_id, "href": f"/casos/{case_id}"},
            skip_automation=False,
        )
        return comment

    def _serialize(self, c: CaseComment) -> dict[str, Any]:
        return {
            "id": c.id,
            "case_id": c.case_id,
            "author_label": c.author_label,
            "body": c.body,
            "mentions": c.mentions_json or [],
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
