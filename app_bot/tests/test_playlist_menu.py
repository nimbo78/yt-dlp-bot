"""Paging a playlist into buttons, and staying inside Telegram's limits.

The limits are the point. Callback data over 64 bytes is rejected and the whole
keyboard fails to send, which is a failure you find by pressing nothing — the
menu simply never appears. So the budget is asserted against the widest
identifier the bot can actually generate, not against a convenient one.
"""

import pytest

from bot.core.playlist_menu import (
    CALLBACK_DATA_LIMIT,
    PAGE_SIZE,
    PLAYLIST_ITEM_PREFIX,
    PLAYLIST_NOOP,
    PLAYLIST_PAGE_PREFIX,
    MenuEntry,
    StoredPlaylist,
    build_menu,
    clamp_page,
    entries_to_rows,
    entry_label,
    find_entry,
    page_count,
    rows_to_entries,
    truncate_label,
)


def entries(count: int, start: int = 1) -> list[MenuEntry]:
    return [
        MenuEntry(index=i, title=f'Track {i}', url=f'https://example.com/{i}')
        for i in range(start, start + count)
    ]


def item_rows(page) -> list:
    """Rows carrying an entry, i.e. everything above the navigation."""
    return [row for row in page.rows if row[0].data.startswith(PLAYLIST_ITEM_PREFIX)]


class TestPaging:
    def test_a_short_list_is_one_page(self) -> None:
        page = build_menu(entries(3), 'c_1')
        assert page.total_pages == 1
        assert len(item_rows(page)) == 3

    def test_a_full_page_is_still_one_page(self) -> None:
        assert build_menu(entries(PAGE_SIZE), 'c_1').total_pages == 1

    def test_one_more_than_a_page(self) -> None:
        page = build_menu(entries(PAGE_SIZE + 1), 'c_1')
        assert page.total_pages == 2
        assert len(item_rows(page)) == PAGE_SIZE

    def test_the_last_page_holds_the_remainder(self) -> None:
        page = build_menu(entries(PAGE_SIZE + 3), 'c_1', page=1)
        assert len(item_rows(page)) == 3
        assert [e.index for e in page.entries] == [
            PAGE_SIZE + 1,
            PAGE_SIZE + 2,
            PAGE_SIZE + 3,
        ]

    def test_no_navigation_row_when_everything_fits(self) -> None:
        page = build_menu(entries(3), 'c_1')
        assert not any(
            button.data == PLAYLIST_NOOP for row in page.rows for button in row
        )

    def test_navigation_appears_once_it_does_not(self) -> None:
        page = build_menu(entries(20), 'c_1')
        counters = [b for row in page.rows for b in row if b.data == PLAYLIST_NOOP]
        assert [b.label for b in counters] == ['1/3']

    def test_paging_wraps_rather_than_leaving_a_dead_button(self) -> None:
        """A back arrow on the first page that does nothing reads as broken."""
        first = build_menu(entries(20), 'c_1', page=0)
        nav = [b for row in first.rows for b in row if b.data.startswith(
            PLAYLIST_PAGE_PREFIX
        )]
        assert [b.data for b in nav] == ['pp:c_1:2', 'pp:c_1:1']

        last = build_menu(entries(20), 'c_1', page=2)
        nav = [b for row in last.rows for b in row if b.data.startswith(
            PLAYLIST_PAGE_PREFIX
        )]
        assert [b.data for b in nav] == ['pp:c_1:1', 'pp:c_1:0']

    def test_every_page_ends_with_cancel(self) -> None:
        for page_number in range(3):
            page = build_menu(entries(20), 'c_1', page=page_number)
            assert page.rows[-1][0].data == 'cancel:c_1'


class TestPageCountAndClamping:
    @pytest.mark.parametrize(
        ('count', 'expected'),
        [(0, 1), (1, 1), (PAGE_SIZE, 1), (PAGE_SIZE + 1, 2), (PAGE_SIZE * 3, 3)],
    )
    def test_page_count(self, count: int, expected: int) -> None:
        assert page_count(count) == expected

    def test_an_empty_list_is_one_empty_page(self) -> None:
        page = build_menu([], 'c_1')
        assert page.total_pages == 1
        assert item_rows(page) == []
        assert page.rows[-1][0].data == 'cancel:c_1'

    def test_a_page_past_the_end_lands_on_the_last(self) -> None:
        """The menu may have been re-read shorter since the button was drawn."""
        assert clamp_page(99, 20) == 2
        assert build_menu(entries(20), 'c_1', page=99).number == 2

    def test_a_negative_page_lands_on_the_first(self) -> None:
        assert clamp_page(-5, 20) == 0
        assert build_menu(entries(20), 'c_1', page=-5).number == 0


