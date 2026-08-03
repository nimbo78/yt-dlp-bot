"""Answering "what is in this playlist" without downloading any of it.

`--flat-playlist` asks the source for its index page and stops there: no
per-item requests, nothing written to disk, and on a small host that matters as
much as the bandwidth. The reply always goes back, success or not — something is
holding a keyboard open on the other end, and silence is the one outcome it
cannot render.

The options come from the same per-host configuration the downloads use, so a
deployment behind a proxy or a rate limit enumerates the way it downloads. That
includes the cookie decision: YouTube is configured to try anonymously first,
because an authenticated session from a server address is what draws the bot
check, and enumeration has no business overriding that.
"""

import asyncio
import logging
from typing import Any, Final
from urllib.parse import urlsplit

from yt_dlp import YoutubeDL
from yt_shared.rabbit.publisher import RmqPublisher
from yt_shared.schemas.playlist import (
    PlaylistRequestPayload,
    PlaylistResultPayload,
)

from worker.core.playlist import apply_flat_overrides, entries_from_info
from worker.core.ytdlp_logger import YtdlpLogger
from worker.utils import cli_to_api
from ytdl_opts.per_host._base import AbstractHostConfig
from ytdl_opts.per_host._registry import HostConfRegistry

_UNKNOWN_ERROR: Final[str] = 'Could not read the playlist'

# Enumerations share the process, and the default thread pool, with the
# downloads. One at a time keeps a burst of menu presses from crowding out the
# thing people are actually waiting for.
_MAX_CONCURRENT: Final[int] = 1


class PlaylistHandler:
    def __init__(self) -> None:
        self._log = logging.getLogger(self.__class__.__name__)
        self._rmq_publisher = RmqPublisher()
        self._slot = asyncio.Semaphore(_MAX_CONCURRENT)

    async def handle(self, payload: PlaylistRequestPayload) -> None:
        async with self._slot:
            try:
                result = await self._enumerate(payload)
            except Exception as err:
                # Never end without a reply. Whatever went wrong here, the
                # keyboard waiting on it has to be told something.
                self._log.exception('Failed to enumerate %s', payload.url)
                result = self._failure(payload, str(err) or _UNKNOWN_ERROR)
        await self._rmq_publisher.send_playlist_result(result)

    async def _enumerate(
        self, payload: PlaylistRequestPayload
    ) -> PlaylistResultPayload:
        logger = YtdlpLogger(self._log)
        host_conf = self._host_conf(payload.url)
        self._log.info(
            'Enumerating %s as %s', payload.url, host_conf.__class__.__name__
        )
        # Building the options reads yt-dlp's config files and constructs its
        # whole option parser, so it belongs in the thread with the extraction
        # rather than on the loop that publishes progress for live downloads.
        info = await asyncio.to_thread(
            self._extract, host_conf, payload.limit, logger, payload.url
        )

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
            entries=playlist.entries,
            total=playlist.total,
        )

    @staticmethod
    def _host_conf(url: str) -> AbstractHostConfig:
        host_to_cls_map = HostConfRegistry.get_host_to_cls_map()
        host_cls = host_to_cls_map.get(urlsplit(url).netloc, host_to_cls_map[None])
        return host_cls(url=url)

    @classmethod
    def _extract(
        cls,
        host_conf: AbstractHostConfig,
        limit: int,
        logger: YtdlpLogger,
        url: str,
    ) -> dict[str, Any] | None:
        opts = cls._build_opts(host_conf, limit)
        opts['logger'] = logger
        with YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    @staticmethod
    def _build_opts(host_conf: AbstractHostConfig, limit: int) -> dict[str, Any]:
        """Flat and bounded, on top of whatever this host is configured with.

        Starting from `DEFAULT_YTDL_OPTS` rather than a hand-written list keeps
        a proxy, a rate limit or a metadata language set in `ytdl_opts/user.py`
        applying here too — a deployment that downloads should not fail to
        enumerate for a reason nobody can see.
        """
        opts = cli_to_api([
            *host_conf.DEFAULT_YTDL_OPTS,
            '--flat-playlist',
            '--skip-download',
        ])
        return apply_flat_overrides(
            opts, limit, cookies_last_resort=host_conf.COOKIES_LAST_RESORT
        )

    @staticmethod
    def _failure(payload: PlaylistRequestPayload, error: str) -> PlaylistResultPayload:
        return PlaylistResultPayload(
            url_id=payload.url_id,
            from_chat_id=payload.from_chat_id,
            ack_message_id=payload.ack_message_id,
            error=error,
        )
