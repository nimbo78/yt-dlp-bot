import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from yt_shared.models import StartupMessage


class StartupMessageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._log = logging.getLogger(self.__class__.__name__)
        self._db = db

    async def take_all(self) -> list[tuple[int, int]]:
        """Return every recorded message and forget them in the same breath.

        Taking rather than reading: once a start has been handed the previous
        batch it owns them, and a message it fails to delete — Telegram refuses
        anything older than 48 hours — must not be retried on every start
        forever.
        """
        result = await self._db.execute(
            select(StartupMessage.chat_id, StartupMessage.message_id)
        )
        recorded = [(row.chat_id, row.message_id) for row in result]
        if recorded:
            await self._db.execute(delete(StartupMessage))
            await self._db.commit()
        return recorded

    async def save_all(self, messages: list[tuple[int, int]]) -> None:
        if not messages:
            return
        self._db.add_all([
            StartupMessage(chat_id=chat_id, message_id=message_id)
            for chat_id, message_id in messages
        ])
        await self._db.commit()
