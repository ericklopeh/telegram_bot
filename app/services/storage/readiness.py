"""P75 — checklist de preparación para storage real (sin credenciales)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StorageReadinessItem:
    key: str
    label: str
    done: bool = False
    notes: str = ""


@dataclass
class StorageReadinessChecklist:
    """Estado documentado para integración OneDrive/SharePoint o S3."""

    provider: str = "local"
    items: list[StorageReadinessItem] = field(default_factory=list)

    @classmethod
    def default_local(cls) -> StorageReadinessChecklist:
        return cls(
            provider="local",
            items=[
                StorageReadinessItem("folder_layout", "Estructura semana/vendedor/cliente/folio", True),
                StorageReadinessItem("local_backend", "LocalStorageBackend operativo", True),
                StorageReadinessItem("sharepoint_env", "Variables MS_* en .env (sin commitear)", False),
                StorageReadinessItem("s3_env", "Bucket S3-compatible (futuro)", False),
                StorageReadinessItem("retry_jobs", "Jobs retry SharePoint en bot", False),
            ],
        )

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "items": [
                {"key": i.key, "label": i.label, "done": i.done, "notes": i.notes}
                for i in self.items
            ],
        }
