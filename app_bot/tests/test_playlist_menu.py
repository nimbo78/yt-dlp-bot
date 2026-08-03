"""Paging a playlist into buttons, and staying inside Telegram's limits.

The limits are the point. Callback data over 64 bytes is rejected and the whole
keyboard fails to send, which is a failure you find by pressing nothing — the
menu simply never appears. So the budget is asserted against the widest
identifier the bot can actually generate, not against a convenient one.
"""

import datetime

import pytest

from bot.core.playlist_menu import (
    CALLBACK_DATA_LIMIT,
    MAX_SELECTED,
    PAGE_SIZE,
    PLAYLIST_ITEM_PREFIX,
    PLAYLIST_NOOP,
    PLAYLIST_PAGE_PREFIX,
    TICKED,
    UNTICKED,
    MenuEntry,
    MenuLabels,
    MenuPage,
    StoredPlaylist,
    build_menu,
    clamp_page,
    entries_to_rows,
    entry_label,
    find_entry,
    page_count,
    rows_to_entries,
    rows_to_selection,
    select_all,
    selected_entries,
    selection_to_rows,
    toggle,
    truncate_label,
)


def entries(count: int, start: int = 1) -> list[MenuEntry]:
    return [
        MenuEntry(index=i, title=f'Track {i}', url=f'https://example.com/{i}')
        for i in range(start, start + count)
    ]


LABELS = MenuLabels(
    cancel='Cancel', select_all='All', clear_all='None', next_step='Next ({count})'
)


def menu(
    entries_,
    url_id: str = 'c_1',
    page: int = 0,
    selected: frozenset[int] = frozenset(),
) -> MenuPage:
    """`build_menu` with the labels and cancel data its caller always supplies."""
    return build_menu(
        entries_,
        url_id,
        labels=LABELS,
        cancel_data=f'cancel:{url_id}',
        page=page,
        selected=selected,
    )


def item_rows(page) -> list:
    """Rows carrying an entry, i.e. everything above the navigation."""
    return [row for row in page.rows if row[0].data.startswith(PLAYLIST_ITEM_PREFIX)]


class TestPaging:
    def test_a_short_list_is_one_page(self) -> None:
        page = menu(entries(3), 'c_1')
        assert page.total_pages == 1
        assert len(item_rows(page)) == 3

    def test_a_full_page_is_still_one_page(self) -> None:
        assert menu(entries(PAGE_SIZE), 'c_1').total_pages == 1

    def test_one_more_than_a_page(self) -> None:
        page = menu(entries(PAGE_SIZE + 1), 'c_1')
        assert page.total_pages == 2
        assert len(item_rows(page)) == PAGE_SIZE

    def test_the_last_page_holds_the_remainder(self) -> None:
        page = menu(entries(PAGE_SIZE + 3), 'c_1', page=1)
        assert len(item_rows(page)) == 3
        assert [e.index for e in page.entries] == [
            PAGE_SIZE + 1,
            PAGE_SIZE + 2,
            PAGE_SIZE + 3,
        ]

    def test_no_navigation_row_when_everything_fits(self) -> None:
        page = menu(entries(3), 'c_1')
        assert not any(
            button.data == PLAYLIST_NOOP for row in page.rows for button in row
        )

    def test_navigation_appears_once_it_does_not(self) -> None:
        page = menu(entries(20), 'c_1')
        counters = [b for row in page.rows for b in row if b.data == PLAYLIST_NOOP]
        assert [b.label for b in counters] == ['1/3']

    def test_paging_wraps_rather_than_leaving_a_dead_button(self) -> None:
        """A back arrow on the first page that does nothing reads as broken."""
        first = menu(entries(20), 'c_1', page=0)
        nav = [b for row in first.rows for b in row if b.data.startswith(
            PLAYLIST_PAGE_PREFIX
        )]
        assert [b.data for b in nav] == ['pp:c_1:2', 'pp:c_1:1']

        last = menu(entries(20), 'c_1', page=2)
        nav = [b for row in last.rows for b in row if b.data.startswith(
            PLAYLIST_PAGE_PREFIX
        )]
        assert [b.data for b in nav] == ['pp:c_1:1', 'pp:c_1:0']

    def test_every_page_ends_with_cancel(self) -> None:
        for page_number in range(3):
            page = menu(entries(20), 'c_1', page=page_number)
            assert page.rows[-1][0].data == 'cancel:c_1'


