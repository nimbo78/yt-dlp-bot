from typing import TYPE_CHECKING

from yt_shared.rabbit.rabbit_config import PLAYLIST_RESULT_QUEUE
from yt_shared.schemas.playlist import PlaylistResultPayload

from bot.core.handlers.playlist import PlaylistResultHandler
from bot.core.workers.abstract import AbstractDownloadResultWorker, RabbitWorkerType

if TYPE_CHECKING:
    from bot.bot.client import VideoBotClient


class PlaylistWorker(AbstractDownloadResultWorker):
    """Consumes what the worker found inside a playlist and offers it."""

    TYPE = RabbitWorkerType.PLAYLIST
    QUEUE_TYPE = PLAYLIST_RESULT_QUEUE
    SCHEMA_CLS = (PlaylistResultPayload,)

    def __init__(self, bot: 'VideoBotClient') -> None:
        super().__init__(bot)
        self._handler = PlaylistResultHandler(bot=bot)

    async def _process_body(self, body: PlaylistResultPayload) -> None:
        await self._handler.handle(body)
