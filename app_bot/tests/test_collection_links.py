"""Which links point at many things, and which at one.

The cost of the two mistakes is not symmetric, and the cases below are picked
to reflect that: a missed collection leaves the behaviour this fork has always
had, while a false positive puts a warning on an ordinary link somebody sends
every day. So the "one thing" cases are the ones worth being exhaustive about.
"""

from typing import ClassVar

import pytest

from bot.core.collection_links import carries_playlist, is_collection_link

COLLECTIONS = [
    # YouTube: playlists, channels in each of the four URL shapes it has
    # accumulated, and the tab pages hanging off a handle.
    'https://www.youtube.com/playlist?list=PLabc123',
    'https://youtube.com/playlist?list=PLabc123',
    'https://m.youtube.com/playlist?list=PLabc123',
    'https://music.youtube.com/playlist?list=OLAK5uy_abc',
    'https://www.youtube.com/channel/UCabc123def',
    'https://www.youtube.com/c/SomeChannel',
    'https://www.youtube.com/user/SomeOldChannel',
    'https://www.youtube.com/@someone',
    'https://www.youtube.com/@someone/videos',
    'https://www.youtube.com/@someone/shorts',
    'https://www.youtube.com/@someone/playlists',
    'https://www.youtube.com/feed/subscriptions',
    # SoundCloud: sets, artist pages and the tabs on them.
    'https://soundcloud.com/artist/sets/some-album',
    'https://soundcloud.com/artist/sets',
    'https://soundcloud.com/artist',
    'https://soundcloud.com/artist/tracks',
    'https://soundcloud.com/artist/albums',
    'https://soundcloud.com/artist/likes',
    'https://soundcloud.com/artist/reposts',
    'https://m.soundcloud.com/artist/sets/some-album',
    'https://soundcloud.com/discover',
    # Vimeo.
    'https://vimeo.com/album/123456',
    'https://vimeo.com/channels/staffpicks',
    'https://vimeo.com/showcase/9876543',
    'https://vimeo.com/groups/motion',
    # Bandcamp, where the artist gets a subdomain of their own.
    'https://artist.bandcamp.com/album/some-record',
    'https://artist.bandcamp.com/music',
    'https://artist.bandcamp.com',
    'https://artist.bandcamp.com/',
]

SINGLE_ITEMS = [
    # The shape you get from the address bar with a playlist playing. Ordinary
    # enough that warning about it would put a notice on most YouTube links.
    'https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLabc123',
    'https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLabc123&index=4',
    'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
    'https://youtu.be/dQw4w9WgXcQ',
    'https://youtu.be/dQw4w9WgXcQ?list=PLabc123',
    'https://www.youtube.com/shorts/abc123def',
    'https://www.youtube.com/live/abc123def',
    'https://music.youtube.com/watch?v=abc123&list=OLAK5uy_abc',
    'https://soundcloud.com/artist/some-track',
    'https://soundcloud.com/artist/some-track?in=other%2Fsets%2Falbum',
    'https://vimeo.com/123456789',
    'https://vimeo.com/123456789/abcdef',
    'https://artist.bandcamp.com/track/some-song',
    # Hosts with no rule of their own are left alone, whatever they look like.
    'https://x.com/someone/status/2083594794454921589',
    'https://www.instagram.com/reel/Cabc123/',
    'https://www.tiktok.com/@someone/video/7123456789',
    'https://example.com/whatever/deeply/nested/thing',
]


@pytest.mark.parametrize('url', COLLECTIONS)
def test_a_collection_is_recognised(url: str) -> None:
    assert is_collection_link(url) is True


@pytest.mark.parametrize('url', SINGLE_ITEMS)
def test_a_single_item_is_left_alone(url: str) -> None:
    assert is_collection_link(url) is False


class TestHostNormalisation:
    """The lookups are exact, so anything decorating the host has to come off."""

    @pytest.mark.parametrize(
        'url',
        [
            'https://WWW.YOUTUBE.COM/playlist?list=PLabc',
            'https://youtube.com:443/playlist?list=PLabc',
            'http://www.youtube.com/playlist?list=PLabc',
            '  https://www.youtube.com/playlist?list=PLabc  ',
        ],
    )
    def test_still_recognised(self, url: str) -> None:
        assert is_collection_link(url) is True

    def test_a_lookalike_host_is_not_youtube(self) -> None:
        """`youtube.com.evil.test` is not YouTube, and neither is a substring."""
        assert is_collection_link('https://youtube.com.evil.test/playlist') is False
        assert is_collection_link('https://notyoutube.com/playlist') is False


class TestRubbishIn:
    """This runs on every message, so nothing it is handed may raise."""

    @pytest.mark.parametrize(
        'url',
        [
            '',
            '   ',
            'not a url at all',
            'https://',
            'http://[',
            'javascript:alert(1)',
        ],
    )
    def test_answers_false_rather_than_raising(self, url: str) -> None:
        assert is_collection_link(url) is False

    def test_a_broken_port_still_answers(self) -> None:
        """`True` here, and that is fine: the URL will fail downstream for its
        own reasons, and the only thing riding on this answer is one line of
        text. What matters is that reading the host did not raise."""
        assert is_collection_link('https://youtube.com:notaport/playlist') is True


def test_a_bare_host_with_no_rule_is_not_a_collection() -> None:
    """The bandcamp rule treats an empty path as the artist page; that must
    not leak into hosts the module says nothing about."""
    assert is_collection_link('https://example.com') is False


class TestCarriesPlaylist:
    """A separate question from the warning, with a different answer.

    `watch?v=…&list=…` loses nothing — `--no-playlist` gives the video that was
    opened — so it earns no warning. But the playlist is named right there in
    the link, and whoever pasted it may want to pick from it instead.
    """

    ADDRESS_BAR_SHAPES: ClassVar[list[str]] = [
        'https://www.youtube.com/watch?v=BOSYJsbndFc&list=PLL3Uz25Wwloa_3RBqY',
        'https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLabc&index=4',
        'https://m.youtube.com/watch?v=abc&list=PLabc',
        'https://music.youtube.com/watch?v=abc&list=OLAK5uy_abc',
        'https://youtu.be/dQw4w9WgXcQ?list=PLabc',
        # An auto-generated mix. Not a playlist anybody made, but the rule that
        # excludes it is one more thing to be wrong about.
        'https://www.youtube.com/watch?v=abc&list=RDabc',
    ]

    @pytest.mark.parametrize('url', ADDRESS_BAR_SHAPES)
    def test_offered_but_not_warned_about(self, url: str) -> None:
        assert carries_playlist(url) is True
        assert is_collection_link(url) is False, 'this must not raise a warning'

    @pytest.mark.parametrize('url', COLLECTIONS)
    def test_everything_warned_about_is_also_offered(self, url: str) -> None:
        """The button is strictly the broader of the two."""
        assert carries_playlist(url) is True

    @pytest.mark.parametrize(
        'url',
        [
            'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
            'https://youtu.be/dQw4w9WgXcQ',
            'https://www.youtube.com/shorts/abc123def',
            # Empty parameter, which is what a trimmed link leaves behind.
            'https://www.youtube.com/watch?v=abc&list=',
            'https://soundcloud.com/artist/some-track',
            'https://x.com/someone/status/2083594794454921589',
            'https://example.com/watch?v=abc&list=PLabc',
        ],
    )
    def test_nothing_to_offer(self, url: str) -> None:
        assert carries_playlist(url) is False

    def test_rubbish_does_not_raise(self) -> None:
        for url in ('', '   ', 'not a url', 'http://['):
            assert carries_playlist(url) is False
