from typing import Any

from aio_pika import ExchangeType

INPUT_QUEUE = 'input.q'
ERROR_QUEUE = 'error.q'
SUCCESS_QUEUE = 'success.q'
PROGRESS_QUEUE = 'progress.q'
PLAYLIST_QUEUE = 'playlist.q'
PLAYLIST_RESULT_QUEUE = 'playlist_result.q'

INPUT_EXCHANGE = 'input.dx'
SUCCESS_EXCHANGE = 'success.dx'
ERROR_EXCHANGE = 'error.dx'
PROGRESS_EXCHANGE = 'progress.dx'
PLAYLIST_EXCHANGE = 'playlist.dx'
PLAYLIST_RESULT_EXCHANGE = 'playlist_result.dx'

# A progress update is worthless once a newer one exists, so the queue is kept
# deliberately lossy: stale messages expire and a slow consumer drops the
# oldest ones instead of building up a backlog.
_PROGRESS_QUEUE_ARGS = {
    'x-message-ttl': 30_000,
    'x-max-length': 200,
    'x-overflow': 'drop-head',
}

# Somebody is looking at a keyboard waiting for this, and will have given up
# long before a five-minute-old answer arrives. Both directions expire, so a
# broker restart cannot deliver a stack of stale menus into people's chats.
_PLAYLIST_QUEUE_ARGS = {
    'x-message-ttl': 300_000,
    'x-max-length': 100,
    'x-overflow': 'drop-head',
}


def get_rabbit_config() -> dict[str, list[dict[str, Any]]]:
    return {
        'queues': [
            {'name': INPUT_QUEUE, 'auto_delete': False, 'durable': True},
            {'name': ERROR_QUEUE, 'auto_delete': False, 'durable': True},
            {'name': SUCCESS_QUEUE, 'auto_delete': False, 'durable': True},
            {
                'name': PROGRESS_QUEUE,
                'auto_delete': False,
                'durable': False,
                'arguments': _PROGRESS_QUEUE_ARGS,
            },
            {
                'name': PLAYLIST_QUEUE,
                'auto_delete': False,
                'durable': False,
                'arguments': _PLAYLIST_QUEUE_ARGS,
            },
            {
                'name': PLAYLIST_RESULT_QUEUE,
                'auto_delete': False,
                'durable': False,
                'arguments': _PLAYLIST_QUEUE_ARGS,
            },
        ],
        'exchanges': [
            {
                'name': INPUT_EXCHANGE,
                'auto_delete': False,
                'durable': True,
                'type': ExchangeType.DIRECT.value,
            },
            {
                'name': ERROR_EXCHANGE,
                'auto_delete': False,
                'durable': True,
                'type': ExchangeType.DIRECT.value,
            },
            {
                'name': SUCCESS_EXCHANGE,
                'auto_delete': False,
                'durable': True,
                'type': ExchangeType.DIRECT.value,
            },
            {
                'name': PROGRESS_EXCHANGE,
                'auto_delete': False,
                'durable': False,
                'type': ExchangeType.DIRECT.value,
            },
            {
                'name': PLAYLIST_EXCHANGE,
                'auto_delete': False,
                'durable': False,
                'type': ExchangeType.DIRECT.value,
            },
            {
                'name': PLAYLIST_RESULT_EXCHANGE,
                'auto_delete': False,
                'durable': False,
                'type': ExchangeType.DIRECT.value,
            },
        ],
        'queue_bindings': {
            INPUT_QUEUE: [{'exchange_name': INPUT_EXCHANGE}],
            ERROR_QUEUE: [{'exchange_name': ERROR_EXCHANGE}],
            SUCCESS_QUEUE: [{'exchange_name': SUCCESS_EXCHANGE}],
            PROGRESS_QUEUE: [{'exchange_name': PROGRESS_EXCHANGE}],
            PLAYLIST_QUEUE: [{'exchange_name': PLAYLIST_EXCHANGE}],
            PLAYLIST_RESULT_QUEUE: [{'exchange_name': PLAYLIST_RESULT_EXCHANGE}],
        },
    }
