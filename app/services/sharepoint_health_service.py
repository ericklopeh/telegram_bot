"""Health check Microsoft Graph / SharePoint (P25.1)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.domain import constants as C
from app.models.case_event import CaseEvent
from app.models.document import Document
from app.services.sharepoint_graph_client import SharePointGraphClient
from app.services.sharepoint_graph_errors import GraphApiError, GraphConfigError

log = logging.getLogger(__name__)


@dataclass
class GraphHealthReport:
    ok: bool
    checked_at: datetime
    config_ok: bool
    token_ok: bool
    last_token_at: datetime | None
    site_id: str | None
    drive_id: str | None
    root_folder: str
    root_folder_readable: bool
    write_probe_ok: bool
    drive_name: str
    site_hostname: str
    site_path: str
    permissions_hint: str
    errors: list[str] = field(default_factory=list)
    recent_graph_errors: list[dict] = field(default_factory=list)
    recent_failed_uploads: list[dict] = field(default_factory=list)


class SharePointHealthService:
    def __init__(self, graph: SharePointGraphClient | None = None) -> None:
        self.graph = graph or SharePointGraphClient()
        self.settings = get_settings()

    def run_check(self, db: Session | None = None) -> GraphHealthReport:
        now = datetime.now(timezone.utc)
        errors: list[str] = []
        config_ok = False
        token_ok = False
        site_id = None
        drive_id = None
        root_readable = False
        write_ok = False
        last_token = self.graph.last_token_ok_at

        try:
            self.graph.validate_config()
            config_ok = True
        except GraphConfigError as exc:
            return GraphHealthReport(
                ok=False,
                checked_at=now,
                config_ok=False,
                token_ok=False,
                last_token_at=last_token,
                site_id=None,
                drive_id=None,
                root_folder=self.settings.ms_root_folder or "",
                root_folder_readable=False,
                write_probe_ok=False,
                drive_name=self.settings.ms_drive_name or "",
                site_hostname=self.settings.ms_site_hostname or "",
                site_path=self.settings.ms_site_path or "",
                permissions_hint=_permissions_hint(),
                errors=[str(exc)],
                recent_graph_errors=_recent_events(db) if db else [],
                recent_failed_uploads=_recent_failed_docs(db) if db else [],
            )

        try:
            token = self.graph.get_access_token()
            token_ok = bool(token)
            last_token = self.graph.last_token_ok_at
        except (GraphApiError, GraphConfigError) as exc:
            errors.append(str(exc))

        if token_ok:
            try:
                site_id = self.graph.get_site_id()
                drive_id = self.graph.get_drive_id()
                if drive_id:
                    root_readable = self.graph.probe_root_folder_readable(drive_id)
                    if not root_readable:
                        errors.append(
                            "MS_ROOT_FOLDER: no se pudo leer la carpeta raíz en el drive."
                        )
                    root_parts = [
                        p.strip()
                        for p in (self.settings.ms_root_folder or "").split("/")
                        if p.strip()
                    ]
                    root_path = "/".join(root_parts)
                    if root_path and drive_id:
                        write_ok = self.graph.probe_write_permission(drive_id, root_path)
                        if not write_ok:
                            errors.append(
                                "Sin permiso de escritura de prueba en MS_ROOT_FOLDER."
                            )
            except GraphApiError as exc:
                errors.append(exc.user_message)

        ok = (
            config_ok
            and token_ok
            and bool(site_id)
            and bool(drive_id)
            and root_readable
            and write_ok
            and not errors
        )

        return GraphHealthReport(
            ok=ok,
            checked_at=now,
            config_ok=True,
            token_ok=token_ok,
            last_token_at=last_token,
            site_id=site_id,
            drive_id=drive_id,
            root_folder=self.settings.ms_root_folder or "",
            root_folder_readable=root_readable,
            write_probe_ok=write_ok,
            drive_name=self.settings.ms_drive_name or self.settings.ms_drive_id or "",
            site_hostname=self.settings.ms_site_hostname or "",
            site_path=self.settings.ms_site_path or "",
            permissions_hint=_permissions_hint(),
            errors=errors,
            recent_graph_errors=_recent_events(db) if db else [],
            recent_failed_uploads=_recent_failed_docs(db) if db else [],
        )


def _permissions_hint() -> str:
    return (
        "Application permissions: Sites.ReadWrite.All y/o Files.ReadWrite.All "
        "(admin consent en Entra ID)."
    )


def _recent_events(db: Session, limit: int = 15) -> list[dict]:
    from app.services.case_event_service import (
        SHAREPOINT_UPLOAD_FAILED,
        DOCUMENT_UPLOAD_FAILED,
    )

    types = (SHAREPOINT_UPLOAD_FAILED, DOCUMENT_UPLOAD_FAILED)
    rows = list(
        db.scalars(
            select(CaseEvent)
            .where(CaseEvent.event_type.in_(types))
            .order_by(CaseEvent.created_at.desc())
            .limit(limit)
        ).all()
    )
    out = []
    for e in rows:
        out.append(
            {
                "case_id": e.case_id,
                "event_type": e.event_type,
                "message": (e.message or "")[:200],
                "created_at": e.created_at.isoformat() if e.created_at else "",
            }
        )
    return out


def _recent_failed_docs(db: Session, limit: int = 20) -> list[dict]:
    rows = list(
        db.scalars(
            select(Document)
            .where(
                Document.is_active.is_(True),
                Document.upload_status == C.UPLOAD_FAILED,
            )
            .order_by(Document.updated_at.desc())
            .limit(limit)
        ).all()
    )
    return [
        {
            "document_id": d.id,
            "case_id": d.case_id,
            "filename": d.stored_filename,
            "error": (d.upload_error or "")[:200],
            "attempts": d.upload_attempts,
        }
        for d in rows
    ]
