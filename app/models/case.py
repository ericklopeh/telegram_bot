from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    case_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    order_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    client_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    temp_folio: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    official_folio: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    current_status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    visible_status: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    seller_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    seller_telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    week_code: Mapped[str] = mapped_column(String(32), nullable=False)
    folder_path: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    history_entries = relationship(
        "CaseHistory", back_populates="case", cascade="all, delete-orphan"
    )
    documents = relationship(
        "Document",
        back_populates="case",
        foreign_keys="Document.case_id",
        cascade="all, delete-orphan",
    )
    authorization_jobs = relationship(
        "AuthorizationJob", back_populates="case", cascade="all, delete-orphan"
    )
    talon_reviews = relationship(
        "TalonReview", back_populates="case", cascade="all, delete-orphan"
    )
