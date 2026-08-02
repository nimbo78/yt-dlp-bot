import sqlalchemy as sa
from sqlalchemy_utils import Timestamp

from yt_shared.db.session import Base
from yt_shared.enums import TelegramChatType


class PendingDownload(Base, Timestamp):
    """A link waiting for someone to press a button on its keyboard.

    Kept out of process memory so a restart does not orphan every keyboard on
    screen. The user is referenced by id rather than stored: their settings can
    change while the keyboard waits, and the configuration is the authority on
    what they are now.
    """

    url_id = sa.Column(sa.String, nullable=False, unique=True, index=True)
    url = sa.Column(sa.String, nullable=False)
    original_url = sa.Column(sa.String, nullable=False)
    from_chat_id = sa.Column(sa.BigInteger, nullable=False)
    from_chat_type = sa.Column(sa.Enum(TelegramChatType), nullable=False)
    from_user_id = sa.Column(sa.BigInteger, nullable=True)
    message_id = sa.Column(sa.BigInteger, nullable=False)
    ack_message_id = sa.Column(sa.BigInteger, nullable=False)
    user_id = sa.Column(sa.BigInteger, nullable=False)
    save_to_storage = sa.Column(sa.Boolean, nullable=False, default=False)
    skip_cache = sa.Column(sa.Boolean, nullable=False, default=False)
    # Wall clock, unlike the in-memory version this replaces: a monotonic
    # reading means nothing to the process that reads it back.
    added_at = sa.Column(sa.DateTime, nullable=False, index=True)
