import asyncio
import copy
import logging
from collections import defaultdict
from typing import Any, DefaultDict, Dict, Optional, Tuple

from telegram.ext import BasePersistence, PersistenceInput

from app.db.session import session_scope
from app.models.bot_chat_data import BotChatData

log = logging.getLogger(__name__)


class PostgresPersistence(BasePersistence):
    """
    Persistencia para python-telegram-bot respaldada por PostgreSQL.
    Solo persiste chat_data (ideal para flujos conversacionales no basados en ConversationHandler).
    """
    def __init__(self) -> None:
        super().__init__(
            store_data=PersistenceInput(
                bot_data=False,
                chat_data=True,
                user_data=False,
                callback_data=False,
            )
        )
        self.chat_data: Optional[DefaultDict[int, Dict[Any, Any]]] = None

    async def get_chat_data(self) -> DefaultDict[int, Dict[Any, Any]]:
        if self.chat_data is None:
            def load_from_db() -> dict[int, dict]:
                with session_scope() as db:
                    rows = db.query(BotChatData).all()
                    return {row.chat_id: copy.deepcopy(row.data) for row in rows}

            try:
                db_data = await asyncio.to_thread(load_from_db)
                self.chat_data = defaultdict(dict, db_data)
                log.info("Cargados %d registros de chat_data desde Postgres.", len(db_data))
            except Exception as e:
                log.exception("Error cargando chat_data desde Postgres: %s", str(e))
                self.chat_data = defaultdict(dict)
        return copy.deepcopy(self.chat_data)

    async def update_chat_data(self, chat_id: int, data: Dict[Any, Any]) -> None:
        if self.chat_data is None:
            self.chat_data = defaultdict(dict)
        
        if not isinstance(data, dict):
            return

        # Si el diccionario está vacío, lo eliminamos de BD
        if not data:
            await self.drop_chat_data(chat_id)
            return

        self.chat_data[chat_id] = data

        def save_to_db() -> None:
            with session_scope() as db:
                record = db.query(BotChatData).filter(BotChatData.chat_id == chat_id).first()
                if not record:
                    record = BotChatData(chat_id=chat_id, data=data)
                    db.add(record)
                else:
                    record.data = data

        try:
            await asyncio.to_thread(save_to_db)
            log.debug("chat_data guardado para chat_id=%s", chat_id)
        except Exception as e:
            log.exception("Error guardando chat_data para chat_id=%s: %s", chat_id, str(e))

    async def drop_chat_data(self, chat_id: int) -> None:
        if self.chat_data and chat_id in self.chat_data:
            del self.chat_data[chat_id]

        def delete_from_db() -> None:
            with session_scope() as db:
                record = db.query(BotChatData).filter(BotChatData.chat_id == chat_id).first()
                if record:
                    db.delete(record)

        try:
            await asyncio.to_thread(delete_from_db)
            log.debug("chat_data eliminado para chat_id=%s", chat_id)
        except Exception as e:
            log.exception("Error eliminando chat_data para chat_id=%s: %s", chat_id, str(e))

    async def refresh_chat_data(self, chat_id: int, chat_data: Dict[Any, Any]) -> None:
        pass

    # Métodos obligatorios para BasePersistence
    async def get_bot_data(self) -> Dict[Any, Any]:
        return {}
    async def update_bot_data(self, data: Dict[Any, Any]) -> None:
        pass
    async def refresh_bot_data(self, bot_data: Dict[Any, Any]) -> None:
        pass
    
    async def get_user_data(self) -> DefaultDict[int, Dict[Any, Any]]:
        return defaultdict(dict)
    async def update_user_data(self, user_id: int, data: Dict[Any, Any]) -> None:
        pass
    async def refresh_user_data(self, user_id: int, user_data: Dict[Any, Any]) -> None:
        pass
    async def drop_user_data(self, user_id: int) -> None:
        pass
    
    async def get_callback_data(self) -> Optional[Tuple[Any, ...]]:
        return None
    async def update_callback_data(self, data: Tuple[Any, ...]) -> None:
        pass
    
    async def get_conversations(self, name: str) -> dict:
        return {}
    async def update_conversation(self, name: str, key: Tuple[int, ...], new_state: Optional[object]) -> None:
        pass
    async def drop_conversation(self, name: str, key: Tuple[int, ...]) -> None:
        pass
    
    async def flush(self) -> None:
        pass