class TestSelection:
    def test_nothing_is_ticked_to_begin_with(self) -> None:
        page = menu(entries(3))
        assert all(b.label.startswith(UNTICKED) for row in item_rows(page) for b in row)

    def test_a_ticked_entry_is_drawn_ticked(self) -> None:
        page = menu(entries(3), selected=frozenset({2}))
        labels = [row[0].label for row in item_rows(page)]
        assert labels[0].startswith(UNTICKED)
        assert labels[1].startswith(TICKED)

    def test_the_next_button_appears_only_once_something_is_ticked(self) -> None:
        """An always-present button that answers "nothing selected" is a button
        that lies about being available."""
        assert not any(
            b.data.startswith('pn:') for row in menu(entries(3)).rows for b in row
        )
        page = menu(entries(3), selected=frozenset({1}))
        nexts = [b for row in page.rows for b in row if b.data.startswith('pn:')]
        assert [b.label for b in nexts] == ['Next (1)']

    def test_the_count_on_the_next_button_is_the_whole_selection(self) -> None:
        """Not just this page's share of it."""
        page = menu(entries(20), selected=frozenset({1, 9, 17}), page=0)
        nexts = [b for row in page.rows for b in row if b.data.startswith('pn:')]
        assert nexts[0].label == 'Next (3)'

    def test_bulk_buttons_are_offered(self) -> None:
        page = menu(entries(3))
        bulk = [b for row in page.rows for b in row if b.data.startswith('pa:')]
        assert [b.data for b in bulk] == ['pa:c_1:1', 'pa:c_1:0']

    def test_no_bulk_buttons_with_nothing_to_bulk(self) -> None:
        page = menu([])
        assert not any(b.data.startswith('pa:') for row in page.rows for b in row)


class TestToggle:
    def test_ticking_and_unticking(self) -> None:
        assert toggle(frozenset(), 3) == frozenset({3})
        assert toggle(frozenset({3}), 3) == frozenset()

    def test_others_are_left_alone(self) -> None:
        assert toggle(frozenset({1, 2}), 3) == frozenset({1, 2, 3})

    def test_the_cap_refuses_by_returning_the_set_unchanged(self) -> None:
        """Which is the only way the caller can tell a refusal from a no-op,
        and therefore say so instead of dropping the press in silence."""
        full = frozenset(range(1, MAX_SELECTED + 1))
        assert toggle(full, MAX_SELECTED + 1) == full

    def test_unticking_still_works_at_the_cap(self) -> None:
        full = frozenset(range(1, MAX_SELECTED + 1))
        assert toggle(full, 1) == full - {1}


class TestSelectAll:
    def test_everything_when_it_fits(self) -> None:
        assert select_all(entries(5)) == frozenset({1, 2, 3, 4, 5})

    def test_truncated_at_the_cap_rather_than_refused(self) -> None:
        """Somebody pressing this on a 100-entry playlist wants as much as they
        can have; the header says how many that was."""
        chosen = select_all(entries(100))
        assert len(chosen) == MAX_SELECTED
        assert chosen == frozenset(range(1, MAX_SELECTED + 1))

    def test_an_empty_playlist(self) -> None:
        assert select_all([]) == frozenset()


