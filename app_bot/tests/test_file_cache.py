"""Answering a repeat request from what Telegram already holds.

A wrong hit here is the quiet kind of failure: somebody gets a file that looks
right and is not. So the tests are mostly about when *not* to use the cache, and
about falling back cleanly when Telegram no longer honours a stored id.
"""


import pytest
from yt_shared.enums import DownMediaType, MediaFileType, VideoQuality
from yt_shared.schemas.file_cache import CachedFile

from bot.core.file_cache import CachedDelivery
from bot.core.schemas import UploadSchema, UserSchema, VideoCaptionSchema

URL = 'https://example.com/v'


def make_user(
    *,
    forward_to: int | None = None,
    silent: bool = False,
    include_size: bool = True,
) -> UserSchema:
    caption = VideoCaptionSchema(
        include_title=True,
        include_filename=False,
        include_link=True,
        include_size=include_size,
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
            forward_to_group=forward_to is not None,
            forward_group_id=forward_to,
            silent=silent,
            video_caption=caption,
        ),
    )


def video(**kwargs) -> CachedFile:
    return CachedFile(
        file_id='VIDEO_ID',
        file_type=MediaFileType.VIDEO,
        title='A title',
        filename='a.mp4',
        duration=61.4,
        width=1920,
        height=1080,
        file_size=1024 * 1024,
        **kwargs,
    )


def audio(**kwargs) -> CachedFile:
    return CachedFile(
        file_id='AUDIO_ID',
        file_type=MediaFileType.AUDIO,
        title='A track',
        filename='a.mp3',
        duration=200.0,
        file_size=1024,
        **kwargs,
    )


class FakeBot:
    PLAIN_CAPTION = 'disabled'

    def __init__(self) -> None:
        self.videos: list[dict] = []
        self.audios: list[dict] = []
        self.refuse_ids: set[str] = set()
        self.refuse_chats: set[int] = set()

    def _check(self, file_id: str, chat_id: int) -> None:
        if file_id in self.refuse_ids or chat_id in self.refuse_chats:
            raise RuntimeError('wrong file identifier')

    async def send_video(self, **kwargs) -> None:
        self._check(kwargs['video'], kwargs['chat_id'])
        self.videos.append(kwargs)

    async def send_audio(self, **kwargs) -> None:
        self._check(kwargs['audio'], kwargs['chat_id'])
        self.audios.append(kwargs)


class FakeStore:
    def __init__(self, entries: list[CachedFile] | None = None) -> None:
        self.entries = entries or []
        self.calls: list[tuple] = []
        self.raises = False

    async def find(
        self, url, download_media_type, video_quality
    ) -> list[CachedFile]:
        if self.raises:
            raise RuntimeError('database is down')
        self.calls.append((url, download_media_type, video_quality))
        return self.entries


class TestFind:
    @pytest.mark.asyncio
    async def test_passes_the_whole_key_to_the_store(self) -> None:
        """Quality is part of it: 720p and 1080p are different answers."""
        store = FakeStore([video()])
        delivery = CachedDelivery(FakeBot(), store)
        await delivery.find(
            url=URL,
            media_type=DownMediaType.VIDEO,
            quality=VideoQuality.HD_720P,
            save_to_storage=False,
        )
        assert store.calls == [(URL, DownMediaType.VIDEO, VideoQuality.HD_720P)]

    @pytest.mark.asyncio
    async def test_skipped_when_the_file_is_wanted_on_disk(self) -> None:
        """A cache hit produces no file in storage, which is the whole point."""
        store = FakeStore([video()])
        found = await CachedDelivery(FakeBot(), store).find(
            url=URL,
            media_type=DownMediaType.VIDEO,
            quality=VideoQuality.BEST,
            save_to_storage=True,
        )
        assert found == []
        assert store.calls == []

    @pytest.mark.asyncio
    async def test_a_broken_database_is_a_miss_not_a_failure(self) -> None:
        store = FakeStore()
        store.raises = True
        found = await CachedDelivery(FakeBot(), store).find(
            url=URL,
            media_type=DownMediaType.VIDEO,
            quality=VideoQuality.BEST,
            save_to_storage=False,
        )
        assert found == []


