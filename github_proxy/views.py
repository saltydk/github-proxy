import werkzeug
from flask import Blueprint
from flask import request

from github_proxy.cache.backend import CacheBackend
from github_proxy.config import Config
from github_proxy.dependencies import inject_cache
from github_proxy.dependencies import inject_config
from github_proxy.proxy import proxy_request

blueprint = Blueprint("github_proxy", __name__)


@blueprint.route("/<path:path>", methods=["GET"])
@inject_cache
@inject_config
def caching_proxy(path: str, config: Config, cache: CacheBackend) -> werkzeug.Response:
    cached_response = cache.get(path)

    if cached_response is None:  # cache miss
        resp = proxy_request(request, config=config)
        etag_value, _ = resp.get_etag()
        if etag_value or resp.last_modified:
            # TODO: Writing to cache should happen asyncronously
            cache.set(path, resp)

        return resp

    # conditional request
    resp = proxy_request(
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
@inject_config
def proxy(path: str, config: Config) -> werkzeug.Response:
    return proxy_request(request, config)