class TestSelectedEntries:
    def test_in_playlist_order_not_set_order(self) -> None:
        """These are queued one after another, and a set has no order."""
        chosen = selected_entries(entries(10), frozenset({7, 2, 5}))
        assert [e.index for e in chosen] == [2, 5, 7]

    def test_indices_that_are_not_there_are_ignored(self) -> None:
        assert selected_entries(entries(3), frozenset({99})) == []

    def test_the_numbering_follows_the_source(self) -> None:
        sparse = [
            MenuEntry(index=1, title='a', url='u1'),
            MenuEntry(index=4, title='b', url='u4'),
        ]
        assert [e.index for e in selected_entries(sparse, frozenset({4}))] == [4]


class TestSelectionStorage:
    def test_a_round_trip(self) -> None:
        assert rows_to_selection(selection_to_rows(frozenset({3, 1, 2}))) == frozenset(
            {1, 2, 3}
        )

    def test_stored_in_a_stable_order(self) -> None:
        """So a rewrite does not churn the row for no reason."""
        assert selection_to_rows(frozenset({5, 1, 3})) == [1, 3, 5]

    def test_a_column_holding_something_else(self) -> None:
        for rubbish in (None, 'nonsense', 42, {}):
            assert rows_to_selection(rubbish) == frozenset()

    def test_entries_that_are_not_numbers_are_skipped(self) -> None:
        assert rows_to_selection([1, 'two', None, 3]) == frozenset({1, 3})


class TestPageCountAndClamping:
    @pytest.mark.parametrize(
        ('count', 'expected'),
        [(0, 1), (1, 1), (PAGE_SIZE, 1), (PAGE_SIZE + 1, 2), (PAGE_SIZE * 3, 3)],
    )
    def test_page_count(self, count: int, expected: int) -> None:
        assert page_count(count) == expected

    def test_an_empty_list_is_one_empty_page(self) -> None:
        page = menu([], 'c_1')
        assert page.total_pages == 1
        assert item_rows(page) == []
        assert page.rows[-1][0].data == 'cancel:c_1'

    def test_a_page_past_the_end_lands_on_the_last(self) -> None:
        """The menu may have been re-read shorter since the button was drawn."""
        assert clamp_page(99, 20) == 2
        assert menu(entries(20), 'c_1', page=99).number == 2

    def test_a_negative_page_lands_on_the_first(self) -> None:
        assert clamp_page(-5, 20) == 0
        assert menu(entries(20), 'c_1', page=-5).number == 0


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
        label = entry_label(MenuEntry(index=7, title='Thing', url='u'))
        assert label.endswith('7. Thing')
        assert label.startswith(UNTICKED)

    def test_a_ticked_entry_says_so(self) -> None:
        entry = MenuEntry(index=1, title='Thing', url='u')
        assert entry_label(entry, selected=True).startswith(TICKED)


class TestCallbackDataBudget:
    """Over 64 bytes and Telegram rejects the whole keyboard, silently."""

    @staticmethod
    def widest_url_id() -> str:
        # A supergroup id is the longest chat id Telegram issues, and message
        # ids run into the millions on a busy chat.
        return f'{-1002123456789}_{999999999}'

    def test_every_button_fits(self) -> None:
        url_id = self.widest_url_id()
        page = menu(entries(100), url_id, page=11)
        for row in page.rows:
            for button in row:
                assert len(button.data.encode()) <= CALLBACK_DATA_LIMIT, button.data

    def test_with_room_to_spare(self) -> None:
        """Not just under the limit — under it by enough that a longer id later
        does not quietly break this."""
        url_id = self.widest_url_id()
        page = menu(entries(100), url_id, page=11)
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
    def test_it_carries_its_age_for_the_policy_layer_to_judge(self) -> None:
        """The store does not decide staleness; `bot.core.playlists` does."""
        when = datetime.datetime(2026, 8, 2, 23, 0, tzinfo=datetime.UTC)
        stored = StoredPlaylist(entries=entries(3), added_at=when)
        assert stored.added_at == when
        assert len(stored.entries) == 3
