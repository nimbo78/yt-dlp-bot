import datetime
import logging

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from yt_shared.models import PendingDownload


class PendingDownloadRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._log = logging.getLogger(self.__class__.__name__)
        self._db = db

    async def save(self, values: dict) -> None:
        """Store a pending choice, replacing any earlier one for the same key.

        The key is derived from the chat and message, so a second keyboard for
        the same message supersedes the first rather than colliding with it.
        """
        stmt = (
            insert(PendingDownload)
            .values(**values)
            .on_conflict_do_update(index_elements=['url_id'], set_=values)
        )
        await self._db.execute(stmt)
        await self._db.commit()

    async def get(self, url_id: str) -> PendingDownload | None:
        result = await self._db.execute(
            select(PendingDownload).where(PendingDownload.url_id == url_id)
        )
        return result.scalar_one_or_none()

    async def delete(self, url_id: str) -> None:
        await self._db.execute(
            delete(PendingDownload).where(PendingDownload.url_id == url_id)
        )
        await self._db.commit()

    async def delete_older_than(self, cutoff: datetime.datetime) -> int:
        result = await self._db.execute(
            delete(PendingDownload).where(PendingDownload.added_at < cutoff)
        )
        await self._db.commit()
        return result.rowcount or 0

    async def count(self) -> int:
        result = await self._db.execute(select(PendingDownload.id))
        return len(result.all())
