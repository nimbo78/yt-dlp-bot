"""The help text, in every language, staying inside what Telegram will accept.

Both limits here are all-or-nothing. A message over 4096 characters is refused,
and so is one with an unbalanced tag under HTML parse mode — in either case
`/help` produces nothing at all rather than something slightly wrong, which is
exactly the failure a translation is most likely to introduce.
"""

import re

import pytest

from bot.core.i18n import LANGUAGES, t

# Telegram's own ceiling for a text message.
MESSAGE_LIMIT = 4096

TAG = re.compile(r'<(/?)(\w+)[^>]*>')


def tags(text: str) -> list[tuple[str, str]]:
    return [(closing, name) for closing, name in TAG.findall(text)]


def help_text(language: str) -> str:
    """Build what an admin sees: both halves, joined as the handler joins them."""
    return f'{t("help.body", language)}\n\n{t("help.admin", language)}'


@pytest.mark.parametrize('language', LANGUAGES)
class TestEveryLanguage:
    def test_it_fits_in_one_message(self, language: str) -> None:
        assert len(help_text(language)) < MESSAGE_LIMIT

    def test_the_tags_are_balanced(self, language: str) -> None:
        """An unclosed <b> makes Telegram refuse the whole message."""
        stack: list[str] = []
        for closing, name in tags(help_text(language)):
            if closing:
                assert stack and stack[-1] == name, (language, name, stack)
                stack.pop()
            else:
                stack.append(name)
        assert stack == [], (language, stack)

    def test_the_angle_brackets_around_placeholders_are_escaped(
        self, language: str
    ) -> None:
        """`<link>` in the usage lines has to be written `&lt;link&gt;`, or
        Telegram reads it as a tag it does not know and rejects the message."""
        for closing, name in tags(help_text(language)):
            assert name in {'b', 'code', 'i', 'u', 's', 'a', 'pre'}, (
                language, closing, name,
            )

    def test_it_says_something(self, language: str) -> None:
        assert len(t('help.body', language)) > 200
        assert len(t('help.admin', language)) > 200


class TestBothHalvesExist:
    def test_the_two_are_separate_keys(self) -> None:
        """The admin half is appended only for admins, so it has to be its own
        key rather than a paragraph inside the other."""
        assert t('help.body', 'en') != t('help.admin', 'en')
        assert '/adduser' not in t('help.body', 'en')
        assert '/adduser' in t('help.admin', 'en')

    def test_the_commands_named_are_the_ones_that_exist(self) -> None:
        """A help text listing a command nobody registered is worse than none."""
        admin = t('help.admin', 'en')
        for command in (
            '/adduser', '/deleteuser', '/listusers',
            '/config', '/reloadconfig', '/restartbot',
        ):
            assert command in admin, command
        body = t('help.body', 'en')
        assert '/nocache' in body
        assert '/help' in body


class TestCommandMenu:
    """The descriptions Telegram shows next to each command in the menu."""

    ALL = (
        'help', 'nocache', 'listusers', 'adduser',
        'deleteuser', 'config', 'reloadconfig', 'restartbot',
    )

    @pytest.mark.parametrize('language', LANGUAGES)
    def test_every_command_is_described_in_every_language(
        self, language: str
    ) -> None:
        for command in self.ALL:
            described = t(f'command.{command}', language)
            assert described, (language, command)
            # Telegram's own ceiling for a command description.
            assert len(described) <= 256, (language, command, len(described))

    def test_the_lists_name_only_commands_that_exist(self) -> None:
        """A menu entry for a command nobody registered does nothing when
        tapped, which is the worst way to learn a list is stale."""
        from bot.core.bot_commands import ADMIN, PUBLIC

        named = {name for name, _ in PUBLIC + ADMIN}
        assert named == set(self.ALL)

    def test_no_command_is_offered_to_everyone_and_to_admins_twice(self) -> None:
        from bot.core.bot_commands import ADMIN, PUBLIC

        assert not {n for n, _ in PUBLIC} & {n for n, _ in ADMIN}

    def test_the_admin_list_matches_what_the_help_text_claims(self) -> None:
        from bot.core.bot_commands import ADMIN

        admin_help = t('help.admin', 'en')
        for name, _ in ADMIN:
            assert f'/{name}' in admin_help, name
