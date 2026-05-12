from sqlalchemy.orm import Session

from app.models.user import User, UserRole


class UserRepository:
    @staticmethod
    def get_by_id(db: Session, user_id: int) -> User | None:
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def get_by_username(db: Session, username: str) -> User | None:
        return db.query(User).filter(User.username == username).first()

    @staticmethod
    def get_by_telegram_id(db: Session, telegram_id: int) -> User | None:
        return db.query(User).filter(User.telegram_id == telegram_id).first()

    @staticmethod
    def get_active_by_telegram_id(db: Session, telegram_id: int) -> User | None:
        return (
            db.query(User)
            .filter(
                User.telegram_id == telegram_id,
                User.is_active.is_(True),
            )
            .first()
        )

    @staticmethod
    def list_active_admins_with_telegram_id(db: Session) -> list[User]:
        admin_roles = [UserRole.ADMIN.value, UserRole.SISTEMAS.value]
        return (
            db.query(User)
            .filter(
                User.telegram_id.isnot(None),
                User.is_active.is_(True),
                User.role.in_(admin_roles),
            )
            .all()
        )

    @staticmethod
    def get_active_dev_telegram_fallback(db: Session) -> User | None:
        """Primer usuario activo para demos sin telegram_id: prioriza admin/sistemas, luego cualquier rol."""
        u = (
            db.query(User)
            .filter(
                User.is_active.is_(True),
                User.role.in_((UserRole.ADMIN, UserRole.SISTEMAS)),
            )
            .order_by(User.id.asc())
            .first()
        )
        if u:
            return u
        return db.query(User).filter(User.is_active.is_(True)).order_by(User.id.asc()).first()

    @staticmethod
    def create(db: Session, user: User) -> User:
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
