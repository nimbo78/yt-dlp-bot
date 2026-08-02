"""The bot's own startup message: who gets it, and when it goes away.

This is the one place the test suite uses fakes. The boundary drawn earlier —
pure functions only — was about not building machinery to reach trivial code.
Here the code deletes messages in people's chats and decides whom to write to,
so getting it wrong is visible and irreversible, and the orchestration *is* the
behaviour. A recording double for the client and the repository is cheaper than
finding out in production.
"""

from types import SimpleNamespace

import pytest
from yt_shared.enums import DownMediaType

from bot.core.schemas import UploadSchema, UserSchema, VideoCaptionSchema
from bot.core.startup_notice import StartupNotice


def make_user(user_id: int, *, is_admin: bool, wants_startup: bool) -> UserSchema:
    caption = VideoCaptionSchema(
        include_title=True,
        include_filename=False,
        include_link=True,
        include_size=True,
    )
    return UserSchema(
        id=user_id,
        is_admin=is_admin,
        send_startup_message=wants_startup,
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


class FakeBot:
    """Records what would have been sent rather than sending it."""

    def __init__(self, users: list[UserSchema], ttl: int = 3600) -> None:
        self.allowed_users = {u.id: u for u in users}
        self.admin_users = {u.id: u for u in users if u.is_admin}
        self.conf = SimpleNamespace(
            telegram=SimpleNamespace(startup_message_ttl=ttl, lang_code='en')
        )
        self.sent: list[dict] = []
        self.edited: list[dict] = []
        self.deleted: list[tuple[int, int]] = []
        self.send_fails_for: set[int] = set()
        self.delete_fails = False
        self._next_message_id = 100

    async def get_me(self) -> SimpleNamespace:
        return SimpleNamespace(first_name='MyBot')

    def language_for(self, *candidate_ids: int | None) -> str:
        return 'en'

    async def send_message(
        self, chat_id: int, text: str, disable_notification: bool = False
    ) -> SimpleNamespace:
        if chat_id in self.send_fails_for:
            raise RuntimeError('blocked by the user')
        self._next_message_id += 1
        self.sent.append({
            'chat_id': chat_id,
            'text': text,
            'silent': disable_notification,
            'id': self._next_message_id,
        })
        return SimpleNamespace(id=self._next_message_id)

    async def edit_message_text(self, chat_id: int, message_id: int, text: str) -> None:
        self.edited.append({
            'chat_id': chat_id,
            'message_id': message_id,
            'text': text,
        })

    async def delete_messages(self, chat_id: int, message_ids: int) -> None:
        if self.delete_fails:
            raise RuntimeError('message is too old to delete')
        self.deleted.append((chat_id, message_ids))


class FakeStore:
    """Stands in for the table that outlives the process."""

    def __init__(self, rows: list[tuple[int, int]] | None = None) -> None:
        self.rows = list(rows or [])

    async def take_all(self) -> list[tuple[int, int]]:
        taken, self.rows = self.rows, []
        return taken

    async def save_all(self, messages: list[tuple[int, int]]) -> None:
        self.rows.extend(messages)


@pytest.fixture
def store() -> FakeStore:
    return FakeStore()


class TestRecipients:
    def test_only_admins(self) -> None:
        """A restart is not news for anyone who cannot act on it."""
        bot = FakeBot([
            make_user(1, is_admin=True, wants_startup=True),
            make_user(2, is_admin=False, wants_startup=True),
        ])
        assert StartupNotice(bot, FakeStore()).recipients() == [1]

    def test_an_admin_can_still_opt_out(self) -> None:
        bot = FakeBot([
            make_user(1, is_admin=True, wants_startup=True),
            make_user(2, is_admin=True, wants_startup=False),
        ])
        assert StartupNotice(bot, FakeStore()).recipients() == [1]

    def test_nobody_at_all(self) -> None:
        bot = FakeBot([make_user(1, is_admin=False, wants_startup=True)])
        assert StartupNotice(bot, FakeStore()).recipients() == []


class TestAnnounce:
    @pytest.mark.asyncio
    async def test_greets_every_recipient_once(self, store: FakeStore) -> None:
        bot = FakeBot([
            make_user(1, is_admin=True, wants_startup=True),
            make_user(2, is_admin=True, wants_startup=True),
        ])
        await StartupNotice(bot, store).announce()
        assert [m['chat_id'] for m in bot.sent] == [1, 2]

    @pytest.mark.asyncio
    async def test_the_message_is_silent(self, store: FakeStore) -> None:
        """Housekeeping should be there when someone looks, not buzz."""
        bot = FakeBot([make_user(1, is_admin=True, wants_startup=True)])
        await StartupNotice(bot, store).announce()
        assert bot.sent[0]['silent'] is True

    @pytest.mark.asyncio
    async def test_says_nothing_when_there_is_nobody(self, store: FakeStore) -> None:
        bot = FakeBot([make_user(1, is_admin=False, wants_startup=True)])
        await StartupNotice(bot, store).announce()
        assert bot.sent == []
        assert store.rows == []

    @pytest.mark.asyncio
    async def test_records_what_it_sent(self, store: FakeStore) -> None:
        bot = FakeBot([make_user(1, is_admin=True, wants_startup=True)])
        await StartupNotice(bot, store).announce()
        assert store.rows == [(1, bot.sent[0]['id'])]

    @pytest.mark.asyncio
    async def test_one_blocked_recipient_does_not_stop_the_rest(self, store: FakeStore) -> None:
        bot = FakeBot([
            make_user(1, is_admin=True, wants_startup=True),
            make_user(2, is_admin=True, wants_startup=True),
        ])
        bot.send_fails_for = {1}
        await StartupNotice(bot, store).announce()
        assert [m['chat_id'] for m in bot.sent] == [2]
        assert store.rows == [(2, bot.sent[0]['id'])]


class TestAppend:
    @pytest.mark.asyncio
    async def test_adds_a_line_to_the_message_already_sent(self, store: FakeStore) -> None:
        bot = FakeBot([make_user(1, is_admin=True, wants_startup=True)])
        notice = StartupNotice(bot, store)
        await notice.announce()
        await notice.append('ytdlp.up_to_date', channel='STABLE', current='2026.01.01')

        assert len(bot.edited) == 1
        edited = bot.edited[0]['text']
        assert bot.sent[0]['text'] in edited
        assert '2026.01.01' in edited
        assert edited.count('\n') >= 1

    @pytest.mark.asyncio
    async def test_appending_twice_keeps_both_lines(self, store: FakeStore) -> None:
        bot = FakeBot([make_user(1, is_admin=True, wants_startup=True)])
        notice = StartupNotice(bot, store)
        await notice.announce()
        await notice.append('ytdlp.up_to_date', channel='STABLE', current='1')
        await notice.append('ytdlp.up_to_date', channel='STABLE', current='2')
        assert '1' in bot.edited[-1]['text']
        assert '2' in bot.edited[-1]['text']

    @pytest.mark.asyncio
    async def test_nothing_to_append_to(self, store: FakeStore) -> None:
        """The version check still runs when no message was posted."""
        bot = FakeBot([make_user(1, is_admin=False, wants_startup=True)])
        notice = StartupNotice(bot, store)
        await notice.announce()
        await notice.append('ytdlp.up_to_date', channel='STABLE', current='1')
        assert bot.edited == []


class TestRemoval:
    @pytest.mark.asyncio
    async def test_clears_what_the_previous_run_left(self, store: FakeStore) -> None:
        store.rows = [(1, 11), (2, 22)]
        bot = FakeBot([make_user(1, is_admin=True, wants_startup=True)])
        await StartupNotice(bot, store).clear_previous()
        assert bot.deleted == [(1, 11), (2, 22)]
        assert store.rows == []

    @pytest.mark.asyncio
    async def test_a_message_too_old_to_delete_is_forgotten_anyway(self, store: FakeStore) -> None:
        """Telegram refuses anything past 48 hours; retrying forever is worse."""
        store.rows = [(1, 11)]
        bot = FakeBot([make_user(1, is_admin=True, wants_startup=True)])
        bot.delete_fails = True
        await StartupNotice(bot, store).clear_previous()
        assert store.rows == []

    @pytest.mark.asyncio
    async def test_nothing_recorded(self, store: FakeStore) -> None:
        bot = FakeBot([make_user(1, is_admin=True, wants_startup=True)])
        await StartupNotice(bot, store).clear_previous()
        assert bot.deleted == []

    @pytest.mark.asyncio
    async def test_remove_now_takes_it_down_and_forgets_it(self, store: FakeStore) -> None:
        bot = FakeBot([make_user(1, is_admin=True, wants_startup=True)])
        notice = StartupNotice(bot, store)
        await notice.announce()
        await notice.remove_now()
        assert bot.deleted == [(1, bot.sent[0]['id'])]
        assert store.rows == []

    @pytest.mark.asyncio
    async def test_removing_twice_is_harmless(self, store: FakeStore) -> None:
        bot = FakeBot([make_user(1, is_admin=True, wants_startup=True)])
        notice = StartupNotice(bot, store)
        await notice.announce()
        await notice.remove_now()
        await notice.remove_now()
        assert len(bot.deleted) == 1

    @pytest.mark.asyncio
    async def test_a_zero_ttl_schedules_no_removal(self, store: FakeStore) -> None:
        bot = FakeBot([make_user(1, is_admin=True, wants_startup=True)], ttl=0)
        notice = StartupNotice(bot, store)
        await notice.announce()
        assert notice._removal is None
        assert bot.deleted == []

    @pytest.mark.asyncio
    async def test_a_ttl_schedules_one(self, store: FakeStore) -> None:
        bot = FakeBot([make_user(1, is_admin=True, wants_startup=True)], ttl=3600)
        notice = StartupNotice(bot, store)
        await notice.announce()
        assert notice._removal is not None
        notice._removal.cancel()
