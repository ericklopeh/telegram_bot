"""P55 — attachments universales."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.enterprise_advanced import Attachment, AttachmentRelation


class AttachmentService:
    def store_file(
        self,
        db: Session,
        *,
        filename: str,
        data: bytes,
        mime_type: str | None,
        entity_type: str,
        entity_id: int,
        attachment_type: str = "file",
        uploaded_by: str | None = None,
        company_id: int = 1,
        relation_role: str = "evidence",
    ) -> Attachment:
        settings = get_settings()
        base = Path(settings.storage_root) / "attachments" / f"tenant_{company_id}"
        base.mkdir(parents=True, exist_ok=True)
        safe_name = f"{uuid.uuid4().hex[:12]}_{filename}"
        path = base / safe_name
        path.write_bytes(data)

        att = Attachment(
            filename=filename,
            stored_path=str(path),
            mime_type=mime_type,
            size_bytes=len(data),
            attachment_type=attachment_type,
            uploaded_by=uploaded_by,
            company_id=company_id,
        )
        db.add(att)
        db.flush()
        db.add(
            AttachmentRelation(
                attachment_id=att.id,
                entity_type=entity_type,
                entity_id=entity_id,
                relation_role=relation_role,
            )
        )
        db.flush()
        try:
            from app.services.platform_cohesion_service import safe_cohesion_emit

            safe_cohesion_emit(
                db,
                action="attachment_uploaded",
                title=f"Adjunto: {filename}",
                entity_type=entity_type,
                entity_id=entity_id,
                actor_label=uploaded_by,
                source="attachments",
                company_id=company_id,
            )
        except Exception:
            pass
        return att

    def list_for_entity(self, db: Session, entity_type: str, entity_id: int) -> list[dict[str, Any]]:
        stmt = (
            select(Attachment, AttachmentRelation)
            .join(AttachmentRelation, AttachmentRelation.attachment_id == Attachment.id)
            .where(
                AttachmentRelation.entity_type == entity_type,
                AttachmentRelation.entity_id == entity_id,
            )
        )
        out = []
        for att, rel in db.execute(stmt).all():
            out.append(
                {
                    "id": att.id,
                    "filename": att.filename,
                    "mime_type": att.mime_type,
                    "size_bytes": att.size_bytes,
                    "type": att.attachment_type,
                    "role": rel.relation_role,
                    "created_at": att.created_at.isoformat() if att.created_at else None,
                }
            )
        return out
