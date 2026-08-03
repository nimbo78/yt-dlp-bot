import asyncio
import html
import logging
import re
from itertools import product
from typing import ClassVar, Final

from pyrogram.enums import ParseMode
from pyrogram.types import CallbackQuery, Message
from yt_shared.enums import DownMediaType, TaskSource, TelegramChatType, VideoQuality
from yt_shared.rabbit.publisher import RmqPublisher
from yt_shared.schemas.media import InbMediaPayload
from yt_shared.schemas.playlist import PlaylistRequestPayload

from bot.bot.client import VideoBotClient
from bot.core.collection_links import carries_playlist, is_collection_link
from bot.core.i18n import t
from bot.core.keyboards import (
    CANCEL_PREFIX,
    DOWNLOAD_PREFIX,
    MEDIA_TYPE_PREFIX,
    build_media_type_keyboard,
    build_playlist_keyboard,
    build_quality_keyboard,
)
from bot.core.pending_downloads import PendingDownload, generate_url_id
from bot.core.playlist_menu import (
    MAX_SELECTED,
    PLAYLIST_ALL_PREFIX,
    PLAYLIST_ITEM_PREFIX,
    PLAYLIST_NEXT_PREFIX,
    PLAYLIST_PAGE_PREFIX,
    PLAYLIST_PREFIX,
    find_entry,
    select_all,
    selected_entries,
    toggle,
    truncate_label,
)
from bot.core.schemas import UserSchema
from bot.core.utils import bold, get_user_id, strip_url_params


