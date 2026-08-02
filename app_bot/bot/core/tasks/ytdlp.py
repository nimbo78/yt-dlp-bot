import asyncio
import datetime
from typing import TYPE_CHECKING

from yt_shared.clients.github import YtdlpGithubClient
from yt_shared.db.session import get_db
from yt_shared.repositories.ytdlp import YtdlpRepository
from yt_shared.schemas.ytdlp import VersionContext
from yt_shared.utils.tasks.abstract import AbstractTask
from yt_shared.ytdlp.version_checker import YtdlpVersionChecker

from bot.core.config.config import get_main_config

if TYPE_CHECKING:
    from bot.bot.client import VideoBotClient


class YtdlpNewVersionNotifyTask(AbstractTask):
    def __init__(self, bot: 'VideoBotClient') -> None:
        super().__init__()
        self._bot = bot
        self._first_check_done = False
        self._ytdlp_conf = get_main_config().ytdlp

    async def run(self) -> None:
        await self._run()

    async def _run(self) -> None:
        release_channel = self._ytdlp_conf.release_channel
        if not self._ytdlp_conf.version_check_enabled:
            self._log.info(
                'New %s "yt-dlp" version check disabled, exiting from task',
                release_channel,
            )
            return

        while True:
            self._log.info('Checking for new %s yt-dlp version', release_channel)
            try:
                await self._notify_if_new_version()
            except Exception:
                self._log.exception(
                    'Failed check new %s yt-dlp version', release_channel
                )
            self._log.info(
                'Next %s yt-dlp version check planned at %s',
                release_channel,
                self._get_next_check_datetime().isoformat(' '),
            )
            await asyncio.sleep(self._ytdlp_conf.version_check_interval)

    def _get_next_check_datetime(self) -> datetime.datetime:
        return (
            datetime.datetime.now(datetime.UTC)
            + datetime.timedelta(seconds=self._ytdlp_conf.version_check_interval)
        ).replace(microsecond=0)

    async def _notify_if_new_version(self) -> None:
        async for db in get_db():
            context = await YtdlpVersionChecker(
                client=YtdlpGithubClient(self._ytdlp_conf.release_channel),
                repository=YtdlpRepository(db),
            ).get_version_context()
            if context.has_new_version:
                self._log.info('yt-dlp has new version: %s', context.latest.version)

            if not self._first_check_done:
                # The first result belongs on the startup message, whichever way
                # it went: it is the same sentence, and one message beats two.
                self._first_check_done = True
                await self._extend_startup_notice(context)
                return

            if context.has_new_version and self._ytdlp_conf.notify_users_on_new_version:
                await self._notify_outdated(context)

    async def _extend_startup_notice(self, ctx: VersionContext) -> None:
        """Append the version line to the message posted at startup.

        Says what is true regardless of ``notify_users_on_new_version``: that
        setting governs the recurring notice below, not whether an admin reading
        their own startup message is told the truth about the version.
        """
        if ctx.has_new_version:
            await self._bot.startup_notice.append(
                'ytdlp.new_version',
                channel=self._ytdlp_conf.release_channel,
                latest=ctx.latest.version,
                current=ctx.current.version,
            )
            return
        await self._bot.startup_notice.append(
            'ytdlp.up_to_date',
            channel=self._ytdlp_conf.release_channel,
            current=ctx.current.version,
        )

    async def _notify_outdated(self, ctx: VersionContext) -> None:
        """Post a standalone notice, which stays: it asks the reader to rebuild."""
        await self._bot.send_translated_to_admins(
            key='ytdlp.new_version',
            channel=self._ytdlp_conf.release_channel,
            latest=ctx.latest.version,
            current=ctx.current.version,
        )