class TestLabels:
    def test_a_short_title_is_left_alone(self) -> None:
        assert truncate_label('Short') == 'Short'

    def test_a_long_one_is_cut_with_an_ellipsis(self) -> None:
        label = truncate_label('x' * 100, limit=10)
        assert len(label) == 10
        assert label.endswith('…')

    def test_exactly_at_the_limit_is_not_cut(self) -> None:
        assert truncate_label('x' * 10, limit=10) == 'x' * 10

    def test_whitespace_is_collapsed(self) -> None:
        """Titles arrive with newlines in them often enough to matter."""
        assert truncate_label('a\n\nb   c') == 'a b c'

    def test_no_trailing_space_before_the_ellipsis(self) -> None:
        assert truncate_label('word ' + 'x' * 50, limit=6) == 'word…'

    def test_the_label_carries_the_source_number(self) -> None:
        assert entry_label(MenuEntry(index=7, title='Thing', url='u')) == '7. Thing'


class TestCallbackDataBudget:
    """Over 64 bytes and Telegram rejects the whole keyboard, silently."""

    @staticmethod
    def widest_url_id() -> str:
        # A supergroup id is the longest chat id Telegram issues, and message
        # ids run into the millions on a busy chat.
        return f'{-1002123456789}_{999999999}'

    def test_every_button_fits(self) -> None:
        url_id = self.widest_url_id()
        page = build_menu(entries(100), url_id, page=11)
        for row in page.rows:
            for button in row:
                assert len(button.data.encode()) <= CALLBACK_DATA_LIMIT, button.data

    def test_with_room_to_spare(self) -> None:
        """Not just under the limit — under it by enough that a longer id later
        does not quietly break this."""
        url_id = self.widest_url_id()
        page = build_menu(entries(100), url_id, page=11)
        longest = max(len(b.data.encode()) for row in page.rows for b in row)
        assert longest <= CALLBACK_DATA_LIMIT // 2, longest


class TestFindEntry:
    def test_by_the_number_on_the_button(self) -> None:
        found = find_entry(entries(5), 3)
        assert found is not None
        assert found.title == 'Track 3'

    def test_the_number_is_the_source_position_not_the_list_position(self) -> None:
        """Unusable entries were dropped when the playlist was read, and the
        numbering did not close up — so index 3 may be the second one here."""
        sparse = [
            MenuEntry(index=1, title='First', url='u1'),
            MenuEntry(index=3, title='Third', url='u3'),
        ]
        found = find_entry(sparse, 3)
        assert found is not None
        assert found.title == 'Third'
        assert find_entry(sparse, 2) is None

    def test_an_unknown_number(self) -> None:
        assert find_entry(entries(5), 99) is None
        assert find_entry([], 1) is None


class TestStorageRoundTrip:
    """The entries live in a JSON column, which can hold anything at all."""

    def test_a_round_trip_keeps_everything(self) -> None:
        original = entries(3)
        assert rows_to_entries(entries_to_rows(original)) == original

    def test_a_column_holding_something_else_entirely(self) -> None:
        for rubbish in (None, {}, 'a string', 42):
            assert rows_to_entries(rubbish) == []

    def test_a_row_written_by_an_older_build_is_skipped(self) -> None:
        rows = [
            {'index': 1, 'title': 'Kept', 'url': 'u1'},
            {'index': 2, 'title': 'No url'},
            {'title': 'No index', 'url': 'u3'},
            'not a row at all',
            {'index': 'not a number', 'title': 't', 'url': 'u'},
            {'index': 6, 'title': 'Also kept', 'url': 'u6'},
        ]
        assert [e.title for e in rows_to_entries(rows)] == ['Kept', 'Also kept']

    def test_one_bad_row_does_not_lose_the_menu(self) -> None:
        rows = [*entries_to_rows(entries(5)), {'broken': True}]
        assert len(rows_to_entries(rows)) == 5


class TestStoredPlaylist:
    def test_truncation_is_reported(self) -> None:
        full = StoredPlaylist(title='A', entries=entries(10), total=10)
        cut = StoredPlaylist(title='A', entries=entries(10), total=250)
        assert not full.is_truncated
        assert cut.is_truncated
