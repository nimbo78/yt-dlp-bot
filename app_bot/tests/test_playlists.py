"""When a stored menu stops being offered, and what happens when it cannot be read.

The whole point of keeping the policy out of the store is that these can be
exercised without a database driver on the import path. The store below only
stores and returns; every decision under test is made in `bot.core.playlists`.
"""

import datetime

import pytest

from bot.core.playlist_menu import MenuEntry, StoredPlaylist
from bot.core.playlists import TTL, Playlists


def now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)


def entries(count: int = 3) -> list[MenuEntry]:
    return [
        MenuEntry(index=i, title=f'Track {i}', url=f'https://example.com/{i}')
        for i in range(1, count + 1)
    ]


class FakeStore:
    """An in-memory stand-in that stores and returns; it judges nothing."""

    def __init__(self) -> None:
        self.rows: dict[str, StoredPlaylist] = {}
        self.raises_on_load = False
        self.raises_on_delete = False

    async def save(self, url_id: str, menu_entries: list[MenuEntry]) -> None:
        self.rows[url_id] = StoredPlaylist(entries=menu_entries, added_at=now())

    async def load(self, url_id: str) -> StoredPlaylist | None:
        if self.raises_on_load:
            raise RuntimeError('database is down')
        return self.rows.get(url_id)

    async def delete(self, url_id: str) -> None:
        if self.raises_on_delete:
            raise RuntimeError('database is down')
        self.rows.pop(url_id, None)

    async def delete_older_than(self, cutoff: datetime.datetime) -> int:
        stale = [k for k, v in self.rows.items() if v.added_at < cutoff]
        for url_id in stale:
            del self.rows[url_id]
        return len(stale)

    def age(self, url_id: str, by: datetime.timedelta) -> None:
        row = self.rows[url_id]
        self.rows[url_id] = StoredPlaylist(
            entries=row.entries, added_at=now() - by
        )


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


@pytest.fixture
def playlists(store: FakeStore) -> Playlists:
    return Playlists(store)


def test_the_ttl_is_six_hours() -> None:
    """Shorter than the pending downloads' two days, on purpose: a playlist
    gains and loses items while nobody is looking at the menu."""
    assert TTL.total_seconds() == 6 * 60 * 60


class TestGet:
    @pytest.mark.asyncio
    async def test_a_fresh_menu_comes_back(self, playlists: Playlists) -> None:
        await playlists.save('a', entries())
        found = await playlists.get('a')
        assert found is not None
        assert [e.index for e in found] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_just_short_of_the_ttl(
        self, playlists: Playlists, store: FakeStore
    ) -> None:
        await playlists.save('a', entries())
        store.age('a', datetime.timedelta(hours=5, minutes=59))
        assert await playlists.get('a') is not None

    @pytest.mark.asyncio
    async def test_past_the_ttl_reads_as_absent(
        self, playlists: Playlists, store: FakeStore
    ) -> None:
        await playlists.save('a', entries())
        store.age('a', datetime.timedelta(hours=7))
        assert await playlists.get('a') is None

    @pytest.mark.asyncio
    async def test_a_stale_menu_is_dropped_on_the_way_out(
        self, playlists: Playlists, store: FakeStore
    ) -> None:
        await playlists.save('a', entries())
        store.age('a', datetime.timedelta(days=2))
        await playlists.get('a')
        assert store.rows == {}

    @pytest.mark.asyncio
    async def test_an_unknown_id(self, playlists: Playlists) -> None:
        assert await playlists.get('nope') is None

    @pytest.mark.asyncio
    async def test_a_broken_store_reads_as_expired(
        self, playlists: Playlists, store: FakeStore
    ) -> None:
        """Far better than an unanswered callback, which spins until the
        client gives up."""
        await playlists.save('a', entries())
        store.raises_on_load = True
        assert await playlists.get('a') is None

    @pytest.mark.asyncio
    async def test_getting_does_not_consume(self, playlists: Playlists) -> None:
        await playlists.save('a', entries())
        await playlists.get('a')
        assert await playlists.get('a') is not None


class TestRemove:
    @pytest.mark.asyncio
    async def test_a_menu_that_has_served_its_purpose(
        self, playlists: Playlists, store: FakeStore
    ) -> None:
        await playlists.save('a', entries())
        await playlists.remove('a')
        assert store.rows == {}

    @pytest.mark.asyncio
    async def test_removing_something_that_is_not_there(
        self, playlists: Playlists
    ) -> None:
        await playlists.remove('nope')

    @pytest.mark.asyncio
    async def test_a_failed_delete_does_not_reach_the_caller(
        self, playlists: Playlists, store: FakeStore
    ) -> None:
        """The sweep will get it; at worst a stale row waits six hours. The
        press that triggered this has a download to get on with."""
        await playlists.save('a', entries())
        store.raises_on_delete = True
        await playlists.remove('a')


class TestSweep:
    @pytest.mark.asyncio
    async def test_removes_only_what_is_past_its_time(
        self, playlists: Playlists, store: FakeStore
    ) -> None:
        await playlists.save('fresh', entries())
        await playlists.save('old', entries())
        store.age('old', datetime.timedelta(hours=7))
        assert await playlists.sweep() == 1
        assert await playlists.get('fresh') is not None

    @pytest.mark.asyncio
    async def test_an_empty_store(self, playlists: Playlists) -> None:
        assert await playlists.sweep() == 0

    @pytest.mark.asyncio
    async def test_it_reaches_menus_nobody_looks_up(
        self, playlists: Playlists, store: FakeStore
    ) -> None:
        """The reason the sweep exists: eviction on access never gets to the
        menus that are actually accumulating."""
        for i in range(20):
            await playlists.save(f'k{i}', entries())
            store.age(f'k{i}', datetime.timedelta(days=1))
        assert await playlists.sweep() == 20
        assert store.rows == {}


@pytest.mark.asyncio
async def test_a_menu_survives_being_read_by_a_new_instance(
    store: FakeStore,
) -> None:
    """The process may be a different one by the time a page is turned."""
    await Playlists(store).save('a', entries())
    assert await Playlists(store).get('a') is not None
