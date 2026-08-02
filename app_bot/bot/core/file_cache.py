"""Sending a file Telegram already holds, instead of fetching it again.

Every upload records the id Telegram gave the file. Until now nothing read
those back, so the same link sent twice was downloaded twice — the whole cost of
a download, twice, for a byte-identical answer.

A file id survives the message that carried it being deleted, which matters
here: the status message always goes, and the link often does too. It is bound
to this bot's token, so changing the token empties the cache in effect, and it
is not promised to work forever — so the rule is try, and on any refusal fall
back to a real download. The cache is an optimisation, never a source of truth.
"""

import logging
from typing import TYPE_CHECKING, Any

from yt_shared.enums import DownMediaType, MediaFileType, VideoQuality
from yt_shared.schemas.file_cache import CachedFile

from bot.core.captions import build_video_caption_items
from bot.core.schemas import UserSchema

if TYPE_CHECKING:
    from bot.bot.client import VideoBotClient
    from bot.core.file_cache_store import FileCacheStore


class CachedDelivery:
    """Answers a repeat request from what Telegram is already storing."""

    def __init__(self, bot: 'VideoBotClient', store: 'FileCacheStore') -> None:
        self._log = logging.getLogger(self.__class__.__name__)
        self._bot = bot
        self._store = store

    async def find(
        self,
        *,
        url: str,
        media_type: DownMediaType,
        quality: VideoQuality,
        save_to_storage: bool,
    ) -> list[CachedFile]:
        """Look up what Telegram already holds for this exact request."""
        if save_to_storage:
            # The point of that setting is a file on disk, and a cache hit
            # produces none. Download it properly instead.
            self._log.debug('Storage requested for %s, not using the cache', url)
            return []
        try:
            return await self._store.find(url, media_type, quality)
        except Exception:
            # A cache that cannot be read is a miss, not a failed download.
            self._log.exception('Could not read the file cache for %s', url)
            return []

    async def send(
        self,
        entries: list[CachedFile],
        *,
        original_url: str,
        chat_id: int,
        reply_to_message_id: int | None,
        user: UserSchema,
    ) -> bool:
        """Send every cached file. False means fall back to a real download."""
        self._log.info(
            'Answering %s from the file cache with %d file(s)',
            original_url,
            len(entries),
        )
        for entry in entries:
            for target in self._targets(chat_id, user):
                sent = await self._send(
                    entry=entry,
                    chat_id=target,
                    original_url=original_url,
                    user=user,
                    reply_to_message_id=(
                        reply_to_message_id if target == chat_id else None
                    ),
                )
                if not sent and target == chat_id:
                    # Telegram no longer accepts this id. Nothing has reached
                    # the person who asked, so let the download proceed.
                    self._log.info(
                        'Cached id for %s was refused, downloading instead',
                        original_url,
                    )
                    return False
        return True

    @staticmethod
    def _targets(chat_id: int, user: UserSchema) -> list[int]:
        """List the originating chat, plus the forward group if one is set.

        Kept the same as a fresh download, so a cache hit is not quietly missing
        from the group a user set up.
        """
        targets = [chat_id]
        if user.upload.forward_to_group and user.upload.forward_group_id:
            targets.append(user.upload.forward_group_id)
        return targets

    async def _send(
        self,
        *,
        entry: CachedFile,
        chat_id: int,
        original_url: str,
        user: UserSchema,
        reply_to_message_id: int | None,
    ) -> bool:
        kwargs: dict[str, Any] = {
            'chat_id': chat_id,
            'caption': self._caption(entry, original_url, user),
            # Captions carry raw titles and links; parsing them as markup
            # would mangle anything with a bracket in it.
            'parse_mode': self._bot.PLAIN_CAPTION,
            'disable_notification': user.upload.silent,
        }
        if reply_to_message_id:
            kwargs['reply_to_message_id'] = reply_to_message_id
        if entry.duration is not None:
            kwargs['duration'] = int(entry.duration)

        try:
            if entry.file_type is MediaFileType.AUDIO:
                await self._bot.send_audio(audio=entry.file_id, **kwargs)
            else:
                await self._bot.send_video(
                    video=entry.file_id,
                    supports_streaming=True,
                    **kwargs,
                )
        except Exception as err:
            self._log.warning(
                'Telegram refused the cached id %s for chat %s: %s',
                entry.file_id,
                chat_id,
                err,
            )
            return False
        return True

    def _caption(
        self, entry: CachedFile, original_url: str, user: UserSchema
    ) -> str:
        if entry.file_type is MediaFileType.AUDIO:
            # Matches a fresh audio upload, which ignores the caption settings.
            return '\n'.join(filter(None, (entry.title, original_url)))
        return '\n'.join(
            build_video_caption_items(
                user.upload.video_caption,
                title=entry.title,
                filename=entry.filename,
                url=original_url,
                file_size=entry.file_size,
            )
        )
