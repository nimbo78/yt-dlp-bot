from pydantic import PositiveInt
from yt_shared.config import CommonSettings


class ApiSettings(CommonSettings):
    API_HOST: str
    API_PORT: PositiveInt
    API_WORKERS: PositiveInt
    # Empty means the API is unauthenticated, which is only safe because the
    # published port is bound to 127.0.0.1. See api/common/security.py.
    API_TOKEN: str = ''


settings = ApiSettings()
