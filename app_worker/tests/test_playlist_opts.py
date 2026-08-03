"""What enumeration must override in the options it inherits.

This exists because of a bug that shipped and was caught only by reading
yt-dlp's source: the download defaults carry `--playlist-items 1:1`, and in
yt-dlp that setting wins over `--playlist-end`. `PlaylistEntries` consults the
start/end pair only when `playlist_items` is unset, so inheriting it capped
every enumeration at one entry — and said nothing, because a menu with a single
row looks like a playlist with a single item.

Dict in, dict out, so none of this needs yt-dlp installed to check.
"""

from worker.core.playlist import apply_flat_overrides

# What `cli_to_api` returns for the shipped DEFAULT_YTDL_OPTS, in the parts
# that matter here.
DOWNLOAD_DEFAULTS = {
    'noplaylist': True,
    'playlist_items': '1:1',
    'outtmpl': {'default': '%(title).200B.%(ext)s'},
    'cookiefile': '/app/cookies/_cookies.txt',
    'ratelimit': 500000,
    'verbose': True,
}


class TestTheCapThatWouldHaveGoneUnnoticed:
    def test_the_one_item_cap_is_lifted(self) -> None:
        opts = apply_flat_overrides(
            DOWNLOAD_DEFAULTS, 100, cookies_last_resort=False
        )
        assert opts['playlist_items'] == '1:100'

    def test_no_playlist_is_lifted(self) -> None:
        """`--no-playlist` asks for the one video a playlist link points at,
        which is the exact opposite of the question being asked."""
        opts = apply_flat_overrides(
            DOWNLOAD_DEFAULTS, 100, cookies_last_resort=False
        )
        assert opts['noplaylist'] is False

    def test_the_limit_is_honoured(self) -> None:
        opts = apply_flat_overrides(DOWNLOAD_DEFAULTS, 25, cookies_last_resort=False)
        assert opts['playlist_items'] == '1:25'


class TestWhatIsKept:
    def test_the_deployment_s_own_settings_survive(self) -> None:
        """A proxy or a rate limit set in `ytdl_opts/user.py` has to apply
        here too, or a host that downloads fails to list for no visible reason.
        """
        opts = apply_flat_overrides(
            DOWNLOAD_DEFAULTS, 100, cookies_last_resort=False
        )
        assert opts['ratelimit'] == 500000
        assert opts['verbose'] is True

    def test_cookies_are_kept_where_the_host_wants_them(self) -> None:
        opts = apply_flat_overrides(
            DOWNLOAD_DEFAULTS, 100, cookies_last_resort=False
        )
        assert opts['cookiefile'] == '/app/cookies/_cookies.txt'

    def test_cookies_are_dropped_where_the_host_prefers_anonymity(self) -> None:
        """YouTube sets this because an authenticated session from a server
        address is what draws the bot check."""
        opts = apply_flat_overrides(DOWNLOAD_DEFAULTS, 100, cookies_last_resort=True)
        assert 'cookiefile' not in opts

    def test_the_output_template_goes(self) -> None:
        opts = apply_flat_overrides(
            DOWNLOAD_DEFAULTS, 100, cookies_last_resort=False
        )
        assert 'outtmpl' not in opts


class TestItDoesNotMutateItsInput:
    def test_the_caller_s_dict_is_left_alone(self) -> None:
        original = dict(DOWNLOAD_DEFAULTS)
        apply_flat_overrides(DOWNLOAD_DEFAULTS, 100, cookies_last_resort=True)
        assert original == DOWNLOAD_DEFAULTS

    def test_options_absent_from_the_input_are_not_invented(self) -> None:
        opts = apply_flat_overrides({}, 10, cookies_last_resort=True)
        assert opts == {'noplaylist': False, 'playlist_items': '1:10'}
