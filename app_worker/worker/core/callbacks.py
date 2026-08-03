import asyncio
import logging

from aio_pika import IncomingMessage
from yt_shared.schemas.media import InbMediaPayload
from yt_shared.schemas.playlist import PlaylistRequestPayload
from yt_shared.utils.tasks.tasks import create_task

from worker.core.config import settings
from worker.core.payload_handler import InboundPayloadHandler
from worker.core.playlist_handler import PlaylistHandler


class RMQCallbacks:
    """RabbitMQ's callbacks."""

    def __init__(self) -> None:
        self._log = logging.getLogger(self.__class__.__name__)
        self._payload_handler = InboundPayloadHandler()
        self._playlist_handler = PlaylistHandler()
        # What actually bounds concurrent downloads. The channel's prefetch
        # does not: the message below is acknowledged before the download
        # starts, so the broker is free to deliver the next one immediately and
        # aio_pika runs every callback as a task of its own. Before this, a
        # selection of ten playlist items ran ten downloads at once on a host
        # that can hold two, and `MAX_SIMULTANEOUS_DOWNLOADS` said otherwise
        # while meaning nothing.
        #
        # Acknowledging late would be the tidier fix and is not available:
        # RabbitMQ closes a channel whose consumer holds a message longer than
        # `consumer_timeout` — thirty minutes as shipped — which a large
        # download passes, and the channel is shared with the playlist
        # consumer, so an unacknowledged download would also block enumeration.
        self._slot = asyncio.Semaphore(settings.MAX_SIMULTANEOUS_DOWNLOADS)

    async def on_input_message(self, message: IncomingMessage) -> None:
        try:
            await self._process_incoming_message(message)
        except Exception:
            self._log.exception('Critical exception in worker RabbitMQ callback')
            if not message.processed:
                await message.reject(requeue=False)

    async def on_playlist_message(self, message: IncomingMessage) -> None:
        """Enumerate a playlist, off to the side of the download queue.

        Acknowledged and spawned immediately rather than awaited: this consumer
        shares the channel's prefetch with the downloads, and holding it for the
        duration of a network round trip would stall a download behind somebody
        opening a menu.
        """
        try:
            payload = PlaylistRequestPayload.model_validate_json(message.body)
        except Exception:
            self._log.exception('Failed to deserialize playlist request: %s',
                                message.body)
            await self._reject_invalid_message(message)
            return

        await message.ack()
        create_task(
            self._playlist_handler.handle(payload),
            task_name=f'playlist-{payload.url_id}',
            logger=self._log,
            exception_message='Playlist enumeration of %s raised an exception',
            exception_message_args=(payload.url,),
        )

    async def _process_incoming_message(self, message: IncomingMessage) -> None:
        self._log.info('[x] Received message %s', message.body)
        try:
            media_payload = InbMediaPayload.model_validate_json(message.body)
        except Exception:
            self._log.exception('Failed to deserialize message body: %s', message.body)
            await self._reject_invalid_message(message)
            return

        await message.ack()
        async with self._slot:
            # Everything past this point is one download's worth of work: the
            # network, the disk and the FFmpeg pass. Waiting here is what makes
            # a queue of them a queue rather than a stampede.
            await self._payload_handler.handle(media_payload=media_payload)
        self._log.info('Processing done with payload: %s', media_payload)

    async def _reject_invalid_message(self, message: IncomingMessage) -> None:
        body = message.body
        self._log.error('Invalid message body: %s, type: %s', body, type(body))
        await message.reject(requeue=False)


rmq_callbacks = RMQCallbacks()
