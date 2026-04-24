from sqlalchemy.orm import Session

from app.models.case_history import CaseHistory


class HistoryRepository:
    @staticmethod
    def append(
        db: Session,
        case_id: int,
        old_status: str | None,
        new_status: str,
        action_source: str = "telegram",
        action_user: str | None = None,
        notes: str | None = None,
    ) -> CaseHistory:
        row = CaseHistory(
            case_id=case_id,
            old_status=old_status,
            new_status=new_status,
            action_source=action_source,
            action_user=action_user,
            notes=notes,
        )
        db.add(row)
        db.flush()
        return row
