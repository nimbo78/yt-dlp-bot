"""The single message the bot posts about its own start.

It used to be two messages, to everyone who had `send_startup_message` set, with
a notification sound, and they stayed in the chat forever. On a machine that
redeploys often that is a growing pile of log entries nobody asked for.

Now: one message, to admins only, silent, and removed after a while. The
greeting goes out immediately and the yt-dlp version line is *appended* to it
when the check finishes — waiting for that check instead would mean no greeting
at all whenever GitHub is slow, which is precisely when knowing the bot came
back matters.

Only the start is ephemeral. The periodic "a new version is out" notice asks the
reader to do something, so it stays until they dismiss it themselves.
"""

import asyncio
import contextlib
import html
import logging
from typing import TYPE_CHECKING, Any

from bot.core.i18n import t

if TYPE_CHECKING:
    from bot.bot.client import VideoBotClient
    from bot.core.startup_message_store import StartupMessageStore


class StartupNotice:
    """Posts, extends and later removes the bot's own startup message."""

    def __init__(self, bot: 'VideoBotClient', store: 'StartupMessageStore') -> None:
        self._log = logging.getLogger(self.__class__.__name__)
        self._bot = bot
        self._store = store
        # chat id -> (message id, text as it currently stands)
        self._posted: dict[int, tuple[int, str]] = {}
        self._removal: asyncio.Task | None = None

    @property
    def _ttl(self) -> int:
        return self._bot.conf.telegram.startup_message_ttl

    def recipients(self) -> list[int]:
        """Admins who have not opted out.

        Deliberately narrower than it used to be: a yt-dlp version is not
        something a non-admin can act on, and a restart is not their news.
        """
        return [
            user.id
            for user in self._bot.admin_users.values()
            if user.send_startup_message
        ]

    async def clear_previous(self) -> None:
        """Remove whatever the previous run left in the chat."""
        recorded = await self._store.take_all()
        for chat_id, message_id in recorded:
            try:
                await self._bot.delete_messages(
                    chat_id=chat_id, message_ids=message_id
                )
            except Exception as err:
                # Telegram refuses anything older than 48 hours, and the message
                # may simply be gone. Either way it is not worth a retry — the
                # ids have already been forgotten.
                self._log.debug(
                    'Could not remove the previous startup message %s in %s: %s',
                    message_id,
                    chat_id,
                    err,
                )

    async def announce(self) -> None:
        """Post the greeting, silently, and arrange for it to go away again."""
        recipients = self.recipients()
        if not recipients:
            self._log.info('No admin wants a startup message, not sending one')
            return

        name = html.escape((await self._bot.get_me()).first_name)
        for chat_id in recipients:
            text = t('start.startup', self._bot.language_for(chat_id), name=name)
            try:
                message = await self._bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    # Housekeeping, not news: it should be there when someone
                    # looks, not buzz in their pocket.
                    disable_notification=True,
                )
            except Exception:
                self._log.exception('Could not greet %s', chat_id)
                continue
            self._posted[chat_id] = (message.id, text)

        await self._record()
        self._schedule_removal()

    async def append(self, key: str, **params: Any) -> None:
        """Add a line to the message already on screen, in each reader's language.

        Silent by nature: editing a message never notifies.
        """
        for chat_id, (message_id, text) in list(self._posted.items()):
            line = t(key, self._bot.language_for(chat_id), **params)
            updated = f'{text}\n{line}'
            try:
                await self._bot.edit_message_text(
                    chat_id=chat_id, message_id=message_id, text=updated
                )
            except Exception as err:
                # The removal timer may already have taken it, or the message
                # may have been deleted by hand. Neither is worth a fuss.
                self._log.debug(
                    'Could not extend the startup message %s in %s: %s',
                    message_id,
                    chat_id,
                    err,
                )
                continue
            self._posted[chat_id] = (message_id, updated)

    async def _record(self) -> None:
        if not self._posted:
            return
        await self._store.save_all([
            (chat_id, message_id) for chat_id, (message_id, _) in self._posted.items()
        ])

    def _schedule_removal(self) -> None:
        if self._ttl <= 0 or not self._posted:
            return
        self._removal = asyncio.create_task(self._remove_after_ttl())

    async def _remove_after_ttl(self) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.sleep(self._ttl)
            await self.remove_now()

    async def remove_now(self) -> None:
        """Take the message down and forget it."""
        posted, self._posted = self._posted, {}
        for chat_id, (message_id, _) in posted.items():
            try:
                await self._bot.delete_messages(
                    chat_id=chat_id, message_ids=message_id
                )
            except Exception as err:
                self._log.debug(
                    'Could not remove the startup message %s in %s: %s',
                    message_id,
                    chat_id,
                    err,
                )
        await self._store.take_all()
