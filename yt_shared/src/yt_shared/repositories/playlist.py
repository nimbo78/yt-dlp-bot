import datetime
import logging

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from yt_shared.models import Playlist


class PlaylistRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._log = logging.getLogger(self.__class__.__name__)
        self._db = db

    async def save(self, values: dict) -> None:
        """Store an enumeration, replacing any earlier one for the same key.

        Asking twice for the same message is a refresh, not a collision — the
        second answer is the newer one and wins.
        """
        stmt = (
            insert(Playlist)
            .values(**values)
            .on_conflict_do_update(index_elements=['url_id'], set_=values)
        )
        await self._db.execute(stmt)
        await self._db.commit()

    async def get(self, url_id: str) -> Playlist | None:
        result = await self._db.execute(
            select(Playlist).where(Playlist.url_id == url_id)
        )
        return result.scalar_one_or_none()

    async def delete(self, url_id: str) -> None:
        await self._db.execute(delete(Playlist).where(Playlist.url_id == url_id))
        await self._db.commit()

    async def delete_older_than(self, cutoff: datetime.datetime) -> int:
        result = await self._db.execute(
            delete(Playlist).where(Playlist.added_at < cutoff)
        )
        await self._db.commit()
        return result.rowcount or 0
