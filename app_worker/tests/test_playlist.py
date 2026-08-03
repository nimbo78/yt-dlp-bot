"""Reading a flat extraction, including all the ways one is untidy.

The shapes below are what yt-dlp really emits: `None` where an item could not
be read at all, a placeholder title where it could be listed but not opened, a
missing title on a perfectly playable item, and a bare id where an extractor
does not give a full address. Each of those has a different right answer, and
getting them wrong shows up as a button that does nothing.
"""

from yt_shared.schemas.playlist import MAX_PLAYLIST_ENTRIES

from worker.core.playlist import entries_from_info


def entry(url: str = 'https://example.com/v', title: str = 'A track') -> dict:
    return {'_type': 'url', 'url': url, 'title': title}


class TestOrdinaryPlaylist:
    def test_entries_come_back_in_order(self) -> None:
        info = {
            'title': 'An album',
            'entries': [entry(title='One'), entry(title='Two'), entry(title='Three')],
        }
        playlist = entries_from_info(info)
        assert playlist.title == 'An album'
        assert [e.title for e in playlist.entries] == ['One', 'Two', 'Three']
        assert [e.index for e in playlist.entries] == [1, 2, 3]
        assert playlist.total == 3
        assert not playlist.is_truncated

    def test_the_url_is_carried_through(self) -> None:
        info = {'entries': [entry(url='https://example.com/watch?v=abc')]}
        assert entries_from_info(info).entries[0].url == (
            'https://example.com/watch?v=abc'
        )

    def test_a_playlist_with_no_title_still_reads(self) -> None:
        assert entries_from_info({'entries': [entry()]}).title == 'Playlist'
        assert entries_from_info({'title': '   ', 'entries': []}).title == 'Playlist'


class TestNotAPlaylist:
    def test_a_single_video_has_no_entries(self) -> None:
        """`extract_flat` on one video returns a plain result. Not an error."""
        playlist = entries_from_info({'title': 'Just a video', 'id': 'abc'})
        assert playlist.entries == []
        assert playlist.total == 0
        assert not playlist.is_truncated

    def test_entries_of_the_wrong_shape(self) -> None:
        assert entries_from_info({'entries': None}).entries == []
        assert entries_from_info({'entries': 'nonsense'}).entries == []

    def test_an_empty_playlist(self) -> None:
        assert entries_from_info({'entries': []}).entries == []


class TestUnusableEntries:
    def test_a_none_entry_is_skipped(self) -> None:
        """yt-dlp puts None here when it could not read the item at all."""
        info = {'entries': [entry(title='One'), None, entry(title='Three')]}
        playlist = entries_from_info(info)
        assert [e.title for e in playlist.entries] == ['One', 'Three']

    def test_the_count_still_reports_what_the_source_claimed(self) -> None:
        """Two of three, and the answer must not read as two of two."""
        info = {'entries': [entry(), None, entry()]}
        playlist = entries_from_info(info)
        assert len(playlist.entries) == 2
        assert playlist.total == 3
        assert playlist.is_truncated

    def test_a_placeholder_title_means_it_cannot_be_opened(self) -> None:
        for placeholder in ('[Deleted video]', '[Private video]', '[unavailable]'):
            info = {'entries': [entry(title=placeholder), entry(title='Real')]}
            titles = [e.title for e in entries_from_info(info).entries]
            assert titles == ['Real'], placeholder

    def test_an_entry_with_no_usable_url_is_skipped(self) -> None:
        """A bare id cannot be resolved without knowing the extractor, so a
        button built on it would simply fail."""
        info = {
            'entries': [
                {'id': 'abc123', 'title': 'Only an id'},
                {'url': 'abc123', 'title': 'A url that is an id'},
                {'url': None, 'title': 'Nothing at all'},
                entry(title='Fine'),
            ]
        }
        assert [e.title for e in entries_from_info(info).entries] == ['Fine']

    def test_the_url_may_live_under_another_key(self) -> None:
        info = {
            'entries': [
                {'webpage_url': 'https://example.com/a', 'title': 'A'},
                {'original_url': 'https://example.com/b', 'title': 'B'},
            ]
        }
        assert [e.url for e in entries_from_info(info).entries] == [
            'https://example.com/a',
            'https://example.com/b',
        ]

    def test_a_missing_title_is_not_a_reason_to_drop_a_playable_item(self) -> None:
        info = {'entries': [{'url': 'https://example.com/a'}, entry(title='  ')]}
        assert [e.title for e in entries_from_info(info).entries] == ['#1', '#2']

    def test_the_index_follows_the_source_not_the_survivors(self) -> None:
        """Position 3 in the playlist stays 3, even with one dropped before it."""
        info = {'entries': [entry(title='One'), None, entry(title='Three')]}
        assert [e.index for e in entries_from_info(info).entries] == [1, 3]


class TestLimit:
    def test_a_long_playlist_is_cut(self) -> None:
        info = {'entries': [entry(title=f'#{i}') for i in range(250)]}
        playlist = entries_from_info(info)
        assert len(playlist.entries) == MAX_PLAYLIST_ENTRIES
        assert playlist.total == 250
        assert playlist.is_truncated

    def test_the_limit_can_be_lowered(self) -> None:
        info = {'entries': [entry() for _ in range(10)]}
        assert len(entries_from_info(info, limit=3).entries) == 3

    def test_the_limit_counts_usable_entries_not_positions(self) -> None:
        """Otherwise a run of dead items eats the whole allowance and the
        answer comes back nearly empty for no visible reason."""
        info = {'entries': [None, None, None, entry(title='A'), entry(title='B')]}
        assert [e.title for e in entries_from_info(info, limit=2).entries] == [
            'A',
            'B',
        ]
