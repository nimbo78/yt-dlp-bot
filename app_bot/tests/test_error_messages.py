"""The classifier that turns yt-dlp's output into an explanation.

The samples below are the shapes yt-dlp really emits. Correctness here depends
as much on the *order* of ``_PATTERNS`` as on the patterns themselves, because
the first match wins and several of these messages satisfy more than one rule —
so ordering gets its own tests rather than being left to luck.
"""

import pytest

from bot.core.error_messages import (
    classify,
    extract_reason,
    strip_extractor_prefix,
)

# (expected category, message as yt-dlp writes it)
RECOGNISED = [
    ('drm', 'ERROR: [generic] The requested site is known to use DRM protection. '
            'It will NOT be supported.'),
    ('site_unsupported', 'ERROR: The requested site is primarily used for piracy '
                         'and is not supported.'),
    ('suspended', 'ERROR: [twitter] 2083594794454921589: Suspended'),
    ('age_restricted', 'ERROR: [youtube] dQw4: Sign in to confirm your age. '
                       'This video may be inappropriate for some users.'),
    ('members_only', 'ERROR: [youtube] dQw4: Join this channel to get access to '
                     'members-only content'),
    ('not_started', 'ERROR: [youtube] dQw4: This live event will begin in 3 hours.'),
    ('geo_blocked', 'ERROR: [youtube] dQw4: The uploader has not made this video '
                    'available in your country'),
    ('login_required', 'ERROR: [youtube] dQw4: Sign in to confirm you are not a bot. '
                       'Use --cookies-from-browser or --cookies'),
    ('private', "ERROR: [youtube] dQw4: Private video. Sign in if you've been "
                'granted access to this video'),
    ('removed', 'ERROR: [youtube] dQw4: Video unavailable. This video has been '
                'removed by the uploader'),
    ('subscription', 'ERROR: [nebula] xyz: This video requires a subscription'),
    ('network', 'ERROR: Unable to download webpage: <urlopen error timed out>'),
    ('no_media', 'ERROR: [twitter] 123: No video could be found in this tweet'),
    ('format_unavailable', 'ERROR: [youtube] dQw4: Requested format is not available'),
    ('rate_limited', 'ERROR: [youtube] dQw4: HTTP Error 429: Too Many Requests'),
    ('unsupported_url', 'ERROR: Unsupported URL: https://example.com/some/page'),
    ('not_found', 'ERROR: [generic] xyz: HTTP Error 404: Not Found'),
    ('forbidden', 'ERROR: unable to download video data: HTTP Error 403: Forbidden'),
    ('unavailable', 'ERROR: [youtube] dQw4: Video unavailable'),
]


@pytest.mark.parametrize(('expected', 'message'), RECOGNISED)
def test_recognised_failures_are_classified(expected: str, message: str) -> None:
    error = classify(message)
    assert error is not None, f'not recognised at all: {message}'
    assert error.name == expected


def test_every_category_is_reachable() -> None:
    """A pattern nothing can reach is a pattern nobody maintains."""
    from bot.core.error_messages import _PATTERNS

    defined = {error.name for _, error in _PATTERNS}
    covered = {name for name, _ in RECOGNISED}
    assert defined - covered == set(), 'categories without a sample above'


@pytest.mark.parametrize(
    'message',
    [
        'ERROR: [SomeSite] xyz: Something entirely new went wrong',
        'ERROR: postprocessing: ffmpeg exited with code 1',
        '',
    ],
)
def test_unrecognised_failures_stay_unclassified(message: str) -> None:
    """Anything unknown must fall through to the full detailed report."""
    assert classify(message) is None


def test_none_is_not_a_failure() -> None:
    assert classify(None) is None


class TestOrdering:
    """The rules that only hold because of where a pattern sits in the table."""

    def test_private_video_is_not_a_login_problem(self) -> None:
        """This one says "Sign in", but adding cookies will not help."""
        error = classify(
            "ERROR: [youtube] dQw4: Private video. Sign in if you've been granted "
            'access to this video'
        )
        assert error.name == 'private'

    def test_age_gate_is_not_a_login_problem(self) -> None:
        """Also says "Sign in", but the advice differs: an adult account."""
        error = classify('ERROR: [youtube] dQw4: Sign in to confirm your age.')
        assert error.name == 'age_restricted'

    def test_drm_wins_over_unsupported(self) -> None:
        """Refusals on principle name a reason; report the reason, not the refusal."""
        error = classify(
            'ERROR: The requested site is known to use DRM protection and is '
            'not supported and will not be supported.'
        )
        assert error.name == 'drm'

    def test_bot_check_is_a_cookie_problem(self) -> None:
        """Distinct from a plain age gate: this one is about the server's address."""
        error = classify(
            "ERROR: [youtube] dQw4: Sign in to confirm you're not a bot."
        )
        assert error.name == 'login_required'


@pytest.mark.parametrize(
    'apostrophe',
    ["'", '’'],
    ids=['ascii', 'typographic'],
)
def test_apostrophes_are_matched_in_both_shapes(apostrophe: str) -> None:
    """yt-dlp uses either, and a missed one silently loses the category."""
    bot_check = f'ERROR: [youtube] dQw4: Sign in to confirm you{apostrophe}re not a bot.'
    assert classify(bot_check).name == 'login_required'

    no_media = f'ERROR: [twitter] 123: There{apostrophe}s no video in this tweet'
    assert classify(no_media).name == 'no_media'


@pytest.mark.parametrize(
    'spelling',
    ['there is no video', 'theres no video', "there's no video"],
)
def test_no_media_phrasings(spelling: str) -> None:
    assert classify(f'ERROR: [twitter] 123: {spelling} in this tweet').name == 'no_media'


class TestStripExtractorPrefix:
    def test_removes_extractor_and_id(self) -> None:
        assert (
            strip_extractor_prefix('[twitter] 2083594794454921589: Suspended')
            == 'Suspended'
        )

    def test_leaves_a_bare_message_alone(self) -> None:
        assert strip_extractor_prefix('Something went wrong') == 'Something went wrong'

    def test_trims_surrounding_space(self) -> None:
        assert strip_extractor_prefix('[youtube] abc:   Private video  ') == 'Private video'


class TestExtractReason:
    def test_yt_dlp_leads_with_the_reason(self) -> None:
        raw = '[youtube] abc: Private video\n  File "x.py", line 1, in <module>'
        assert extract_reason(raw) == 'Private video'

    def test_a_python_traceback_ends_with_it(self) -> None:
        raw = (
            'Traceback (most recent call last):\n'
            '  File "x.py", line 1, in <module>\n'
            'ValueError: boom'
        )
        assert extract_reason(raw) == 'ValueError: boom'

    def test_blank_input(self) -> None:
        assert extract_reason('   \n  \n') == ''
