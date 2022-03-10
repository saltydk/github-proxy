from datetime import datetime
from datetime import timezone
from typing import Callable

import pytest
from faker import Faker
from requests import Response

from github_proxy.ratelimit import REMAINING_RATELIMIT_HEADER
from github_proxy.ratelimit import RESET_RATELIMIT_HEADER
from github_proxy.ratelimit import get_ratelimit_limit
from github_proxy.ratelimit import get_ratelimit_remaining
from github_proxy.ratelimit import get_ratelimit_reset
from github_proxy.ratelimit import is_rate_limited


def test_is_rate_limited():
    resp = Response()
    resp.status_code = 403
    resp.headers[REMAINING_RATELIMIT_HEADER] = "0"
    assert is_rate_limited(resp)


def test_is_not_rate_limited():
    resp = Response()
    resp.status_code = 200
    resp.headers[REMAINING_RATELIMIT_HEADER] = "10"
    assert not is_rate_limited(resp)


def test_get_ratelimit_remaining(faker: Faker):
    remaining = faker.pyint()
    resp = Response()
    resp.status_code = 200
    resp.headers[REMAINING_RATELIMIT_HEADER] = str(remaining)
    assert get_ratelimit_remaining(resp) == remaining


def test_get_ratelimit_reset(faker: Faker):
    expected: datetime = faker.date_time(tzinfo=timezone.utc)
    resp = Response()
    resp.status_code = 200
    resp.headers[RESET_RATELIMIT_HEADER] = str(expected.timestamp())

    actual = get_ratelimit_reset(resp)
    assert actual is not None
    assert actual.time() == expected.time()
    assert actual.date() == expected.date()


@pytest.mark.parametrize(
    argnames="func",
    argvalues=[get_ratelimit_limit, get_ratelimit_remaining, get_ratelimit_reset],
    ids=["limit", "remaining", "reset"],
)
def test_get_ratelimit_headers_without_header_existing(
    func: Callable[[Response], None]
):
    resp = Response()
    resp.status_code = 200
    assert func(resp) is None
