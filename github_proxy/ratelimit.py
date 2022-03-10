from datetime import datetime
from typing import Callable
from typing import Optional
from typing import TypeVar

import requests

REMAINING_RATELIMIT_HEADER = "x-ratelimit-remaining"
RESET_RATELIMIT_HEADER = "x-ratelimit-reset"
LIMIT_RATELIMIT_HEADER = "x-ratelimit-limit"


def is_rate_limited(resp: requests.Response) -> bool:
    remaining = get_ratelimit_remaining(resp)
    return resp.status_code == 403 and remaining is not None and remaining == 0


def get_ratelimit_remaining(resp: requests.Response) -> Optional[int]:
    return _get_optional_header(resp, REMAINING_RATELIMIT_HEADER, int)


def get_ratelimit_limit(resp: requests.Response) -> Optional[int]:
    return _get_optional_header(resp, LIMIT_RATELIMIT_HEADER, int)


def get_ratelimit_reset(resp: requests.Response) -> Optional[datetime]:
    return _get_optional_header(
        resp, RESET_RATELIMIT_HEADER, lambda s: datetime.utcfromtimestamp(float(s))
    )


T = TypeVar("T")


def _get_optional_header(
    resp: requests.Response, key: str, type_: Callable[[str], T]
) -> Optional[T]:
    serialized = resp.headers.get(key)
    if serialized is None:
        return None

    return type_(serialized)
