"""Where an enumerated playlist waits while somebody reads it.

Split from :mod:`bot.core.playlist_menu` for the reason every store here is:
importing ``yt_shared.db.session`` builds the engine and drags in asyncpg, and
the paging and serialisation rules are worth testing without a database driver
on the path. Everything that decides anything lives over there; this only reads
and writes.

The TTL is shorter than the pending downloads' two days. A menu is read within
minutes of being opened or not at all, and the contents go stale — a playlist
gains and loses items — so an old answer is worse than none.
"""

import datetime
import logging
from typing import Final, Protocol

from yt_shared.db.session import get_db
from yt_shared.repositories.playlist import PlaylistRepository

from bot.core.playlist_menu import (
    MenuEntry,
    StoredPlaylist,
    entries_to_rows,
    rows_to_entries,
)

TTL: Final[datetime.timedelta] = datetime.timedelta(hours=6)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


def cutoff() -> datetime.datetime:
    return _now() - TTL


class PlaylistStore(Protocol):
    async def save(
        self, url_id: str, title: str, entries: list[MenuEntry], total: int
    ) -> None: ...

    async def load(self, url_id: str) -> StoredPlaylist | None: ...

    async def delete(self, url_id: str) -> None: ...

    async def delete_older_than(self, when: datetime.datetime) -> int: ...


class PostgresPlaylistStore:
    def __init__(self) -> None:
        self._log = logging.getLogger(self.__class__.__name__)

    async def save(
        self, url_id: str, title: str, entries: list[MenuEntry], total: int
    ) -> None:
        values = {
            'url_id': url_id,
            'title': title,
            'entries': entries_to_rows(entries),
            'total': total,
            'added_at': _now(),
        }
        async for db in get_db():
            await PlaylistRepository(db).save(values)

    async def load(self, url_id: str) -> StoredPlaylist | None:
        async for db in get_db():
            row = await PlaylistRepository(db).get(url_id)
            if row is None:
                return None
            if row.added_at < cutoff():
                # Dropped on the way past rather than served: a playlist gains
                # and loses items while nobody is looking at it.
                await PlaylistRepository(db).delete(url_id)
                return None
            return StoredPlaylist(
                title=row.title,
                entries=rows_to_entries(row.entries),
                total=row.total,
            )
        return None

    async def delete(self, url_id: str) -> None:
        async for db in get_db():
            await PlaylistRepository(db).delete(url_id)

    async def delete_older_than(self, when: datetime.datetime) -> int:
        async for db in get_db():
            return await PlaylistRepository(db).delete_older_than(when)
        return 0
