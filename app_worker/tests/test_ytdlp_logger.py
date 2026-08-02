"""Collecting the reason a download failed out of yt-dlp's own output.

yt-dlp runs with ``ignoreerrors``, so an extractor failure never raises — the
only trace of it is what the logger was told. Picking the wrong line here means
the user is shown a stack frame instead of "Account suspended", which has
happened twice.
"""

import logging

import pytest

from worker.core.ytdlp_logger import YtdlpLogger


@pytest.fixture
def ytdlp_log() -> YtdlpLogger:
    return YtdlpLogger(logging.getLogger('test'))


class TestLastError:
    def test_nothing_reported(self, ytdlp_log: YtdlpLogger) -> None:
        assert ytdlp_log.last_error() is None

    def test_a_single_error(self, ytdlp_log: YtdlpLogger) -> None:
        ytdlp_log.error('ERROR: [twitter] 123: Suspended')
        assert ytdlp_log.last_error() == '[twitter] 123: Suspended'

    def test_the_prefix_is_stripped(self, ytdlp_log: YtdlpLogger) -> None:
        ytdlp_log.error('ERROR: Unsupported URL: https://example.com')
        assert ytdlp_log.last_error() == 'Unsupported URL: https://example.com'

    def test_only_the_first_line_is_kept(self, ytdlp_log: YtdlpLogger) -> None:
        ytdlp_log.error('ERROR: Private video\nSign in if you have access')
        assert ytdlp_log.last_error() == 'Private video'

    def test_the_most_recent_error_wins(self, ytdlp_log: YtdlpLogger) -> None:
        ytdlp_log.error('ERROR: first')
        ytdlp_log.error('ERROR: second')
        assert ytdlp_log.last_error() == 'second'

    def test_a_prefixed_reason_beats_an_unprefixed_traceback(
        self, ytdlp_log: YtdlpLogger
    ) -> None:
        """In verbose mode the reason and the traceback arrive as two calls."""
        ytdlp_log.error('ERROR: [twitter] 123: Suspended')
        ytdlp_log.error('Traceback (most recent call last):\n  File "x.py", line 1')
        assert ytdlp_log.last_error() == '[twitter] 123: Suspended'

    def test_bare_frames_without_a_traceback_header_are_rejected(
        self, ytdlp_log: YtdlpLogger
    ) -> None:
        """An expected failure has no header — it starts at the first frame."""
        ytdlp_log.error('  File "yt_dlp/extractor/common.py", line 1, in _real_extract')
        assert ytdlp_log.last_error() is None

    def test_falls_back_to_an_unprefixed_message(self, ytdlp_log: YtdlpLogger) -> None:
        """Not everything yt-dlp reports carries the prefix; better than nothing."""
        ytdlp_log.error('something went wrong')
        assert ytdlp_log.last_error() == 'something went wrong'

    def test_blank_messages_are_skipped(self, ytdlp_log: YtdlpLogger) -> None:
        ytdlp_log.error('ERROR: [twitter] 123: Suspended')
        ytdlp_log.error('ERROR: ')
        assert ytdlp_log.last_error() == '[twitter] 123: Suspended'

    @pytest.mark.parametrize('msg', ['', 'ERROR: ', '\n', '   '])
    def test_an_empty_message_yields_no_reason(
        self, ytdlp_log: YtdlpLogger, msg: str
    ) -> None:
        assert ytdlp_log.error(msg) is None
        assert ytdlp_log.last_error() is None

    @pytest.mark.parametrize('msg', ['', 'ERROR:', 'ERROR: ', '\n', '   ', 'ERROR: \n\n'])
    def test_a_degenerate_message_never_raises(
        self, ytdlp_log: YtdlpLogger, msg: str
    ) -> None:
        """This runs while a download is already failing, so a crash here would
        replace the real reason with a traceback about the reporting itself."""
        ytdlp_log.error(msg)
        ytdlp_log.last_error()  # must not raise; the value itself is uninteresting


class TestProgressTicker:
    """The download ticker arrives many times a second and buries everything."""

    @pytest.mark.parametrize(
        'msg',
        [
            '[download]  42.5% of  159.34MiB at    9.60MiB/s ETA 00:12',
            '[download]  100% of 5.00MiB in 00:01',
            '[download]   0.1% of ~ 12.00MiB at Unknown B/s ETA Unknown',
        ],
    )
    def test_ticker_lines_are_recognised(self, msg: str) -> None:
        assert YtdlpLogger._is_progress_tick(msg)

    @pytest.mark.parametrize(
        'msg',
        [
            '[download] Destination: /tmp/video.f137.mp4',
            '[download] Downloading playlist: Something',
            '[info] Writing video thumbnail to: /tmp/video.jpg',
            'Deleting original file /tmp/video.f137.mp4 (pass -k to keep)',
        ],
    )
    def test_other_lines_are_kept(self, msg: str) -> None:
        assert not YtdlpLogger._is_progress_tick(msg)


class TestRouting:
    def test_errors_are_collected(self, ytdlp_log: YtdlpLogger) -> None:
        ytdlp_log.error('ERROR: one')
        ytdlp_log.error('ERROR: two')
        assert ytdlp_log.errors == ['ERROR: one', 'ERROR: two']

    def test_warnings_are_not_collected(self, ytdlp_log: YtdlpLogger) -> None:
        """Only errors explain a failure; warnings are noise for this purpose."""
        ytdlp_log.warning('WARNING: something odd')
        assert ytdlp_log.errors == []

    def test_info_is_not_collected(self, ytdlp_log: YtdlpLogger) -> None:
        ytdlp_log.info('[info] Downloading 1 format(s)')
        assert ytdlp_log.errors == []

    def test_debug_lines_do_not_raise(self, ytdlp_log: YtdlpLogger) -> None:
        ytdlp_log.debug('[debug] Command-line config: []')
        ytdlp_log.debug('[download]  42.5% of 1.00MiB at 1.00MiB/s ETA 00:01')
        ytdlp_log.debug('plain info routed through debug')
        assert ytdlp_log.errors == []
