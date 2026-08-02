"""Links waiting for a format to be chosen, and when they stop waiting.

Entries are aged by handing them an ``added_at`` in the past rather than by
patching the clock: the store reads ``time.monotonic()`` itself, so this
exercises the real comparison.
"""

import time
from collections.abc import Callable, Iterator

import pytest
from yt_shared.enums import DownMediaType, TelegramChatType

from bot.core.pending_downloads import PendingDownload, PendingDownloadsStore
from bot.core.schemas import UploadSchema, UserSchema, VideoCaptionSchema

HOUR = 60 * 60


@pytest.fixture
def user() -> UserSchema:
    caption = VideoCaptionSchema(
        include_title=True,
        include_filename=False,
        include_link=True,
        include_size=True,
    )
    return UserSchema(
        id=1,
        is_admin=False,
        send_startup_message=False,
        download_media_type=DownMediaType.VIDEO,
        save_to_storage=False,
        use_url_regex_match=True,
        upload=UploadSchema(
            upload_video_file=True,
            upload_video_max_file_size=2147483648,
            forward_to_group=False,
            forward_group_id=None,
            silent=False,
            video_caption=caption,
        ),
    )


@pytest.fixture
def make_pending(user: UserSchema) -> Callable[..., PendingDownload]:
    def _make(age_seconds: float = 0.0) -> PendingDownload:
        return PendingDownload(
            url='https://example.com/v',
            original_url='https://example.com/v',
            from_chat_id=1,
            from_chat_type=TelegramChatType.PRIVATE,
            from_user_id=1,
            message_id=2,
            ack_message_id=3,
            save_to_storage=False,
            user=user,
            added_at=time.monotonic() - age_seconds,
        )

    return _make


@pytest.fixture(autouse=True)
def _empty_store() -> Iterator[None]:
    """Start each test with an empty store; it is class-level shared state."""
    PendingDownloadsStore.clear()
    yield
    PendingDownloadsStore.clear()


def test_url_id_is_unique_per_message() -> None:
    generate = PendingDownloadsStore.generate_url_id
    assert generate(1, 2) != generate(1, 3)
    assert generate(1, 2) != generate(2, 2)
    assert generate(1, 2) == generate(1, 2)


def test_the_default_ttl_is_two_days() -> None:
    assert PendingDownloadsStore.TTL_SECONDS == 48 * HOUR


class TestGet:
    def test_a_fresh_entry_comes_back(self, make_pending) -> None:
        PendingDownloadsStore.add('a', make_pending())
        assert PendingDownloadsStore.get('a') is not None

    def test_an_entry_just_short_of_the_ttl_still_comes_back(
        self, make_pending
    ) -> None:
        PendingDownloadsStore.add('a', make_pending(age_seconds=47 * HOUR))
        assert PendingDownloadsStore.get('a') is not None

    def test_an_expired_entry_reads_as_absent(self, make_pending) -> None:
        PendingDownloadsStore.add('a', make_pending(age_seconds=49 * HOUR))
        assert PendingDownloadsStore.get('a') is None

    def test_an_expired_entry_is_dropped_on_the_way_out(self, make_pending) -> None:
        PendingDownloadsStore.add('a', make_pending(age_seconds=49 * HOUR))
        PendingDownloadsStore.get('a')
        assert PendingDownloadsStore.size() == 0

    def test_an_unknown_id(self) -> None:
        assert PendingDownloadsStore.get('nope') is None

    def test_getting_does_not_consume(self, make_pending) -> None:
        PendingDownloadsStore.add('a', make_pending())
        PendingDownloadsStore.get('a')
        assert PendingDownloadsStore.get('a') is not None


class TestRemove:
    def test_returns_and_consumes(self, make_pending) -> None:
        PendingDownloadsStore.add('a', make_pending())
        assert PendingDownloadsStore.remove('a') is not None
        assert PendingDownloadsStore.remove('a') is None

    def test_an_expired_entry_is_not_handed_out(self, make_pending) -> None:
        """Pressing a two-day-old button must answer "expired", not download."""
        PendingDownloadsStore.add('a', make_pending(age_seconds=49 * HOUR))
        assert PendingDownloadsStore.remove('a') is None
        assert PendingDownloadsStore.size() == 0

    def test_an_unknown_id(self) -> None:
        assert PendingDownloadsStore.remove('nope') is None


class TestSweep:
    def test_removes_only_what_is_past_its_time(self, make_pending) -> None:
        PendingDownloadsStore.add('fresh', make_pending())
        PendingDownloadsStore.add('old', make_pending(age_seconds=49 * HOUR))
        PendingDownloadsStore.add('older', make_pending(age_seconds=100 * HOUR))

        assert PendingDownloadsStore.sweep() == 2
        assert PendingDownloadsStore.size() == 1
        assert PendingDownloadsStore.get('fresh') is not None

    def test_an_empty_store(self) -> None:
        assert PendingDownloadsStore.sweep() == 0

    def test_nothing_to_do(self, make_pending) -> None:
        PendingDownloadsStore.add('a', make_pending())
        assert PendingDownloadsStore.sweep() == 0
        assert PendingDownloadsStore.size() == 1

    def test_reaches_entries_nobody_looks_up(self, make_pending) -> None:
        """The reason the sweep exists at all: eviction on access never gets
        to the entries that are actually accumulating."""
        for i in range(50):
            PendingDownloadsStore.add(f'k{i}', make_pending(age_seconds=100 * HOUR))
        assert PendingDownloadsStore.sweep() == 50
        assert PendingDownloadsStore.size() == 0


def test_a_shorter_ttl_takes_effect(monkeypatch, make_pending) -> None:
    monkeypatch.setattr(PendingDownloadsStore, 'TTL_SECONDS', 10.0)
    PendingDownloadsStore.add('a', make_pending(age_seconds=11))
    assert PendingDownloadsStore.get('a') is None
