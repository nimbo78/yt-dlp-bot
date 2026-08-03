"""Turning what the worker found in a playlist into a menu on screen."""

import html
import logging
from typing import TYPE_CHECKING

from pyrogram.enums import ParseMode
from yt_shared.schemas.playlist import PlaylistResultPayload

from bot.core.error_messages import classify, strip_extractor_prefix
from bot.core.i18n import t
from bot.core.keyboards import build_playlist_keyboard
from bot.core.playlist_menu import MenuEntry

if TYPE_CHECKING:
    from bot.bot.client import VideoBotClient


class PlaylistResultHandler:
    def __init__(self, bot: 'VideoBotClient') -> None:
        self._log = logging.getLogger(self.__class__.__name__)
        self._bot = bot

    async def handle(self, payload: PlaylistResultPayload) -> None:
        language = self._bot.language_for(payload.from_chat_id)
        if payload.error:
            await self._report_failure(payload, language)
            return

        entries = [
            MenuEntry(index=e.index, title=e.title, url=e.url) for e in payload.entries
        ]
        if not entries:
            # A link that looked like a collection and turned out to hold
            # nothing offerable. Saying so beats an empty keyboard.
            await self._edit(
                payload, t('playlist.empty', language), reply_markup=None
            )
            return

        await self._bot.playlists.save(payload.url_id, entries)
        await self._edit(
            payload,
            self._header(payload.title, len(entries), payload.total, language),
            reply_markup=build_playlist_keyboard(entries, payload.url_id, 0, language),
        )
        self._log.info(
            'Offered %d of %d entries for %s',
            len(entries),
            payload.total,
            payload.url_id,
        )

    @staticmethod
    def _header(title: str, shown: int, total: int, language: str) -> str:
        """Name the playlist and say how much of it is on offer.

        The counts are told apart on purpose: showing 100 of 250 as "100" reads
        as the whole thing, which is the same silent wrongness the warning about
        collection links exists to prevent.

        The title is escaped because it is somebody else's text going into an
        HTML message: one `<` in an album name and Telegram rejects the whole
        edit, so the menu never appears and nothing says why.
        """
        key = 'playlist.header_truncated' if total > shown else 'playlist.header'
        return t(key, language, title=html.escape(title), shown=shown, total=total)

    async def _report_failure(
        self, payload: PlaylistResultPayload, language: str
    ) -> None:
        """Explain the refusal through the same classifier as a failed download.

        A playlist fails for the reasons a video does — private, geo-blocked,
        needs a login — so it is worth the same sentence rather than a new one.
        """
        reason = strip_extractor_prefix(payload.error or '')
        friendly = classify(reason)
        if friendly is not None:
            text = (
                f'{friendly.emoji} <b>{t(friendly.title_key, language)}</b>\n\n'
                f'{t(friendly.hint_key, language)}'
            )
        else:
            text = t('playlist.failed', language)
        await self._edit(payload, text, reply_markup=None)

    async def _edit(
        self, payload: PlaylistResultPayload, text: str, reply_markup: object
    ) -> None:
        try:
            await self._bot.edit_message_text(
                chat_id=payload.from_chat_id,
                message_id=payload.ack_message_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )
        except Exception as err:
            # The message may have been deleted while the worker was reading
            # the playlist. Logged the way the other ack-message editors log it
            # — quietly, because a traceback for "the user deleted it" is noise.
            self._log.debug(
                'Could not show the playlist on message %s: %s',
                payload.ack_message_id,
                err,
            )
