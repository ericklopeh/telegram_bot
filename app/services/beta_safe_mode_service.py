"""Modo operación beta segura y confirmaciones textuales (P34)."""

from __future__ import annotations

from fastapi import Request

from app.config import get_settings
from app.services.beta_ops_log import log_mass_action_confirmed, log_safe_mode_blocked


class BetaSafeModeService:
    """Cuando BETA_SAFE_MODE=true exige frases de confirmación en acciones sensibles."""

    def is_enabled(self) -> bool:
        return bool(get_settings().beta_safe_mode)

    @staticmethod
    def phrase_rollback_import(batch_id: int) -> str:
        return f"REVERTIR-LOTE-{batch_id}"

    @staticmethod
    def phrase_regenerate_export(sale_capture_id: int) -> str:
        return f"REGENERAR-{sale_capture_id}"

    @staticmethod
    def phrase_mass_commissions() -> str:
        return "RECALCULAR-COMISIONES"

    @staticmethod
    def phrase_mass_sharepoint() -> str:
        return "REINTENTAR-SHAREPOINT"

    @staticmethod
    def phrase_resolve_incident(incident_id: int) -> str:
        return f"RESOLVER-{incident_id}"

    @staticmethod
    def phrase_replace_document(document_id: int) -> str:
        return f"REEMPLAZAR-DOC-{document_id}"

    def require_confirmation(
        self,
        action: str,
        required_phrase: str,
        confirm_text: str | None,
        *,
        entity_type: str | None = None,
        entity_id: int | str | None = None,
        username: str | None = None,
        force: bool = False,
    ) -> tuple[bool, str | None]:
        """
        Si modo seguro activo (o force), exige coincidencia exacta de confirm_text.
        Retorna (ok, mensaje_error).
        """
        if not self.is_enabled() and not force:
            return True, None

        provided = (confirm_text or "").strip()
        if provided != required_phrase:
            log_safe_mode_blocked(
                action,
                entity_type=entity_type,
                entity_id=entity_id,
                reason=f"frase esperada '{required_phrase}'",
            )
            return (
                False,
                f"Modo beta seguro: escriba exactamente «{required_phrase}» para confirmar.",
            )

        log_mass_action_confirmed(
            action,
            entity_type=entity_type,
            entity_id=entity_id,
            username=username,
        )
        return True, None

    def block_mass_rollback_without_phrase(
        self,
        batch_id: int,
        confirm_text: str | None,
        *,
        username: str | None = None,
    ) -> tuple[bool, str | None]:
        return self.require_confirmation(
            "rollback_import",
            self.phrase_rollback_import(batch_id),
            confirm_text,
            entity_type="import_batch",
            entity_id=batch_id,
            username=username,
            force=self.is_enabled(),
        )


def beta_ui_context_for_request(request: Request, db) -> dict:
    """Alertas ligeras para navbar (admin/sistemas)."""
    from app.services.beta_readiness_service import BetaReadinessService

    usuario = request.session.get("usuario") or {}
    if usuario.get("rol") not in ("admin", "sistemas"):
        return {"beta_ui": None}

    try:
        alerts = BetaReadinessService().quick_banner_alerts(db)
    except Exception:
        alerts = {"safe_mode": BetaSafeModeService().is_enabled(), "error": True}

    alerts["safe_mode"] = BetaSafeModeService().is_enabled()
    return {"beta_ui": alerts}
