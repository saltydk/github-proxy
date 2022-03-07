import logging
from datetime import datetime
from typing import Optional

import requests
import werkzeug

from github_proxy.config import Config
from github_proxy.github_credentials import RateLimited
from github_proxy.github_credentials import credential_generator

logger = logging.getLogger(__name__)

REMAINING_RATELIMIT_HEADER = "x-ratelimit-remaining"
RESET_RATELIMIT_HEADER = "x-ratelimit-reset"
REQUEST_FILTERED_HEADERS = {"Connection", "Host"}
RESPONSE_FILTERED_HEADERS = {"Content-Length", "Content-Encoding", "Transfer-Encoding"}


def is_rate_limited(resp: requests.Response) -> bool:
    return (
        resp.status_code == 403
        and resp.headers.get(REMAINING_RATELIMIT_HEADER, "1") == "0"
    )


def proxy_request(
    path: str,
    request: werkzeug.Request,
    config: Config,
    rate_limited: Optional[RateLimited] = None,
    etag: Optional[str] = None,
    last_modified: Optional[str] = None,
) -> werkzeug.Response:
    if rate_limited is None:
        rate_limited = {}

    # filter request headers
    headers = {
        k: v for k, v in request.headers.items() if k not in REQUEST_FILTERED_HEADERS
    }

    # add cache headers
    if etag is not None:
        headers["If-None-Match"] = etag

    if last_modified is not None:
        headers["If-Modified-Since"] = last_modified

    for cred in credential_generator(config, rate_limited):
        logger.info("Using %s %s credential", cred.origin.value, cred.name)
        # add auth
        headers["Authorization"] = f"token {cred.token}"

        resp = requests.request(
            method=request.method.lower(),
            url=f'{config.github_api_url.rstrip("/")}/{path}',
            data=request.data,
            headers=headers,
            params=request.args.to_dict(),
        )

        if is_rate_limited(resp):
            reset_val = resp.headers.get(RESET_RATELIMIT_HEADER)
            if reset_val:
                reset = datetime.utcfromtimestamp(float(reset_val))
                rate_limited[(cred.origin, cred.name)] = reset
                # TODO: Emit OTEL metric
                logger.warning(
                    "%s %s credential is rate limited. Resetting at %s",
                    cred.origin.value,
                    cred.name,
                    reset,
                )
        else:
            # filter response headers
            for h in RESPONSE_FILTERED_HEADERS:
                resp.headers.pop(h, None)

            return werkzeug.Response(
                response=resp.text,
                status=resp.status_code,
                headers=resp.headers.items(),
            )

    raise RuntimeError("All available GitHub credentials are rate limited")
