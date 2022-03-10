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
from github_proxy.dependencies import inject_rate_limited
from github_proxy.dependencies import inject_tel_collector
from github_proxy.dependencies import inject_tokens
from github_proxy.github_credentials import RateLimited
from github_proxy.proxy import proxy_cached_request
from github_proxy.proxy import proxy_request
from github_proxy.telemetry import TelemetryCollector

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
@inject_rate_limited
@inject_tel_collector
@auth.login_required  # type: ignore
def caching_proxy(
    path: str,
    config: Config,
    cache: CacheBackend,
    rate_limited: RateLimited,
    tel_collector: TelemetryCollector,
) -> werkzeug.Response:
    return proxy_cached_request(
        path, request, auth.current_user(), config, cache, rate_limited, tel_collector
    )


@blueprint.route("/<path:path>", methods=["POST", "PATCH", "PUT", "DELETE"])
@inject_config
@inject_rate_limited
@inject_tel_collector
@auth.login_required  # type: ignore
def proxy(
    path: str,
    config: Config,
    rate_limited: RateLimited,
    tel_collector: TelemetryCollector,
) -> werkzeug.Response:
    return proxy_request(
        path, request, auth.current_user(), config, rate_limited, tel_collector
    )
