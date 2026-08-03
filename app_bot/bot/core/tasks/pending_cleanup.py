"""Periodic eviction of what nobody came back to.

Evicting on access is not enough on its own: an entry nobody looks up again is
never reached that way, and those are precisely the ones that accumulate. That
holds for pending format choices and for enumerated playlists alike, so both are
swept here.
"""

import asyncio
from typing import TYPE_CHECKING

from yt_shared.utils.tasks.abstract import AbstractTask

if TYPE_CHECKING:
    from bot.bot.client import VideoBotClient


class PendingCleanupTask(AbstractTask):
    _SLEEP_TIME: int = 60 * 60

    def __init__(self, bot: 'VideoBotClient') -> None:
        super().__init__()
        self._bot = bot

    async def run(self) -> None:
        await self._run()

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._SLEEP_TIME)
            try:
                evicted = await self._bot.pending_downloads.sweep()
            except Exception:
                self._log.exception('Could not sweep the pending downloads')
                continue
            if evicted:
                # Only when something happened: an hourly "nothing to do" line
                # is how a log stops being read.
                self._log.info(
                    'Dropped %d expired pending download(s), %d left',
                    evicted,
                    await self._bot.pending_downloads.size(),
                )

            try:
                stale = await self._bot.playlists.sweep()
            except Exception:
                self._log.exception('Could not sweep the stored playlists')
                continue
            if stale:
                self._log.info('Dropped %d stale playlist menu(s)', stale)
