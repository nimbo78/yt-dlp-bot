"""Who the bot recognises, and by which of an update's several ids.

This is the decision behind the message filters. It used to be made once at
startup and frozen into `filters.user(...)`, which is why `/adduser` wrote the
config, said it had worked, and left the new user unable to send anything until
a restart. Kept as a plain set membership so that the rule can be checked
without Pyrogram.
"""

import pytest

from bot.core.access import is_known


class TestRecognised:
    def test_the_sender(self) -> None:
        assert is_known([111, None], {111, 222}) is True

    def test_the_chat(self) -> None:
        """A group is configured under its chat id while the person writing has
        one of their own, and either may be the one listed."""
        assert is_known([999, -100123], {-100123}) is True

    def test_neither(self) -> None:
        assert is_known([999, -100999], {111, -100123}) is False


class TestMissingIds:
    def test_no_sender(self) -> None:
        """A message from a channel has none."""
        assert is_known([None, -100123], {-100123}) is True

    def test_nothing_at_all(self) -> None:
        assert is_known([None, None], {111}) is False

    def test_none_is_never_a_match_even_against_an_empty_list(self) -> None:
        assert is_known([None], set()) is False


class TestNobodyConfigured:
    @pytest.mark.parametrize('known', [set(), [], {}])
    def test_an_empty_list_recognises_nobody(self, known) -> None:
        """Which is what makes registering the admin handlers unconditionally
        safe: with no admins, the filter simply never matches."""
        assert is_known([111, 222], known) is False


class TestItReadsWhatItIsGiven:
    def test_a_dict_is_read_by_its_keys(self) -> None:
        """The bot holds `allowed_users` as {id: UserSchema}, and it is passed
        straight in."""
        assert is_known([111], {111: object(), 222: object()}) is True

    def test_a_later_addition_is_seen(self) -> None:
        """The whole point: the set is read at call time, not captured."""
        known: dict[int, object] = {}
        assert is_known([111], known) is False
        known[111] = object()
        assert is_known([111], known) is True
