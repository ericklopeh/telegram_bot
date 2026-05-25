"""P56 — auditoría y compliance avanzado."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enterprise_advanced import AuditEntry, ComplianceEvent, DigitalSignature


class ComplianceService:
    def record_audit(
        self,
        db: Session,
        *,
        entity_type: str,
        entity_id: int | None,
        action: str,
        actor_label: str | None,
        before: dict[str, Any] | None,
        after: dict[str, Any] | None,
        company_id: int = 1,
    ) -> AuditEntry:
        payload = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "before": before,
            "after": after,
        }
        immutable_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()
        entry = AuditEntry(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_label=actor_label,
            before_json=before,
            after_json=after,
            immutable_hash=immutable_hash,
            company_id=company_id,
        )
        db.add(entry)
        db.flush()
        return entry

    def record_event(
        self,
        db: Session,
        *,
        event_type: str,
        message: str,
        severity: str = "info",
        entity_type: str | None = None,
        entity_id: int | None = None,
        metadata: dict[str, Any] | None = None,
        company_id: int = 1,
    ) -> ComplianceEvent:
        ev = ComplianceEvent(
            event_type=event_type,
            message=message,
            severity=severity,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata_json=metadata,
            company_id=company_id,
        )
        db.add(ev)
        db.flush()
        return ev

    def list_audit(
        self,
        db: Session,
        *,
        entity_type: str | None = None,
        limit: int = 100,
        company_id: int = 1,
    ) -> list[dict[str, Any]]:
        stmt = select(AuditEntry).where(AuditEntry.company_id == company_id)
        if entity_type:
            stmt = stmt.where(AuditEntry.entity_type == entity_type)
        stmt = stmt.order_by(AuditEntry.created_at.desc()).limit(limit)
        rows = list(db.scalars(stmt).all())
        return [
            {
                "id": r.id,
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "action": r.action,
                "actor_label": r.actor_label,
                "hash": r.immutable_hash[:16],
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    def build_compliance_center(
        self,
        db: Session,
        *,
        company_id: int = 1,
        limit: int = 100,
    ) -> dict[str, Any]:
        audit = self.list_audit(db, limit=limit, company_id=company_id)
        events = list(
            db.scalars(
                select(ComplianceEvent)
                .where(ComplianceEvent.company_id == company_id)
                .order_by(ComplianceEvent.created_at.desc())
                .limit(limit)
            ).all()
        )
        timeline = []
        for a in audit[:40]:
            timeline.append(
                {
                    "kind": "audit",
                    "title": a["action"],
                    "entity": f"{a['entity_type']} #{a['entity_id'] or ''}",
                    "actor": a["actor_label"],
                    "at": a["created_at"],
                    "tone": "info",
                }
            )
        for e in events[:20]:
            timeline.append(
                {
                    "kind": "compliance",
                    "title": e.event_type,
                    "entity": e.message[:80],
                    "actor": "system",
                    "at": e.created_at.isoformat() if e.created_at else None,
                    "tone": e.severity,
                }
            )
        timeline.sort(key=lambda x: x.get("at") or "", reverse=True)
        sig_count = db.scalar(select(func.count(DigitalSignature.id))) or 0
        return {
            "audit_count": len(audit),
            "compliance_events": len(events),
            "signatures_count": sig_count,
            "timeline": timeline[:50],
            "audit_sample": audit[:25],
        }

    def export_audit_csv_rows(self, db: Session, *, limit: int = 500) -> list[list[str]]:
        rows = self.list_audit(db, limit=limit)
        out = [["id", "entity_type", "entity_id", "action", "actor", "created_at"]]
        for r in rows:
            out.append(
                [
                    str(r["id"]),
                    r["entity_type"],
                    str(r["entity_id"] or ""),
                    r["action"],
                    r["actor_label"] or "",
                    r["created_at"] or "",
                ]
            )
        return out
