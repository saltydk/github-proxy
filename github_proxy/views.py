import logging
from typing import Mapping
from typing import Optional

import werkzeug
from flask import Blueprint
from flask import request
from flask_httpauth import HTTPTokenAuth  # type: ignore

from github_proxy.cache.backend import CacheBackend
from github_proxy.config import Config
from github_proxy.dependencies import inject_cache
from github_proxy.dependencies import inject_config
from github_proxy.dependencies import inject_tokens
from github_proxy.proxy import proxy_request

logger = logging.getLogger(__name__)


blueprint = Blueprint("github_proxy", __name__)
auth = HTTPTokenAuth(scheme="token")


@auth.verify_token  # type: ignore
@inject_tokens
def verify_token(token: str, tokens: Mapping[str, str]) -> Optional[str]:
    return tokens.get(token)


@blueprint.route("/<path:path>", methods=["GET"])
@inject_cache
@inject_config
@auth.login_required  # type: ignore
def caching_proxy(path: str, config: Config, cache: CacheBackend) -> werkzeug.Response:
    logger.info(
        "%s client requesting %s, with Etag: %s, Last-Modified: %s",
        auth.current_user(),
        path,
        request.headers.get("If-None-Match"),
        request.headers.get("If-Modified-Since"),
    )
    cached_response = cache.get(path)

    if cached_response is None:  # cache miss
        resp = proxy_request(path, request, config=config)
        etag_value, _ = resp.get_etag()
        if etag_value or resp.last_modified:
            # TODO: Writing to cache should happen asyncronously
            cache.set(path, resp)

        return resp

    # conditional request
    resp = proxy_request(
        path,
        request,
        config=config,
        etag=cached_response.headers.get("Etag"),
        last_modified=cached_response.headers.get("Last-Modified"),
    )
    if resp.status_code != 304:
        cache.set(path, resp)

        return resp

    return cached_response  # cache hit


@blueprint.route("/<path:path>", methods=["POST", "PATCH", "PUT", "DELETE"])
@auth.login_required  # type: ignore
@inject_config
def proxy(path: str, config: Config) -> werkzeug.Response:
    logger.info("%s client requesting %s", auth.current_user(), path)
    return proxy_request(path, request, config)
