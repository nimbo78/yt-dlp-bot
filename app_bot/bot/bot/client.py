import asyncio
import logging
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram.errors import RPCError

from bot.core.file_cache import CachedDelivery
from bot.core.file_cache_store import PostgresFileCacheStore
from bot.core.i18n import t
from bot.core.pending_download_store import PostgresPendingDownloadStore
from bot.core.pending_downloads import PendingDownloads
from bot.core.playlist_store import PostgresPlaylistStore
from bot.core.playlists import Playlists
from bot.core.schemas import ConfigSchema, UserSchema
from bot.core.startup_message_store import PostgresStartupMessageStore
from bot.core.startup_notice import StartupNotice


class VideoBotClient(Client):
    """Extended Pyrogram's `Client` class."""

    _RUN_FOREVER_SLEEP_SECONDS: int = 86400
    # For captions built from titles and links, which are text and not markup.
    # Exposed here so the modules that build them need not import Pyrogram.
    PLAIN_CAPTION: ParseMode = ParseMode.DISABLED

    def __init__(self, *args, conf: ConfigSchema, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._log = logging.getLogger(self.__class__.__name__)
        self._log.info('Initializing bot client')
        self.conf = conf

        self.allowed_users: dict[int, UserSchema] = {}
        self.admin_users: dict[int, UserSchema] = {}
        self.startup_notice = StartupNotice(self, PostgresStartupMessageStore())
        self.cached_delivery = CachedDelivery(self, PostgresFileCacheStore())
        self.pending_downloads = PendingDownloads(
            PostgresPendingDownloadStore(self)
        )
        self.playlists = Playlists(PostgresPlaylistStore())

        for user in self.conf.telegram.allowed_users:
            self.allowed_users[user.id] = user
            if user.is_admin:
                self.admin_users[user.id] = user

    async def run_forever(self) -> None:
        """Firstly, 'await bot.start()' should be called."""
        if not self.is_initialized:
            raise RuntimeError('Bot was not started (initialized).')
        while True:
            await asyncio.sleep(self._RUN_FOREVER_SLEEP_SECONDS)

    def language_for(self, *candidate_ids: int | None) -> str:
        """Pick the language to address someone in: theirs, or the global default.

        Several ids may be offered because a group is configured under its chat
        id while the person writing has one of their own; the first that names a
        user with a language of their own wins.
        """
        for candidate_id in candidate_ids:
            user = self.allowed_users.get(candidate_id) if candidate_id else None
            if user is not None and user.lang_code:
                return user.lang_code
        return self.conf.telegram.lang_code

    def wants_source_message_deleted(self, user: UserSchema | None) -> bool:
        """Decide whether to remove the link: the user's setting wins."""
        if user is None:
            return False
        if user.delete_source_message is not None:
            return user.delete_source_message
        return self.conf.telegram.delete_source_message

    async def send_translated_to_users(
        self, key: str, user_ids: Iterable[int], **params: Any
    ) -> None:
        """Send one message, rendered in each recipient's own language.

        Recipients are grouped by language so a message still costs one render
        and one gather, however many people receive it.
        """
        by_language: dict[str, list[int]] = defaultdict(list)
        for user_id in user_ids:
            by_language[self.language_for(user_id)].append(user_id)
        for language, ids in by_language.items():
            await self.send_message_to_users(
                text=t(key, language, **params), user_ids=ids
            )

    async def send_translated_to_admins(self, key: str, **params: Any) -> None:
        await self.send_translated_to_users(
            key=key, user_ids=self.admin_users.keys(), **params
        )

    async def send_message_to_users(
        self, text: str, user_ids: Iterable[int], parse_mode: ParseMode = ParseMode.HTML
    ) -> None:
        coros = []
        self._log.debug('Sending message "%s" to chat ids %s', text, user_ids)
        for user_id in user_ids:
            coros.append(self.send_message(user_id, text, parse_mode=parse_mode))
        results = await asyncio.gather(*coros, return_exceptions=True)
        for user_id, result in zip(user_ids, results, strict=False):
            if isinstance(result, RPCError):
                self._log.error('User %s did not receive message: %s', user_id, result)

    async def send_message_all(
        self, text: str, parse_mode: ParseMode = ParseMode.HTML
    ) -> None:
        """Send a message to all defined user IDs in config.json."""
        await self.send_message_to_users(
            text=text, user_ids=self.allowed_users.keys(), parse_mode=parse_mode
        )

    async def send_message_admins(
        self, text: str, parse_mode: ParseMode = ParseMode.HTML
    ) -> None:
        """Send a message to all defined user IDs in config.json."""
        await self.send_message_to_users(
            text=text, user_ids=self.admin_users.keys(), parse_mode=parse_mode
        )