class TelegramCallback:
    # Callback data is packed as colon-separated fields; a payload with the
    # wrong number of them is from an older build and cannot be trusted.
    _MEDIA_TYPE_FIELDS: Final[int] = 2
    _DOWNLOAD_FIELDS: Final[int] = 3

    _QUALITY_LABELS: ClassVar[dict[VideoQuality, str]] = {
        VideoQuality.UHD_4K: '4K',
        VideoQuality.QHD_1440P: '1440p',
        VideoQuality.FHD_1080P: '1080p',
        VideoQuality.HD_720P: '720p',
        VideoQuality.SD_480P: '480p',
        VideoQuality.LD_360P: '360p',
    }
    _MEDIA_TYPE_EMOJI: ClassVar[dict[DownMediaType, str]] = {
        DownMediaType.VIDEO: '🎬',
        DownMediaType.AUDIO: '🎵',
        DownMediaType.AUDIO_VIDEO: '🎬+🎵',
    }

    def __init__(self) -> None:
        self._log = logging.getLogger(self.__class__.__name__)
        self._rmq_publisher = RmqPublisher()

    @staticmethod
    async def on_start(client: VideoBotClient, message: Message) -> None:
        await message.reply(
            bold(
                t(
                    'start.greeting',
                    client.language_for(get_user_id(message), message.chat.id),
                )
            ),
            parse_mode=ParseMode.HTML,
            reply_to_message_id=message.id,
        )

    async def on_nocache(self, client: VideoBotClient, message: Message) -> None:
        """Handle /nocache <url>: download again, ignoring the stored copy."""
        language = client.language_for(get_user_id(message), message.chat.id)
        _, _, rest = message.text.partition(' ')
        if not rest.strip():
            await message.reply(
                t('format.nocache_usage', language),
                parse_mode=ParseMode.HTML,
                reply_to_message_id=message.id,
            )
            return
        await self.on_message(client, message, skip_cache=True, text=rest)

    async def on_message(
        self,
        client: VideoBotClient,
        message: Message,
        *,
        skip_cache: bool = False,
        text: str | None = None,
    ) -> None:
        """Receive video URL and show format selection keyboard."""
        self._log.debug('Received Telegram Message: %s', message)
        text = text if text is not None else message.text
        if not text:
            self._log.debug('Forwarded message, skipping')
            return

        urls = text.splitlines()
        user = client.allowed_users[get_user_id(message)]
        if user.use_url_regex_match:
            urls = self._filter_urls(
                urls=urls, regexes=client.conf.telegram.url_validation_regexes
            )
            if not urls:
                self._log.debug('No urls to download, skipping message')
                return

        language = client.language_for(user.id, message.chat.id)
        # Process each URL - show format selection keyboard
        for url in urls:
            await self._show_format_selection(
                client=client,
                message=message,
                url=url,
                user=user,
                language=language,
                skip_cache=skip_cache,
            )

    async def _show_format_selection(  # noqa: PLR0913
        self,
        client: VideoBotClient,
        message: Message,
        url: str,
        user: UserSchema,
        language: str,
        skip_cache: bool = False,
    ) -> None:
        """Show inline keyboard for format selection."""
        from_user_id = message.from_user.id if message.from_user else None
        processed_url = strip_url_params(url)

        # Two different questions. The warning is about loss: only a link that
        # points *only* at a collection drops anything, so `watch?v=…&list=…`
        # earns no notice. The button is about offer: that same link names a
        # playlist, and its owner may want to pick from it.
        warning = (
            f'\n\n{t("format.playlist_warning", language)}'
            if is_collection_link(url)
            else ''
        )

        # Send message with format selection keyboard
        ack_message = await message.reply(
            text=f'{t("format.choose", language)}\n\n<code>{url}</code>{warning}',
            parse_mode=ParseMode.HTML,
            reply_to_message_id=message.id,
            reply_markup=build_media_type_keyboard(
                url_id=generate_url_id(message.chat.id, message.id),
                language=language,
                offer_playlist=carries_playlist(url),
            ),
        )

        # Store pending download
        url_id = generate_url_id(message.chat.id, message.id)
        pending = PendingDownload(
            url=processed_url,
            original_url=url,
            from_chat_id=message.chat.id,
            from_chat_type=TelegramChatType(message.chat.type.value),
            from_user_id=from_user_id,
            message_id=message.id,
            ack_message_id=ack_message.id,
            save_to_storage=user.save_to_storage,
            user=user,
            skip_cache=skip_cache,
        )
        await client.pending_downloads.add(url_id, pending)

    @staticmethod
    def _split_indexed(data: str, prefix: str) -> tuple[str, int | None]:
        """Split `<prefix><url_id>:<number>` into its two halves.

        `rpartition` rather than `split`, because a url_id contains a colon-free
        underscore but nothing guarantees that forever. A number that will not
        parse comes back as ``None`` rather than raising: it means a build that
        no longer exists drew the button.
        """
        url_id, _, number = data.removeprefix(prefix).rpartition(':')
        try:
            return url_id, int(number)
        except ValueError:
            return url_id, None

    async def _require_pending(
        self,
        client: VideoBotClient,
        callback_query: CallbackQuery,
        url_id: str,
        language: str,
    ) -> PendingDownload | None:
        """Fetch the choice this button belongs to, or say it has expired.

        Every button here needs the same thing and answers its absence the same
        way, including removing the keyboard that can no longer do anything.
        """
        pending = await client.pending_downloads.get(url_id)
        if pending is None:
            await callback_query.answer(t('format.session_expired', language))
            await callback_query.message.delete()
        return pending

    async def on_callback_query(
        self, client: VideoBotClient, callback_query: CallbackQuery
    ) -> None:
        """Handle callback queries from inline keyboards."""
        data = callback_query.data
        self._log.debug('Received callback query: %s', data)

        language = client.language_for(
            callback_query.from_user.id if callback_query.from_user else None,
            callback_query.message.chat.id if callback_query.message else None,
        )

        if data.startswith(PLAYLIST_ITEM_PREFIX):
            await self._handle_playlist_item(client, callback_query, language)
        elif data.startswith(PLAYLIST_PAGE_PREFIX):
            await self._handle_playlist_page(client, callback_query, language)
        elif data.startswith(PLAYLIST_ALL_PREFIX):
            await self._handle_playlist_select_all(client, callback_query, language)
        elif data.startswith(PLAYLIST_NEXT_PREFIX):
            await self._handle_playlist_next(client, callback_query, language)
        elif data.startswith(PLAYLIST_PREFIX):
            await self._handle_playlist_request(client, callback_query, language)
        elif data.startswith(MEDIA_TYPE_PREFIX):
            await self._handle_media_type_selection(client, callback_query, language)
        elif data.startswith(DOWNLOAD_PREFIX):
            await self._handle_download_selection(client, callback_query, language)
        elif data.startswith(CANCEL_PREFIX):
            await self._handle_cancel(client, callback_query, language)
        else:
            # The page counter lands here, and so does callback data from a
            # build that no longer exists. Both need answering: an unanswered
            # query leaves the button spinning until the client gives up.
            await callback_query.answer()

    async def _handle_playlist_request(
        self, client: VideoBotClient, callback_query: CallbackQuery, language: str
    ) -> None:
        """Ask the worker to list what is behind a collection link."""
        url_id = callback_query.data.removeprefix(PLAYLIST_PREFIX)
        pending = await self._require_pending(client, callback_query, url_id, language)
        if pending is None:
            return

        payload = PlaylistRequestPayload(
            url_id=url_id,
            url=pending.url,
            from_chat_id=pending.from_chat_id,
            ack_message_id=pending.ack_message_id,
        )
        if not await self._rmq_publisher.send_playlist_request(payload):
            self._log.error('Failed to queue playlist request for %s', pending.url)
            await callback_query.answer(t('format.queue_failed', language))
            return

        # Reading a playlist takes a network round trip, and a keyboard that
        # does not visibly react to a press reads as a keyboard that is broken.
        await callback_query.answer(t('playlist.reading_toast', language))
        await callback_query.message.edit_text(
            text=t('playlist.reading', language), parse_mode=ParseMode.HTML
        )

    async def _handle_playlist_page(
        self, client: VideoBotClient, callback_query: CallbackQuery, language: str
    ) -> None:
        """Turn to another page of an already-read playlist."""
        url_id, page = self._split_indexed(callback_query.data, PLAYLIST_PAGE_PREFIX)
        if page is None:
            # A malformed page number is not worth a database read.
            await callback_query.answer(t('format.invalid_selection', language))
            return

        playlist = await client.playlists.load(url_id)
        if playlist is None:
            await callback_query.answer(t('playlist.expired', language))
            return

        markup = build_playlist_keyboard(
            playlist.entries, url_id, page, language, playlist.selected
        )
        try:
            await callback_query.edit_message_reply_markup(reply_markup=markup)
        except Exception:
            # Telegram refuses an edit that changes nothing, which a double
            # press produces. Answering anyway stops the button spinning, and
            # the page on screen is already the one that was asked for.
            self._log.debug('Could not turn to page %d of %s', page, url_id)
        await callback_query.answer()

    async def _handle_playlist_item(
        self, client: VideoBotClient, callback_query: CallbackQuery, language: str
    ) -> None:
        """Tick or untick one entry."""
        url_id, index = self._split_indexed(callback_query.data, PLAYLIST_ITEM_PREFIX)
        if index is None:
            await callback_query.answer(t('format.invalid_selection', language))
            return

        playlist = await client.playlists.load(url_id)
        if playlist is None:
            await callback_query.answer(t('playlist.expired', language))
            return
        if find_entry(playlist.entries, index) is None:
            await callback_query.answer(t('format.invalid_selection', language))
            return

        selected = toggle(playlist.selected, index)
        if selected == playlist.selected:
            # `toggle` returns the set unchanged when the cap is reached, which
            # is the only way to tell a refusal from a no-op.
            await callback_query.answer(
                t('playlist.too_many', language, limit=MAX_SELECTED)
            )
            return

        await client.playlists.set_selected(url_id, selected)
        await self._redraw(client, callback_query, url_id, playlist.entries, selected)

    async def _handle_playlist_select_all(
        self, client: VideoBotClient, callback_query: CallbackQuery, language: str
    ) -> None:
        """Tick everything that fits, or clear the lot."""
        url_id, flag = self._split_indexed(
            callback_query.data, PLAYLIST_ALL_PREFIX
        )
        if flag is None:
            await callback_query.answer(t('format.invalid_selection', language))
            return

        playlist = await client.playlists.load(url_id)
        if playlist is None:
            await callback_query.answer(t('playlist.expired', language))
            return

        selected = select_all(playlist.entries) if flag else frozenset()
        await client.playlists.set_selected(url_id, selected)
        if flag and len(selected) < len(playlist.entries):
            await callback_query.answer(
                t('playlist.capped', language, limit=MAX_SELECTED)
            )
        await self._redraw(client, callback_query, url_id, playlist.entries, selected)

    async def _redraw(
        self,
        client: VideoBotClient,
        callback_query: CallbackQuery,
        url_id: str,
        entries: list,
        selected: frozenset[int],
    ) -> None:
        """Put the ticks that were just changed back on screen.

        The page is read off the message rather than carried in the callback
        data, which has no room for it: the keyboard on screen already knows
        which page it is showing.
        """
        language = client.language_for(
            callback_query.from_user.id if callback_query.from_user else None,
            callback_query.message.chat.id if callback_query.message else None,
        )
        page = self._page_on_screen(callback_query, url_id)
        markup = build_playlist_keyboard(entries, url_id, page, language, selected)
        try:
            await callback_query.edit_message_reply_markup(reply_markup=markup)
        except Exception:
            self._log.debug('Could not redraw the menu for %s', url_id)
        await callback_query.answer()

    @staticmethod
    def _page_on_screen(callback_query: CallbackQuery, url_id: str) -> int:
        """Work out which page the keyboard being pressed is showing.

        Read back from the navigation buttons it already carries. Sending the
        page in every entry's callback data would cost bytes the 64-byte budget
        does not have to spare, and holding it server-side would be one more
        thing to keep in step with what is on screen.
        """
        markup = callback_query.message.reply_markup if callback_query.message else None
        for row in getattr(markup, 'inline_keyboard', []) or []:
            for button in row:
                data = getattr(button, 'callback_data', None)
                if data and data.startswith(f'{PLAYLIST_PAGE_PREFIX}{url_id}:'):
                    # The "next" arrow points one past the current page, and
                    # wraps, so the page is what it points at minus one.
                    _, _, number = data.rpartition(':')
                    try:
                        return int(number) - 1
                    except ValueError:
                        return 0
        return 0

    async def _handle_playlist_next(
        self, client: VideoBotClient, callback_query: CallbackQuery, language: str
    ) -> None:
        """Done ticking — ask for the format, then the quality, once for all."""
        url_id = callback_query.data.removeprefix(PLAYLIST_NEXT_PREFIX)
        pending = await self._require_pending(client, callback_query, url_id, language)
        if pending is None:
            return

        playlist = await client.playlists.load(url_id)
        if playlist is None:
            await callback_query.answer(t('playlist.expired', language))
            return

        chosen = selected_entries(playlist.entries, playlist.selected)
        if not chosen:
            await callback_query.answer(t('playlist.nothing_selected', language))
            return

        await callback_query.message.edit_text(
            text=t('playlist.chosen', language, count=len(chosen)),
            parse_mode=ParseMode.HTML,
            reply_markup=build_media_type_keyboard(url_id, language),
        )
        await callback_query.answer()

    async def _handle_media_type_selection(
        self, client: VideoBotClient, callback_query: CallbackQuery, language: str
    ) -> None:
        """Handle media type selection (Video/Audio/Both)."""
        data = callback_query.data.removeprefix(MEDIA_TYPE_PREFIX)
        parts = data.split(':')

        if len(parts) != self._MEDIA_TYPE_FIELDS:
            await callback_query.answer(t('format.invalid_selection', language))
            return

        media_type_str, url_id = parts

        # Handle back button
        if media_type_str == 'back':
            pending = await client.pending_downloads.get(url_id)
            if not pending:
                await callback_query.answer(t('format.session_expired', language))
                await callback_query.message.delete()
                return

            await callback_query.message.edit_text(
                text=(
                    f'{t("format.choose", language)}\n\n'
                    f'<code>{pending.original_url}</code>'
                ),
                parse_mode=ParseMode.HTML,
                # Recomputed rather than remembered: after an item was picked
                # the pending download points at that item, so the offer to
                # list correctly disappears.
                reply_markup=build_media_type_keyboard(
                    url_id,
                    language,
                    offer_playlist=carries_playlist(pending.original_url),
                ),
            )
            await callback_query.answer()
            return

        pending = await client.pending_downloads.get(url_id)
        if not pending:
            await callback_query.answer(t('format.session_expired', language))
            await callback_query.message.delete()
            return

        try:
            media_type = DownMediaType(media_type_str)
        except ValueError:
            await callback_query.answer(t('format.invalid_media_type', language))
            return

        # For audio, directly start download
        if media_type == DownMediaType.AUDIO:
            await self._start_download(
                client=client,
                callback_query=callback_query,
                url_id=url_id,
                media_type=media_type,
                quality=VideoQuality.BEST,
                language=language,
            )
            return

        # For video, show quality selection
        await callback_query.message.edit_text(
            text=(
                f'{t("format.choose_quality", language)}\n\n'
                f'<code>{pending.original_url}</code>'
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=build_quality_keyboard(url_id, media_type, language),
        )
        await callback_query.answer()

    async def _handle_download_selection(
        self, client: VideoBotClient, callback_query: CallbackQuery, language: str
    ) -> None:
        """Handle download with selected quality."""
        data = callback_query.data.removeprefix(DOWNLOAD_PREFIX)
        parts = data.split(':')

        if len(parts) != self._DOWNLOAD_FIELDS:
            await callback_query.answer(t('format.invalid_selection', language))
            return

        media_type_str, quality_str, url_id = parts

        try:
            media_type = DownMediaType(media_type_str)
            quality = VideoQuality(quality_str)
        except ValueError:
            await callback_query.answer(t('format.invalid_selection', language))
            return

        await self._start_download(
            client=client,
            callback_query=callback_query,
            url_id=url_id,
            media_type=media_type,
            quality=quality,
            language=language,
        )

    async def _start_download(  # noqa: PLR0913
        self,
        client: VideoBotClient,
        callback_query: CallbackQuery,
        url_id: str,
        media_type: DownMediaType,
        quality: VideoQuality,
        language: str,
    ) -> None:
        """Start the download process."""
        pending, playlist = await asyncio.gather(
            client.pending_downloads.remove(url_id), client.playlists.load(url_id)
        )
        if not pending:
            await callback_query.answer(t('format.session_expired', language))
            await callback_query.message.delete()
            return
        await client.playlists.remove(url_id)

        chosen = (
            selected_entries(playlist.entries, playlist.selected)
            if playlist is not None
            else []
        )
        if chosen:
            await self._start_batch(
                client, callback_query, pending, chosen, media_type, quality, language
            )
            return

        # Build quality text for message
        quality_text = ''
        if media_type != DownMediaType.AUDIO:
            label = self._QUALITY_LABELS.get(quality) or t(
                'format.quality_best', language
            )
            quality_text = f' ({label})'

        summary = (
            f'{self._MEDIA_TYPE_EMOJI.get(media_type, "")} '
            f'{media_type.value}{quality_text}\n'
            f'<code>{pending.original_url}</code>'
        )

        # Ask the cache first: the same link at the same quality is a file
        # Telegram is already holding, and re-fetching it costs a full download.
        cached = []
        if not pending.skip_cache:
            cached = await client.cached_delivery.find(
                url=pending.url,
                media_type=media_type,
                quality=quality,
                save_to_storage=pending.save_to_storage,
            )

        if cached:
            await callback_query.message.edit_text(
                text=f'{t("format.from_cache", language)}\n\n{summary}',
                parse_mode=ParseMode.HTML,
            )
            await callback_query.answer(t('format.from_cache_toast', language))
            if await self._deliver_cached(client, pending, cached):
                return
            # Telegram refused the stored id; carry on as an ordinary download.

        # Update message to show download started
        await callback_query.message.edit_text(
            text=f'{t("format.started", language)}\n\n{summary}',
            parse_mode=ParseMode.HTML,
        )
        await callback_query.answer(t('format.started_toast', language))

        # Send to worker
        payload = InbMediaPayload(
            url=pending.url,
            original_url=pending.original_url,
            message_id=pending.message_id,
            ack_message_id=pending.ack_message_id,
            from_user_id=pending.from_user_id,
            from_chat_id=pending.from_chat_id,
            from_chat_type=pending.from_chat_type,
            source=TaskSource.BOT,
            save_to_storage=pending.save_to_storage,
            download_media_type=media_type,
            video_quality=quality,
            custom_filename=None,
            automatic_extension=False,
        )

        is_sent = await self._rmq_publisher.send_for_download(payload)
        if not is_sent:
            self._log.error('Failed to publish URL %s to message broker', pending.url)
            await callback_query.message.edit_text(
                text=t('format.queue_failed', language),
                parse_mode=ParseMode.HTML,
            )

    async def _start_batch(  # noqa: PLR0913
        self,
        client: VideoBotClient,
        callback_query: CallbackQuery,
        pending: PendingDownload,
        chosen: list,
        media_type: DownMediaType,
        quality: VideoQuality,
        language: str,
    ) -> None:
        """Queue every ticked entry at the one format and quality just chosen.

        Each gets a status message of its own, and therefore its own task, which
        is why none of the pipeline below the bot needed changing: the worker,
        the task model and the progress path see a stream of ordinary single
        downloads. The alternative — one message counting "3 of 10" — would have
        meant teaching every one of those about batches.

        Queued, not run: `MAX_SIMULTANEOUS_DOWNLOADS` decides how many actually
        proceed at once, so a selection of twenty does not become twenty
        concurrent downloads on a machine that cannot hold two.
        """
        await callback_query.message.edit_text(
            text=t('playlist.queueing', language, count=len(chosen)),
            parse_mode=ParseMode.HTML,
        )
        await callback_query.answer(t('format.started_toast', language))

        queued = 0
        for entry in chosen:
            status = await self._queue_one(
                callback_query, pending, entry, media_type, quality, language
            )
            queued += status

        await callback_query.message.edit_text(
            text=t(
                'playlist.queued' if queued == len(chosen) else 'playlist.queued_some',
                language,
                count=queued,
                total=len(chosen),
            ),
            parse_mode=ParseMode.HTML,
        )

        if queued:
            # Recorded only now, and only for what actually made it onto the
            # queue: the count has to match the number of endings that will
            # arrive, or nobody is ever last and the tidying never happens.
            await client.batches.start(
                chat_id=pending.from_chat_id,
                message_id=pending.message_id,
                count=queued,
                summary_message_id=callback_query.message.id,
            )

    async def _queue_one(  # noqa: PLR0913
        self,
        callback_query: CallbackQuery,
        pending: PendingDownload,
        entry: object,
        media_type: DownMediaType,
        quality: VideoQuality,
        language: str,
    ) -> int:
        """Post one entry's status message and queue it against that message.

        Returns 1 when it was queued, so the caller can report how many of the
        selection actually made it — a broker that refuses halfway through
        should not be reported as a complete success.
        """
        title = html.escape(truncate_label(entry.title, limit=60))
        try:
            status = await callback_query.message.reply(
                text=t('playlist.item_queued', language, index=entry.index,
                       title=title),
                parse_mode=ParseMode.HTML,
                reply_to_message_id=pending.message_id,
                disable_notification=True,
            )
        except Exception:
            self._log.exception('Could not post a status message for %s', entry.url)
            return 0

        payload = InbMediaPayload(
            url=strip_url_params(entry.url),
            original_url=entry.url,
            message_id=pending.message_id,
            ack_message_id=status.id,
            from_user_id=pending.from_user_id,
            from_chat_id=pending.from_chat_id,
            from_chat_type=pending.from_chat_type,
            source=TaskSource.BOT,
            save_to_storage=pending.save_to_storage,
            download_media_type=media_type,
            video_quality=quality,
            custom_filename=None,
            automatic_extension=False,
        )
        if await self._rmq_publisher.send_for_download(payload):
            return 1

        self._log.error('Failed to publish %s to message broker', entry.url)
        await status.edit_text(
            text=t('format.queue_failed', language), parse_mode=ParseMode.HTML
        )
        return 0

    async def _deliver_cached(
        self,
        client: VideoBotClient,
        pending: PendingDownload,
        cached: list,
    ) -> bool:
        """Send the stored copy and tidy up exactly as a real download would."""
        delivered = await client.cached_delivery.send(
            cached,
            original_url=pending.original_url,
            chat_id=pending.from_chat_id,
            reply_to_message_id=pending.message_id,
            user=pending.user,
        )
        if not delivered:
            return False

        # From here the chat should look the same as after a fresh download:
        # the status message goes, and the link goes if that is configured.
        for message_id, wanted in (
            (pending.ack_message_id, True),
            (
                pending.message_id,
                client.wants_source_message_deleted(pending.user),
            ),
        ):
            if not wanted:
                continue
            try:
                await client.delete_messages(
                    chat_id=pending.from_chat_id, message_ids=message_id
                )
            except Exception as err:
                self._log.warning(
                    'Could not remove message %s in chat %s: %s',
                    message_id,
                    pending.from_chat_id,
                    err,
                )
        return True

    async def _handle_cancel(
        self, client: VideoBotClient, callback_query: CallbackQuery, language: str
    ) -> None:
        """Handle cancel button."""
        url_id = callback_query.data.removeprefix(CANCEL_PREFIX)
        # The menu is keyed by the same id but has a lifetime of its own, so
        # every way a choice ends has to take it along. Otherwise a cancelled
        # playlist sits in the table for six hours waiting for the sweep.
        await asyncio.gather(
            client.pending_downloads.remove(url_id), client.playlists.remove(url_id)
        )

        await callback_query.message.edit_text(
            text=t('format.cancelled', language),
            parse_mode=ParseMode.HTML,
        )
        await callback_query.answer(t('format.cancelled_toast', language))

    def _filter_urls(self, urls: list[str], regexes: list[str]) -> list[str]:
        """Return valid urls."""
        self._log.debug('Matching urls: %s against regexes %s', urls, regexes)
        valid_urls: list[str] = []
        for url, regex in product(urls, regexes):
            if re.match(regex, url):
                valid_urls.append(url)

        valid_urls = list(dict.fromkeys(valid_urls))
        self._log.debug('Matched urls: %s', valid_urls)
        return valid_urls
