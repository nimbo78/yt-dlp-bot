"""Refusing a download that will not fit.

The guard runs as a yt-dlp progress hook, so the contract that matters is: it
raises for a download that cannot fit, stays silent otherwise, and never raises
for a reason the user cannot act on.
"""

from collections.abc import Callable

import pytest

from worker.core import free_space
from worker.core.free_space import (
    NotEnoughSpaceError,
    ensure_floor,
    make_space_guard,
    required_bytes,
    shortage_message,
)

MB = 1024 * 1024
GB = 1024 * MB


@pytest.fixture
def free(monkeypatch) -> Callable[[int], None]:
    """Pretend the staging area has this much room."""

    def _set(amount: int) -> None:
        monkeypatch.setattr(free_space, 'free_bytes', lambda _path: amount)

    return _set


class TestRequiredBytes:
    def test_leaves_room_for_the_streams_and_the_merge(self) -> None:
        """Video and audio arrive separately and are merged into a third file."""
        assert required_bytes(100 * MB, floor_bytes=0, multiplier=3.0) == 300 * MB

    def test_the_floor_is_added_on_top(self) -> None:
        assert required_bytes(100 * MB, floor_bytes=512 * MB, multiplier=3.0) == (
            300 * MB + 512 * MB
        )

    def test_a_zero_sized_download_still_wants_the_floor(self) -> None:
        assert required_bytes(0, floor_bytes=512 * MB) == 512 * MB


class TestShortageMessage:
    def test_names_both_numbers(self) -> None:
        message = shortage_message(free=100 * MB, required=2 * GB)
        assert '100.0MiB' in message
        assert '2.0GiB' in message

    def test_is_recognised_by_the_bot_error_classifier(self) -> None:
        """The wording is the contract between the two services.

        The worker writes this string; the bot matches it to a category and
        explains it. Rewording it here without the bot's pattern would silently
        turn a clear refusal back into a raw dump.
        """
        assert 'not enough free space' in shortage_message(1, 2).lower()


class TestEnsureFloor:
    def test_passes_when_there_is_room(self, tmp_path, free) -> None:
        free(2 * GB)
        ensure_floor(tmp_path, 512 * MB)

    def test_raises_when_below_the_floor(self, tmp_path, free) -> None:
        free(100 * MB)
        with pytest.raises(NotEnoughSpaceError, match='Not enough free space'):
            ensure_floor(tmp_path, 512 * MB)

    def test_a_zero_floor_disables_the_check(self, tmp_path, free) -> None:
        free(0)
        ensure_floor(tmp_path, 0)

    def test_reads_the_real_filesystem_by_default(self, tmp_path) -> None:
        """Without a floor to compare against, nothing should ever raise."""
        ensure_floor(tmp_path, 0)


class TestSpaceGuard:
    def test_allows_a_download_that_fits(self, tmp_path, free) -> None:
        free(10 * GB)
        guard = make_space_guard(tmp_path, floor_bytes=512 * MB)
        guard({'status': 'downloading', 'total_bytes': 1 * GB, 'downloaded_bytes': 0})

    def test_stops_a_download_that_does_not_fit(self, tmp_path, free) -> None:
        free(1 * GB)
        guard = make_space_guard(tmp_path, floor_bytes=512 * MB)
        with pytest.raises(NotEnoughSpaceError):
            guard({
                'status': 'downloading',
                'total_bytes': 2 * GB,
                'downloaded_bytes': 0,
            })

    def test_counts_what_has_already_been_written(self, tmp_path, free) -> None:
        """Those bytes came out of the same free space.

        Ignoring them would make the guard stricter the further a download got,
        and abort one that was always going to fit.
        """
        guard = make_space_guard(tmp_path, floor_bytes=0)
        # 3 GiB needed for a 1 GiB download. Half of it is already on disk, so
        # 1.5 GiB of headroom plus the 1.5 GiB written is exactly enough.
        free(2 * GB - 512 * MB)
        guard({
            'status': 'downloading',
            'total_bytes': 1 * GB,
            'downloaded_bytes': 1 * GB + 512 * MB,
        })

    def test_uses_the_estimate_when_the_exact_size_is_unknown(
        self, tmp_path, free
    ) -> None:
        free(100 * MB)
        guard = make_space_guard(tmp_path, floor_bytes=0)
        with pytest.raises(NotEnoughSpaceError):
            guard({'status': 'downloading', 'total_bytes_estimate': 2 * GB})

    def test_says_nothing_when_no_size_is_reported(self, tmp_path, free) -> None:
        """Some sites never report one; the floor is the only check left."""
        free(1)
        guard = make_space_guard(tmp_path, floor_bytes=0)
        guard({'status': 'downloading'})
        guard({'status': 'downloading', 'total_bytes': None})

    @pytest.mark.parametrize('status', ['finished', 'error', 'processing'])
    def test_ignores_every_other_status(self, tmp_path, free, status: str) -> None:
        """Only a download in flight can still be stopped usefully."""
        free(1)
        guard = make_space_guard(tmp_path, floor_bytes=1 * GB)
        guard({'status': status, 'total_bytes': 100 * GB})

    def test_the_floor_is_kept_in_reserve(self, tmp_path, free) -> None:
        """A download that fits exactly must still leave the floor untouched."""
        free(3 * GB)
        guard = make_space_guard(tmp_path, floor_bytes=1 * GB)
        with pytest.raises(NotEnoughSpaceError):
            guard({'status': 'downloading', 'total_bytes': 1 * GB})
