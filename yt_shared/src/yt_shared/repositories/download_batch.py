import datetime
import logging

from sqlalchemy import delete, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from yt_shared.models import DownloadBatch


class DownloadBatchRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._log = logging.getLogger(self.__class__.__name__)
        self._db = db

    async def start(self, values: dict) -> None:
        """Record a batch, replacing any earlier one from the same message."""
        stmt = (
            insert(DownloadBatch)
            .values(**values)
            .on_conflict_do_update(
                index_elements=['chat_id', 'message_id'], set_=values
            )
        )
        await self._db.execute(stmt)
        await self._db.commit()

    async def finish_one(self, chat_id: int, message_id: int) -> tuple[int, int] | None:
        """Count one task off, and say what is left and which message to tidy.

        The decrement and the read are one statement on purpose: two workers
        finishing at the same instant would otherwise both read the same number
        and neither would see zero, so the source message would survive and the
        summary would sit there for good.

        Returns ``(remaining, summary_message_id)``, or ``None`` when this
        download belongs to no batch — which is every ordinary single one.
        """
        result = await self._db.execute(
            update(DownloadBatch)
            .where(
                DownloadBatch.chat_id == chat_id,
                DownloadBatch.message_id == message_id,
            )
            .values(remaining=DownloadBatch.remaining - 1)
            .returning(DownloadBatch.remaining, DownloadBatch.summary_message_id)
        )
        row = result.first()
        await self._db.commit()
        if row is None:
            return None
        return int(row[0]), row[1]

    async def delete(self, chat_id: int, message_id: int) -> None:
        await self._db.execute(
            delete(DownloadBatch).where(
                DownloadBatch.chat_id == chat_id,
                DownloadBatch.message_id == message_id,
            )
        )
        await self._db.commit()

    async def delete_older_than(self, cutoff: datetime.datetime) -> int:
        result = await self._db.execute(
            delete(DownloadBatch).where(DownloadBatch.added_at < cutoff)
        )
        await self._db.commit()
        return result.rowcount or 0
