"""Periodic eviction of pending format choices nobody came back to.

Evicting on access is not enough on its own: an entry nobody looks up again is
never reached that way, and those are precisely the ones that accumulate.
"""

import asyncio

from yt_shared.utils.tasks.abstract import AbstractTask

from bot.core.pending_downloads import PendingDownloadsStore


class PendingCleanupTask(AbstractTask):
    _SLEEP_TIME: int = 60 * 60

    async def run(self) -> None:
        await self._run()

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._SLEEP_TIME)
            evicted = PendingDownloadsStore.sweep()
            if evicted:
                # Only when something happened: an hourly "nothing to do" line
                # is how a log stops being read.
                self._log.info(
                    'Dropped %d expired pending download(s), %d left',
                    evicted,
                    PendingDownloadsStore.size(),
                )
