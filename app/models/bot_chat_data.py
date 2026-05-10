from sqlalchemy import BigInteger
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BotChatData(Base):
    __tablename__ = "bot_chat_data"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
