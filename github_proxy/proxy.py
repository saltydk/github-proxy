import logging
from typing import Optional

import requests
import werkzeug

from github_proxy.cache.backend import CacheBackend
from github_proxy.config import Config
from github_proxy.github_credentials import RateLimited
from github_proxy.github_credentials import credential_generator
from github_proxy.ratelimit import get_ratelimit_reset
from github_proxy.ratelimit import is_rate_limited
from github_proxy.telemetry import TelemetryCollector

logger = logging.getLogger(__name__)


REQUEST_FILTERED_HEADERS = {"Connection", "Host"}
RESPONSE_FILTERED_HEADERS = {"Content-Length", "Content-Encoding", "Transfer-Encoding"}


def proxy_request(
    path: str,
    request: werkzeug.Request,
    client: str,
    config: Config,
    rate_limited: RateLimited,
    tel_collector: TelemetryCollector,
) -> werkzeug.Response:
    logger.info("%s client requesting %s %s", client, request.method, path)
    tel_collector.collect_proxy_request_metrics(client, request)
    return send_gh_request(path, request, config, rate_limited, tel_collector)


def proxy_cached_request(
    path: str,
    request: werkzeug.Request,
    client: str,
    config: Config,
    cache: CacheBackend,
    rate_limited: RateLimited,
    tel_collector: TelemetryCollector,
) -> werkzeug.Response:
    logger.info(
        "%s client requesting %s, with Etag: %s, Last-Modified: %s",
        client,
        path,
        request.headers.get("If-None-Match"),
        request.headers.get("If-Modified-Since"),
    )

    cached_response = cache.get(path)

    if cached_response is None:  # cache miss
        resp = send_gh_request(
            path,
            request,
            config=config,
            rate_limited=rate_limited,
            tel_collector=tel_collector,
        )
        etag_value, _ = resp.get_etag()
        if etag_value or resp.last_modified:
            # TODO: Writing to cache should happen asyncronously
            cache.set(path, resp)

        tel_collector.collect_proxy_request_metrics(client, request, cache_hit=False)
        return resp

    # conditional request
    resp = send_gh_request(
        path,
        request,
        config=config,
        rate_limited=rate_limited,
        tel_collector=tel_collector,
        etag=cached_response.headers.get("Etag"),
        last_modified=cached_response.headers.get("Last-Modified"),
    )
    if resp.status_code != 304:
        cache.set(path, resp)
        tel_collector.collect_proxy_request_metrics(client, request, cache_hit=False)
        return resp

    tel_collector.collect_proxy_request_metrics(client, request, cache_hit=True)
    return cached_response  # cache hit


def send_gh_request(
    path: str,
    request: werkzeug.Request,
    config: Config,
    rate_limited: RateLimited,
    tel_collector: TelemetryCollector,
    etag: Optional[str] = None,
    last_modified: Optional[str] = None,
) -> werkzeug.Response:
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
        tel_collector.collect_gh_response_metrics(cred, resp)

        if is_rate_limited(resp):
            reset = get_ratelimit_reset(resp)
            if reset:
                rate_limited[(cred.origin, cred.name)] = reset
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
