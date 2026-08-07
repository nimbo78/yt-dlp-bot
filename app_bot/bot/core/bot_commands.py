"""The command list Telegram shows in the menu next to the message box.

Telling people what exists is better done by the client than by a help text
they have to know to ask for. This publishes the list once at startup.

Everything here is best-effort on purpose. It is a cosmetic call over the
network against a Pyrogram API this repository cannot exercise in its tests —
Pyrogram will not install in the environment they run in — so a wrong guess
about the API, or a Telegram that is having a bad minute, costs the menu and
nothing else. The bot must still start.
"""

import logging
from typing import TYPE_CHECKING

from bot.core.i18n import t

if TYPE_CHECKING:
    from bot.bot.client import VideoBotClient

_log = logging.getLogger(__name__)

# Commands and the key describing each. Kept in the order somebody meets them.
PUBLIC: tuple[tuple[str, str], ...] = (
    ('help', 'command.help'),
    ('nocache', 'command.nocache'),
)
ADMIN: tuple[tuple[str, str], ...] = (
    ('listusers', 'command.listusers'),
    ('adduser', 'command.adduser'),
    ('deleteuser', 'command.deleteuser'),
    ('config', 'command.config'),
    ('reloadconfig', 'command.reloadconfig'),
    ('restartbot', 'command.restartbot'),
)


async def publish(bot: 'VideoBotClient') -> None:
    """Put the commands in the client's menu, for everyone and for admins.

    Admins get their own list in their own chat, so the six commands that would
    refuse everybody else are not offered to everybody else.
    """
    try:
        from pyrogram.types import (  # noqa: PLC0415
            BotCommand,
            BotCommandScopeChat,
            BotCommandScopeDefault,
        )
    except Exception:
        # A Pyrogram that names these differently. The menu is not worth a
        # failed start, and `/help` still says everything this would have.
        _log.exception('Could not import the bot command types; menu not published')
        return

    language = bot.conf.telegram.lang_code

    def described(pairs: tuple[tuple[str, str], ...], lang: str) -> list:
        return [BotCommand(name, t(key, lang)) for name, key in pairs]

    try:
        await bot.set_bot_commands(
            described(PUBLIC, language), scope=BotCommandScopeDefault()
        )
    except Exception:
        _log.exception('Could not publish the default command list')
        return

    for user in bot.admin_users.values():
        try:
            await bot.set_bot_commands(
                described(PUBLIC + ADMIN, user.lang_code or language),
                scope=BotCommandScopeChat(user.id),
            )
        except Exception:
            # Most likely this admin has never opened a chat with the bot, or
            # is configured as a group. Neither is worth a line above debug.
            _log.debug('Could not publish the admin command list to %s', user.id)
