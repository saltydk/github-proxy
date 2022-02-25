from typing import Optional

import requests
import werkzeug
from flask import Blueprint, request

from github_proxy.cache.backend import CacheBackend
from github_proxy.config import Config
from github_proxy.dependencies import dep_injector

blueprint = Blueprint("github_proxy", __name__)


def proxy_request(
    request: werkzeug.Request, config: Config, etag: Optional[str] = None
) -> werkzeug.Response:
    # filter request headers
    headers = {
        k: v for k, v in request.headers.items() if k not in {"Connectinon", "Host"}
    }

    # add auth
    headers["Authorization"] = f"token {config.github_pat}"

    # add cache headers
    if etag is not None:
        headers["If-None-Match"] = etag

    resp = requests.request(
        method=request.method.lower(),
        url=config.github_api_url.rstrip("/") + request.path,
        data=request.data,
        headers=headers,
        params=request.args.to_dict(),
    )

    # filter response headers
    for h in {"Content-Length", "Content-Encoding", "Transfer-Encoding"}:
        resp.headers.pop(h, None)

    return werkzeug.Response(
        response=resp.text,
        status=resp.status_code,
        headers=resp.headers.items(),
    )


@blueprint.route("/<path:path>", methods=["GET"])
def caching_proxy(path: str) -> werkzeug.Response:
    config = dep_injector.get(Config)
    cache = dep_injector.get(CacheBackend)

    cached_value = cache.get(path)

    if cached_value is None:
        resp = proxy_request(request, config=config)
        etag = resp.headers.get("Etag") # TODO: Need to also handle the `Last-Modified` header
        if etag is not None:
            cache.set(path, (resp, etag))

        return resp

    cached_resp, cached_etag = cached_value

    # conditional request
    resp = proxy_request(request, config=config, etag=cached_etag)

    if resp.status_code != 304:
        new_etag = resp.headers.get("Etag")
        if new_etag is not None:
            cache.set(path, (resp, new_etag))

        return resp

    return cached_resp


@blueprint.route("/<path:path>", methods=["POST", "PATCH", "PUT", "DELETE"])
def proxy(path: str) -> werkzeug.Response:
    config = dep_injector.get(Config)
    return proxy_request(request, config)
