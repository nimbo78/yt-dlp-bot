"""Who is last, and what they tidy up.

Both bugs this exists for were invisible in the code and obvious on screen:
the message a playlist link arrived in was deleted after the *first* of four
downloads finished, and the "4 queued" summary — the one message no single task
points at — stayed there for good.
"""

import datetime

import pytest

from bot.core.batches import TTL, Batches, BatchProgress


class FakeStore:
    """Counts, and nothing else. Every decision under test is made elsewhere."""

    def __init__(self) -> None:
        self.rows: dict[tuple[int, int], list] = {}
        self.raises_on_finish = False
        self.raises_on_start = False

    async def start(
        self,
        chat_id: int,
        message_id: int,
        count: int,
        summary_message_id: int | None,
    ) -> None:
        if self.raises_on_start:
            raise RuntimeError('database is down')
        self.rows[chat_id, message_id] = [count, summary_message_id]

    async def finish_one(
        self, chat_id: int, message_id: int
    ) -> tuple[int, int | None] | None:
        if self.raises_on_finish:
            raise RuntimeError('database is down')
        row = self.rows.get((chat_id, message_id))
        if row is None:
            return None
        row[0] -= 1
        return row[0], row[1]

    async def delete(self, chat_id: int, message_id: int) -> None:
        self.rows.pop((chat_id, message_id), None)

    async def delete_older_than(self, cutoff: datetime.datetime) -> int:
        dropped = len(self.rows)
        self.rows.clear()
        return dropped


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def batches(store: FakeStore) -> Batches:
    return Batches(store)


def test_the_ttl_outlasts_a_long_queue() -> None:
    assert TTL.total_seconds() == 12 * 60 * 60


class TestIsLast:
    def test_zero_is_last(self) -> None:
        assert BatchProgress(remaining=0, summary_message_id=1).is_last

    def test_more_to_come_is_not(self) -> None:
        assert not BatchProgress(remaining=3, summary_message_id=1).is_last

    def test_below_zero_is_still_last(self) -> None:
        """A task delivered twice would take the count negative, and nobody
        would ever be last if this compared for equality."""
        assert BatchProgress(remaining=-2, summary_message_id=1).is_last


class TestFinishOne:
    @pytest.mark.asyncio
    async def test_an_ordinary_download_belongs_to_no_batch(
        self, batches: Batches
    ) -> None:
        """Which is almost all of them, and must behave exactly as before."""
        assert await batches.finish_one(1, 2) is None

    @pytest.mark.asyncio
    async def test_only_the_last_of_four_is_last(self, batches: Batches) -> None:
        await batches.start(1, 2, count=4, summary_message_id=9)
        results = [await batches.finish_one(1, 2) for _ in range(4)]
        assert [r.is_last for r in results] == [False, False, False, True]

    @pytest.mark.asyncio
    async def test_the_summary_travels_with_every_answer(
        self, batches: Batches
    ) -> None:
        await batches.start(1, 2, count=2, summary_message_id=9)
        first = await batches.finish_one(1, 2)
        last = await batches.finish_one(1, 2)
        assert first.summary_message_id == 9
        assert last.summary_message_id == 9

    @pytest.mark.asyncio
    async def test_the_batch_is_dropped_once_finished(
        self, batches: Batches, store: FakeStore
    ) -> None:
        await batches.start(1, 2, count=1, summary_message_id=9)
        await batches.finish_one(1, 2)
        assert store.rows == {}

    @pytest.mark.asyncio
    async def test_a_late_arrival_after_the_batch_closed(
        self, batches: Batches
    ) -> None:
        """Reads as an ordinary single download, which is the safe answer: it
        deletes nothing that is not already gone."""
        await batches.start(1, 2, count=1, summary_message_id=9)
        await batches.finish_one(1, 2)
        assert await batches.finish_one(1, 2) is None

    @pytest.mark.asyncio
    async def test_batches_from_different_messages_do_not_mix(
        self, batches: Batches
    ) -> None:
        await batches.start(1, 2, count=2, summary_message_id=9)
        await batches.start(1, 3, count=1, summary_message_id=10)
        assert (await batches.finish_one(1, 3)).is_last
        assert not (await batches.finish_one(1, 2)).is_last

    @pytest.mark.asyncio
    async def test_the_same_message_id_in_another_chat_is_another_batch(
        self, batches: Batches
    ) -> None:
        await batches.start(1, 2, count=2, summary_message_id=9)
        await batches.start(99, 2, count=1, summary_message_id=10)
        assert (await batches.finish_one(99, 2)).is_last

    @pytest.mark.asyncio
    async def test_an_unreadable_store_reads_as_no_batch(
        self, batches: Batches, store: FakeStore
    ) -> None:
        """The old behaviour, which is wrong in a small way — where raising
        would break the delivery of a file that already downloaded."""
        await batches.start(1, 2, count=2, summary_message_id=9)
        store.raises_on_finish = True
        assert await batches.finish_one(1, 2) is None


class TestMissingIds:
    """The API can queue a download that came from no message at all."""

    @pytest.mark.asyncio
    async def test_no_message_id(self, batches: Batches, store: FakeStore) -> None:
        assert await batches.finish_one(1, None) is None
        assert not store.raises_on_finish, 'the store was not even asked'

    @pytest.mark.asyncio
    async def test_no_chat_id(self, batches: Batches) -> None:
        assert await batches.finish_one(None, 2) is None

    @pytest.mark.asyncio
    async def test_neither(self, batches: Batches) -> None:
        assert await batches.finish_one(None, None) is None


class TestStart:
    @pytest.mark.asyncio
    async def test_a_failure_to_record_does_not_reach_the_caller(
        self, batches: Batches, store: FakeStore
    ) -> None:
        """Losing the record costs the tidying up, not the downloads — those
        are already queued and will arrive either way."""
        store.raises_on_start = True
        await batches.start(1, 2, count=3, summary_message_id=9)

    @pytest.mark.asyncio
    async def test_a_second_batch_from_one_message_replaces_the_first(
        self, batches: Batches
    ) -> None:
        await batches.start(1, 2, count=5, summary_message_id=9)
        await batches.start(1, 2, count=1, summary_message_id=11)
        progress = await batches.finish_one(1, 2)
        assert progress.is_last
        assert progress.summary_message_id == 11


class TestSweep:
    @pytest.mark.asyncio
    async def test_it_drops_what_never_finished(
        self, batches: Batches, store: FakeStore
    ) -> None:
        await batches.start(1, 2, count=3, summary_message_id=9)
        assert await batches.sweep() == 1
        assert store.rows == {}

    @pytest.mark.asyncio
    async def test_nothing_to_sweep(self, batches: Batches) -> None:
        assert await batches.sweep() == 0
