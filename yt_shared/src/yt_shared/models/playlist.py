import uuid

import sqlalchemy as sa
from sqlalchemy_utils import Timestamp, UUIDType

from yt_shared.db.session import Base


class Playlist(Base, Timestamp):
    """What a playlist link turned out to contain, kept while its menu is open.

    Held so that turning a page does not mean asking the site again — the answer
    cost a network round trip and does not change while somebody is reading it.
    Outside the bot process for the same reason as the pending downloads next to
    it: a restart would otherwise orphan every menu on screen.

    The entries are stored as JSON rather than as rows of their own. Nothing
    ever queries inside them: they are written once, read whole, and dropped
    together, so a second table would buy joins nobody needs.
    """

    # Declared rather than inherited. See the note in `pending_download.py`.
    id = sa.Column(UUIDType(binary=False), primary_key=True, default=uuid.uuid4)
    # Names the pending download whose keyboard this belongs to.
    url_id = sa.Column(sa.String, nullable=False, unique=True, index=True)
    title = sa.Column(sa.String, nullable=False)
    entries = sa.Column(sa.JSON, nullable=False)
    # What the source claimed, before the limit and the unusable ones were
    # dropped, so the menu can say "10 of 250" rather than implying 10.
    total = sa.Column(sa.Integer, nullable=False)
    added_at = sa.Column(sa.DateTime, nullable=False, index=True)
