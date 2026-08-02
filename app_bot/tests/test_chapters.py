"""Chapter timestamps and how they are split across messages.

Telegram turns a timestamp into a seek link only when the whole thing is
intact, so a split that lands mid-line does not merely look untidy — it stops
being clickable.
"""

import pytest
from yt_shared.schemas.media import Chapter

from bot.core.chapters import format_chapters, format_timestamp, group_into_messages


@pytest.mark.parametrize(
    ('seconds', 'expected'),
    [
        (0, '0:00'),
        (7, '0:07'),
        (67, '1:07'),
        (600, '10:00'),
        (3599, '59:59'),
        (3600, '1:00:00'),
        (3725, '1:02:05'),
        (36000, '10:00:00'),
        (9.7, '0:09'),  # yt-dlp reports float seconds
    ],
)
def test_format_timestamp(seconds: float, expected: str) -> None:
    assert format_timestamp(seconds) == expected


def test_negative_positions_are_clamped() -> None:
    """Never emit "-1:-1", which Telegram would not link anyway."""
    assert format_timestamp(-5) == '0:00'


def test_format_chapters() -> None:
    chapters = [
        Chapter(start_time=0, title='Intro'),
        Chapter(start_time=90, title='The long middle'),
    ]
    assert format_chapters(chapters) == ['0:00 Intro', '1:30 The long middle']


def test_format_chapters_without_any() -> None:
    assert format_chapters([]) == []


class TestGroupIntoMessages:
    def test_everything_in_one_message_when_it_fits(self) -> None:
        lines = ['0:00 One', '1:00 Two', '2:00 Three']
        assert group_into_messages(lines, limit=100) == ['0:00 One\n1:00 Two\n2:00 Three']

    def test_no_lines_means_no_messages(self) -> None:
        assert group_into_messages([], limit=100) == []

    def test_splits_between_lines_only(self) -> None:
        lines = [f'{i}:00 Chapter number {i}' for i in range(20)]
        messages = group_into_messages(lines, limit=60)
        assert len(messages) > 1
        rejoined = '\n'.join(messages).split('\n')
        assert rejoined == lines, 'a line was broken or lost'

    def test_no_message_exceeds_the_limit(self) -> None:
        lines = [f'{i}:00 Chapter number {i}' for i in range(20)]
        limit = 60
        for message in group_into_messages(lines, limit=limit):
            assert len(message) <= limit

    def test_exact_fit_stays_in_one_message(self) -> None:
        """Two lines plus the newline joining them land exactly on the limit."""
        lines = ['0:00 aaaa', '1:00 bbbb']
        limit = len(lines[0]) + 1 + len(lines[1])
        assert group_into_messages(lines, limit=limit) == ['\n'.join(lines)]

    def test_one_character_over_splits(self) -> None:
        lines = ['0:00 aaaa', '1:00 bbbb']
        limit = len(lines[0]) + len(lines[1])  # no room for the newline
        assert group_into_messages(lines, limit=limit) == lines

    def test_a_line_longer_than_the_limit_is_kept_whole(self) -> None:
        """Truncating would destroy the timestamp; an oversized message is better."""
        lines = ['0:00 ' + 'x' * 100]
        assert group_into_messages(lines, limit=20) == lines
