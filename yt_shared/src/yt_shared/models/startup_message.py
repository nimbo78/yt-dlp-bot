import uuid

import sqlalchemy as sa
from sqlalchemy_utils import Timestamp, UUIDType

from yt_shared.db.session import Base


class StartupMessage(Base, Timestamp):
    """A message the bot posted about its own start, so it can be removed later.

    The timer that removes it lives in the bot process and dies with it — and a
    restart is exactly when these messages appear, so on a machine that
    redeploys often the timer is the case that fails. Recording the ids here
    lets the next start clear whatever the last one left behind.
    """

    # See the note in `pending_download.py`: the base's `id` carries a legacy
    # annotation that recent SQLAlchemy will not copy into a subclass, and
    # every model that shipped before this one declares its own.
    id = sa.Column(UUIDType(binary=False), primary_key=True, default=uuid.uuid4)
    chat_id = sa.Column(sa.BigInteger, nullable=False)
    message_id = sa.Column(sa.BigInteger, nullable=False)
