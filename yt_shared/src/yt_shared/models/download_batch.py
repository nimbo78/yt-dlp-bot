import uuid

import sqlalchemy as sa
from sqlalchemy_utils import Timestamp, UUIDType

from yt_shared.db.session import Base


class DownloadBatch(Base, Timestamp):
    """Several downloads that came from one message, and how many are left.

    Without this every task believes it is alone, which is how the first item
    of a playlist selection to finish deleted the message the link arrived in —
    while three more were still queued behind it — and left the "4 queued"
    summary on screen with nothing pointing at it.

    Keyed by the message the links came from, because that is the only thing
    every task in the batch already carries.
    """

    # Declared rather than inherited. See the note in `pending_download.py`.
    id = sa.Column(UUIDType(binary=False), primary_key=True, default=uuid.uuid4)
    chat_id = sa.Column(sa.BigInteger, nullable=False)
    message_id = sa.Column(sa.BigInteger, nullable=False)
    # The "n queued" message, removed by whichever task finishes last.
    summary_message_id = sa.Column(sa.BigInteger, nullable=True)
    # Counts down. The task that takes it to zero does the tidying up.
    remaining = sa.Column(sa.Integer, nullable=False)
    added_at = sa.Column(sa.DateTime, nullable=False, index=True)

    __table_args__ = (
        sa.UniqueConstraint('chat_id', 'message_id', name='download_batch_source_idx'),
    )
