"""P52 — firma digital y aprobaciones."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enterprise_advanced import DigitalSignature, SignedDocument


class SignatureService:
    @staticmethod
    def _hash_payload(payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()

    def sign_entity(
        self,
        db: Session,
        *,
        entity_type: str,
        entity_id: int,
        signer_user_id: int | None,
        signer_label: str,
        signer_role: str | None,
        payload: dict[str, Any],
        document_path: str | None = None,
    ) -> DigitalSignature:
        payload_hash = self._hash_payload(payload)
        sig_material = f"{signer_label}:{payload_hash}:{entity_type}:{entity_id}"
        signature_hash = hashlib.sha256(sig_material.encode()).hexdigest()

        sig = DigitalSignature(
            entity_type=entity_type,
            entity_id=entity_id,
            signer_user_id=signer_user_id,
            signer_label=signer_label,
            signer_role=signer_role,
            signature_hash=signature_hash,
            payload_hash=payload_hash,
            metadata_json=payload,
        )
        db.add(sig)
        db.flush()

        if document_path:
            doc_hash = hashlib.sha256(document_path.encode()).hexdigest()
            db.add(
                SignedDocument(
                    signature_id=sig.id,
                    document_path=document_path,
                    document_hash=doc_hash,
                )
            )
            db.flush()
        try:
            from app.services.platform_cohesion_service import safe_cohesion_emit

            safe_cohesion_emit(
                db,
                action="signature_created",
                title=f"Firma: {signer_label}",
                entity_type=entity_type,
                entity_id=entity_id,
                actor_user_id=signer_user_id,
                actor_label=signer_label,
                source="signatures",
            )
        except Exception:
            pass
        return sig

    def list_for_entity(self, db: Session, entity_type: str, entity_id: int) -> list[dict[str, Any]]:
        rows = list(
            db.scalars(
                select(DigitalSignature)
                .where(
                    DigitalSignature.entity_type == entity_type,
                    DigitalSignature.entity_id == entity_id,
                )
                .order_by(DigitalSignature.signed_at.desc())
            ).all()
        )
        return [
            {
                "id": s.id,
                "signer_label": s.signer_label,
                "signer_role": s.signer_role,
                "status": s.status,
                "signed_at": s.signed_at.isoformat() if s.signed_at else None,
                "signature_hash": s.signature_hash[:16] + "…",
            }
            for s in rows
        ]
