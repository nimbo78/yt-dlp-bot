"""Reads and writes enumerated playlist menus, dropping the ones gone stale.

The same shape as :mod:`bot.core.pending_downloads`: the policy lives here, the
store only reads and writes, and a store that cannot be read reads as "no menu"
rather than as a traceback in front of whoever pressed the button.

The TTL is six hours, against the pending downloads' two days. A menu is read
within minutes of being opened or not at all, and its contents go stale — a
playlist gains and loses items — so an old answer is worse than none.
"""

import datetime
import logging
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from bot.core.playlist_menu import MenuEntry, StoredPlaylist
    from bot.core.playlist_store import PlaylistStore

TTL: Final[datetime.timedelta] = datetime.timedelta(hours=6)


class Playlists:
    def __init__(self, store: 'PlaylistStore') -> None:
        self._log = logging.getLogger(self.__class__.__name__)
        self._store = store

    @staticmethod
    def _cutoff() -> datetime.datetime:
        return datetime.datetime.now(datetime.UTC).replace(tzinfo=None) - TTL

    async def save(self, url_id: str, entries: list['MenuEntry']) -> None:
        await self._store.save(url_id, entries)

    async def set_selected(self, url_id: str, selected: frozenset[int]) -> None:
        await self._store.set_selected(url_id, selected)

    async def load(self, url_id: str) -> 'StoredPlaylist | None':
        """Fetch a menu whole — entries and ticks — or ``None`` if it is stale."""
        try:
            found = await self._store.load(url_id)
        except Exception:
            # A menu that cannot be read is a menu that has expired, as far as
            # the person pressing the button is concerned. Far better than an
            # unanswered callback, which spins until the client gives up.
            self._log.exception('Could not read the playlist %s', url_id)
            return None

        if found is None:
            return None
        if found.added_at < self._cutoff():
            # Evicting on access alone never reaches a menu nobody returns to,
            # which is why the sweep exists as well.
            self._log.debug('Playlist %s has gone stale', url_id)
            await self._forget(url_id)
            return None
        return found

    async def get(self, url_id: str) -> list['MenuEntry'] | None:
        """Fetch just the entries, for callers with no interest in the ticks."""
        found = await self.load(url_id)
        return None if found is None else found.entries

    async def remove(self, url_id: str) -> None:
        """Drop a menu that has served its purpose, or been abandoned."""
        await self._forget(url_id)

    async def _forget(self, url_id: str) -> None:
        try:
            await self._store.delete(url_id)
        except Exception:
            # Worth a line, not worth failing the thing that asked: the sweep
            # will get it, and at worst a stale row waits six hours.
            self._log.exception('Could not drop the playlist %s', url_id)

    async def sweep(self) -> int:
        """Drop every menu past its time, and say how many that was."""
        return await self._store.delete_older_than(self._cutoff())
