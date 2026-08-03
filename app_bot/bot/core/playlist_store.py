"""Where an enumerated playlist waits while somebody reads it.

Split from :mod:`bot.core.playlists` for the reason every store here is split:
importing ``yt_shared.db.session`` builds the engine and drags in asyncpg, and
the expiry rules are worth testing without a database driver on the path. So
this reads and writes and judges nothing — including whether a row is too old,
which travels back as ``added_at`` for the policy layer to decide.
"""

import datetime
from typing import Protocol

from yt_shared.db.session import get_db
from yt_shared.repositories.playlist import PlaylistRepository

from bot.core.playlist_menu import (
    MenuEntry,
    StoredPlaylist,
    entries_to_rows,
    rows_to_entries,
)


class PlaylistStore(Protocol):
    async def save(self, url_id: str, entries: list[MenuEntry]) -> None: ...

    async def load(self, url_id: str) -> StoredPlaylist | None: ...

    async def delete(self, url_id: str) -> None: ...

    async def delete_older_than(self, cutoff: datetime.datetime) -> int: ...


class PostgresPlaylistStore:
    async def save(self, url_id: str, entries: list[MenuEntry]) -> None:
        values = {
            'url_id': url_id,
            'entries': entries_to_rows(entries),
            'added_at': datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
        }
        async for db in get_db():
            await PlaylistRepository(db).save(values)

    async def load(self, url_id: str) -> StoredPlaylist | None:
        async for db in get_db():
            row = await PlaylistRepository(db).get(url_id)
            if row is None:
                return None
            return StoredPlaylist(
                entries=rows_to_entries(row.entries), added_at=row.added_at
            )
        return None

    async def delete(self, url_id: str) -> None:
        async for db in get_db():
            await PlaylistRepository(db).delete(url_id)

    async def delete_older_than(self, cutoff: datetime.datetime) -> int:
        async for db in get_db():
            return await PlaylistRepository(db).delete_older_than(cutoff)
        return 0
