"""Links waiting for a format to be chosen, and when they stop waiting.

Entries are aged by giving them an ``added_at`` in the past. The expiry decision
lives here rather than in the store precisely so it can be exercised without a
database: the store is a dumb reader, this class decides what is still valid.
"""

import datetime
from collections.abc import Callable

import pytest
from yt_shared.enums import DownMediaType, TelegramChatType

from bot.core.pending_downloads import (
    TTL,
    PendingDownload,
    PendingDownloads,
    generate_url_id,
)
from bot.core.schemas import UploadSchema, UserSchema, VideoCaptionSchema


def now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


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
    def _make(age: datetime.timedelta | None = None) -> PendingDownload:
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
            added_at=None if age is None else now() - age,
        )

    return _make


class FakeStore:
    """An in-memory stand-in that only stores and returns; it judges nothing."""

    def __init__(self) -> None:
        self.rows: dict[str, PendingDownload] = {}
        self.raises = False

    async def save(self, url_id: str, pending: PendingDownload) -> None:
        self.rows[url_id] = pending

    async def load(self, url_id: str) -> PendingDownload | None:
        if self.raises:
            raise RuntimeError('database is down')
        return self.rows.get(url_id)

    async def delete(self, url_id: str) -> None:
        self.rows.pop(url_id, None)

    async def delete_older_than(self, cutoff: datetime.datetime) -> int:
        stale = [
            url_id
            for url_id, pending in self.rows.items()
            if pending.added_at is not None and pending.added_at < cutoff
        ]
        for url_id in stale:
            del self.rows[url_id]
        return len(stale)

    async def count(self) -> int:
        return len(self.rows)


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def pending_downloads(store: FakeStore) -> PendingDownloads:
    return PendingDownloads(store)


def test_url_id_is_unique_per_message() -> None:
    assert generate_url_id(1, 2) != generate_url_id(1, 3)
    assert generate_url_id(1, 2) != generate_url_id(2, 2)
    assert generate_url_id(1, 2) == generate_url_id(1, 2)


def test_the_ttl_is_two_days() -> None:
    assert TTL.total_seconds() == 48 * 60 * 60


class TestExpiry:
    def test_a_fresh_entry_is_not_expired(self, make_pending) -> None:
        pending = make_pending(age=datetime.timedelta(hours=1))
        assert not pending.is_expired(now() - TTL)

    def test_an_old_entry_is(self, make_pending) -> None:
        pending = make_pending(age=datetime.timedelta(hours=49))
        assert pending.is_expired(now() - TTL)

    def test_an_unknown_age_counts_as_fresh(self, make_pending) -> None:
        """A choice just made has no recorded age yet."""
        assert not make_pending().is_expired(now() - TTL)


class TestGet:
    @pytest.mark.asyncio
    async def test_a_fresh_entry_comes_back(
        self, pending_downloads: PendingDownloads, make_pending
    ) -> None:
        await pending_downloads.add('a', make_pending())
        assert await pending_downloads.get('a') is not None

    @pytest.mark.asyncio
    async def test_just_short_of_the_ttl_still_comes_back(
        self, pending_downloads: PendingDownloads, make_pending
    ) -> None:
        await pending_downloads.add(
            'a', make_pending(age=datetime.timedelta(hours=47))
        )
        assert await pending_downloads.get('a') is not None

    @pytest.mark.asyncio
    async def test_an_expired_entry_reads_as_absent(
        self, pending_downloads: PendingDownloads, make_pending
    ) -> None:
        await pending_downloads.add(
            'a', make_pending(age=datetime.timedelta(hours=49))
        )
        assert await pending_downloads.get('a') is None

    @pytest.mark.asyncio
    async def test_an_expired_entry_is_dropped_on_the_way_out(
        self, pending_downloads: PendingDownloads, store: FakeStore, make_pending
    ) -> None:
        await pending_downloads.add(
            'a', make_pending(age=datetime.timedelta(hours=49))
        )
        await pending_downloads.get('a')
        assert store.rows == {}

    @pytest.mark.asyncio
    async def test_an_unknown_id(self, pending_downloads: PendingDownloads) -> None:
        assert await pending_downloads.get('nope') is None

    @pytest.mark.asyncio
    async def test_getting_does_not_consume(
        self, pending_downloads: PendingDownloads, make_pending
    ) -> None:
        await pending_downloads.add('a', make_pending())
        await pending_downloads.get('a')
        assert await pending_downloads.get('a') is not None

    @pytest.mark.asyncio
    async def test_a_broken_store_reads_as_expired(
        self, pending_downloads: PendingDownloads, store: FakeStore, make_pending
    ) -> None:
        """Far better than a traceback in front of whoever pressed the button."""
        await pending_downloads.add('a', make_pending())
        store.raises = True
        assert await pending_downloads.get('a') is None


class TestRemove:
    @pytest.mark.asyncio
    async def test_returns_and_consumes(
        self, pending_downloads: PendingDownloads, make_pending
    ) -> None:
        await pending_downloads.add('a', make_pending())
        assert await pending_downloads.remove('a') is not None
        assert await pending_downloads.remove('a') is None

    @pytest.mark.asyncio
    async def test_an_expired_entry_is_not_handed_out(
        self, pending_downloads: PendingDownloads, store: FakeStore, make_pending
    ) -> None:
        """Pressing a two-day-old button answers "expired", it does not download."""
        await pending_downloads.add(
            'a', make_pending(age=datetime.timedelta(hours=49))
        )
        assert await pending_downloads.remove('a') is None
        assert store.rows == {}


class TestSweep:
    @pytest.mark.asyncio
    async def test_removes_only_what_is_past_its_time(
        self, pending_downloads: PendingDownloads, make_pending
    ) -> None:
        await pending_downloads.add('fresh', make_pending())
        await pending_downloads.add(
            'old', make_pending(age=datetime.timedelta(hours=49))
        )
        await pending_downloads.add(
            'older', make_pending(age=datetime.timedelta(days=30))
        )

        assert await pending_downloads.sweep() == 2
        assert await pending_downloads.size() == 1
        assert await pending_downloads.get('fresh') is not None

    @pytest.mark.asyncio
    async def test_an_empty_store(self, pending_downloads: PendingDownloads) -> None:
        assert await pending_downloads.sweep() == 0

    @pytest.mark.asyncio
    async def test_reaches_entries_nobody_looks_up(
        self, pending_downloads: PendingDownloads, make_pending
    ) -> None:
        """The reason the sweep exists: eviction on access never gets to the
        entries that are actually accumulating."""
        for i in range(50):
            await pending_downloads.add(
                f'k{i}', make_pending(age=datetime.timedelta(days=30))
            )
        assert await pending_downloads.sweep() == 50
        assert await pending_downloads.size() == 0


@pytest.mark.asyncio
async def test_a_choice_survives_being_read_by_a_new_instance(
    store: FakeStore, make_pending
) -> None:
    """The whole point: the process may be a different one by then."""
    await PendingDownloads(store).add('a', make_pending())
    assert await PendingDownloads(store).get('a') is not None