class TestSend:
    async def deliver(self, bot: FakeBot, entries: list[CachedFile], **kwargs) -> bool:
        return await CachedDelivery(bot, FakeStore()).send(
            entries,
            original_url=URL,
            chat_id=kwargs.pop('chat_id', 100),
            reply_to_message_id=kwargs.pop('reply_to_message_id', 7),
            user=kwargs.pop('user', make_user()),
        )

    @pytest.mark.asyncio
    async def test_video_goes_out_as_a_video(self) -> None:
        bot = FakeBot()
        assert await self.deliver(bot, [video()])
        assert len(bot.videos) == 1
        assert bot.videos[0]['video'] == 'VIDEO_ID'
        assert bot.videos[0]['supports_streaming'] is True

    @pytest.mark.asyncio
    async def test_audio_goes_out_as_audio(self) -> None:
        """Sending audio as a video would lose the player and the tags."""
        bot = FakeBot()
        assert await self.deliver(bot, [audio()])
        assert len(bot.audios) == 1
        assert bot.audios[0]['audio'] == 'AUDIO_ID'

    @pytest.mark.asyncio
    async def test_both_files_when_both_were_asked_for(self) -> None:
        bot = FakeBot()
        assert await self.deliver(bot, [video(), audio()])
        assert len(bot.videos) == 1
        assert len(bot.audios) == 1

    @pytest.mark.asyncio
    async def test_it_replies_to_the_link(self) -> None:
        bot = FakeBot()
        await self.deliver(bot, [video()], reply_to_message_id=7)
        assert bot.videos[0]['reply_to_message_id'] == 7

    @pytest.mark.asyncio
    async def test_the_forward_group_gets_a_copy(self) -> None:
        """Otherwise a cache hit would quietly skip the group someone set up."""
        bot = FakeBot()
        await self.deliver(bot, [video()], user=make_user(forward_to=-500))
        assert [v['chat_id'] for v in bot.videos] == [100, -500]

    @pytest.mark.asyncio
    async def test_the_forwarded_copy_replies_to_nothing(self) -> None:
        """That message id belongs to the other chat."""
        bot = FakeBot()
        await self.deliver(bot, [video()], user=make_user(forward_to=-500))
        assert 'reply_to_message_id' not in bot.videos[1]

    @pytest.mark.asyncio
    async def test_the_silent_setting_is_honoured(self) -> None:
        bot = FakeBot()
        await self.deliver(bot, [video()], user=make_user(silent=True))
        assert bot.videos[0]['disable_notification'] is True

    @pytest.mark.asyncio
    async def test_a_refused_id_means_download_it_properly(self) -> None:
        """File ids are not promised to last; the cache is only an optimisation."""
        bot = FakeBot()
        bot.refuse_ids = {'VIDEO_ID'}
        assert await self.deliver(bot, [video()]) is False

    @pytest.mark.asyncio
    async def test_a_refused_forward_still_counts_as_delivered(self) -> None:
        """The person who asked has their file; re-downloading would send it twice."""
        bot = FakeBot()
        bot.refuse_chats = {-500}
        assert await self.deliver(bot, [video()], user=make_user(forward_to=-500))
        assert [v['chat_id'] for v in bot.videos] == [100]


class TestCaption:
    @pytest.mark.asyncio
    async def test_video_follows_the_caption_settings(self) -> None:
        bot = FakeBot()
        await CachedDelivery(bot, FakeStore()).send(
            [video()],
            original_url=URL,
            chat_id=100,
            reply_to_message_id=None,
            user=make_user(include_size=True),
        )
        caption = bot.videos[0]['caption']
        assert 'A title' in caption
        assert URL in caption
        assert '1.0MiB' in caption

    @pytest.mark.asyncio
    async def test_size_can_be_left_out(self) -> None:
        bot = FakeBot()
        await CachedDelivery(bot, FakeStore()).send(
            [video()],
            original_url=URL,
            chat_id=100,
            reply_to_message_id=None,
            user=make_user(include_size=False),
        )
        assert '1.0MiB' not in bot.videos[0]['caption']

    @pytest.mark.asyncio
    async def test_audio_keeps_the_plain_title_and_link(self) -> None:
        """Matching a fresh audio upload, which ignores the caption settings."""
        bot = FakeBot()
        await CachedDelivery(bot, FakeStore()).send(
            [audio()],
            original_url=URL,
            chat_id=100,
            reply_to_message_id=None,
            user=make_user(include_size=True),
        )
        assert bot.audios[0]['caption'] == f'A track\n{URL}'


@pytest.mark.asyncio
async def test_duration_is_passed_as_whole_seconds() -> None:
    """Telegram wants an integer; a float would be rejected."""
    bot = FakeBot()
    await CachedDelivery(bot, FakeStore()).send(
        [video()],
        original_url=URL,
        chat_id=100,
        reply_to_message_id=None,
        user=make_user(),
    )
    assert bot.videos[0]['duration'] == 61
