"""Pyrogram filters that read the current configuration rather than a snapshot.

`filters.user(...)` takes a list and freezes it. Everything here asks the bot
for its live dictionaries instead, so `/adduser` and `/config set` take effect
on the next message rather than on the next restart.
"""

from typing import TYPE_CHECKING

from pyrogram import filters
from pyrogram.types import CallbackQuery, Message

from bot.core.access import is_known

if TYPE_CHECKING:
    from pyrogram.filters import Filter

    from bot.bot.client import VideoBotClient


def _candidate_ids(update: Message | CallbackQuery) -> list[int | None]:
    """Collect the ids an update could be recognised by: sender, and chat."""
    sender = update.from_user.id if update.from_user else None
    if isinstance(update, CallbackQuery):
        chat = update.message.chat.id if update.message else None
    else:
        chat = update.chat.id if update.chat else None
    return [sender, chat]


def allowed(bot: 'VideoBotClient') -> 'Filter':
    """Anyone in `allowed_users`, by their own id or by the chat they write in.

    The same rule the frozen `filters.user(ids) | filters.chat(ids)` had, asked
    against the dictionary the bot is holding right now.
    """

    async def check(_: 'Filter', __: object, update: Message | CallbackQuery) -> bool:
        return is_known(_candidate_ids(update), bot.allowed_users)

    return filters.create(check, name='AllowedUser')


def admin(bot: 'VideoBotClient') -> 'Filter':
    """Match an admin, by their own id only.

    Deliberately narrower than `allowed`: the chat is not consulted, so being
    in a group that happens to be configured as an admin does not make everyone
    in it one. That was the old behaviour and it is the right one.
    """

    async def check(_: 'Filter', __: object, update: Message | CallbackQuery) -> bool:
        sender = update.from_user.id if update.from_user else None
        return is_known([sender], bot.admin_users)

    return filters.create(check, name='AdminUser')
