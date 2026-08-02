"""Answering "what is in this playlist" without downloading any of it.

`--flat-playlist` asks the source for its index page and stops there: no
per-item requests, nothing written to disk, and on a small host that matters as
much as the bandwidth. The reply always goes back, success or not — something is
holding a keyboard open on the other end, and silence is the one outcome it
cannot render.
"""

import asyncio
import logging
from typing import Any

from yt_dlp import YoutubeDL
from yt_shared.rabbit.publisher import RmqPublisher
from yt_shared.schemas.playlist import (
    PlaylistEntryPayload,
    PlaylistRequestPayload,
    PlaylistResultPayload,
)

from worker.core.playlist import entries_from_info
from worker.core.ytdlp_logger import YtdlpLogger
from worker.utils import cli_to_api, get_cookies_opts_if_not_empty

_UNKNOWN_ERROR = 'Could not read the playlist'


class PlaylistHandler:
    def __init__(self) -> None:
        self._log = logging.getLogger(self.__class__.__name__)
        self._rmq_publisher = RmqPublisher()

    async def handle(self, payload: PlaylistRequestPayload) -> None:
        try:
            result = await self._enumerate(payload)
        except Exception as err:
            # Never let this end without a reply. Whatever went wrong here, the
            # keyboard waiting on it has to be told something.
            self._log.exception('Failed to enumerate %s', payload.url)
            result = self._failure(payload, str(err) or _UNKNOWN_ERROR)
        await self._rmq_publisher.send_playlist_result(result)

    async def _enumerate(self, payload: PlaylistRequestPayload) -> PlaylistResultPayload:
        opts = self._build_opts(payload.limit)
        logger = YtdlpLogger(self._log)
        opts['logger'] = logger

        self._log.info('Enumerating %s with options: %s', payload.url, opts)
        # yt-dlp is synchronous and this reaches the network, so it must not run
        # on the event loop: the bot's progress updates share this process.
        info = await asyncio.to_thread(self._extract, opts, payload.url)

        if info is None:
            # `ignoreerrors` makes yt-dlp return None rather than raise, so the
            # reason is only in what the logger collected.
            return self._failure(payload, logger.last_error() or _UNKNOWN_ERROR)

        playlist = entries_from_info(info, limit=payload.limit)
        self._log.info(
            'Enumerated %s: %d of %d offerable',
            payload.url,
            len(playlist.entries),
            playlist.total,
        )
        return PlaylistResultPayload(
            url_id=payload.url_id,
            from_chat_id=payload.from_chat_id,
            ack_message_id=payload.ack_message_id,
            title=playlist.title,
            entries=[
                PlaylistEntryPayload(index=e.index, title=e.title, url=e.url)
                for e in playlist.entries
            ],
            total=playlist.total,
        )

    @staticmethod
    def _extract(opts: dict[str, Any], url: str) -> dict[str, Any] | None:
        with YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    @staticmethod
    def _build_opts(limit: int) -> dict[str, Any]:
        """Flat, bounded, and carrying the cookies the downloads use.

        Built from CLI options through the same converter as every other
        yt-dlp call here, so a site that needs a session to list its contents
        gets the one already configured.
        """
        return cli_to_api([
            '--flat-playlist',
            '--skip-download',
            '--ignore-errors',
            '--playlist-end',
            str(limit),
            *get_cookies_opts_if_not_empty(),
        ])

    @staticmethod
    def _failure(payload: PlaylistRequestPayload, error: str) -> PlaylistResultPayload:
        return PlaylistResultPayload(
            url_id=payload.url_id,
            from_chat_id=payload.from_chat_id,
            ack_message_id=payload.ack_message_id,
            error=error,
        )
