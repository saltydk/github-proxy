from typing import Optional

import werkzeug
from flask import Blueprint
from flask import request
from flask_httpauth import HTTPTokenAuth  # type: ignore

from github_proxy.dependencies import inject_proxy
from github_proxy.proxy import Proxy

blueprint = Blueprint("github_proxy", __name__)
auth = HTTPTokenAuth(scheme="token")


@auth.verify_token  # type: ignore
@inject_proxy
def verify_token(token: str, proxy: Proxy) -> Optional[str]:
    return proxy.auth(token, request)


@blueprint.route("/<path:path>", methods=["GET"])
@inject_proxy
@auth.login_required  # type: ignore
def caching_proxy(
    path: str,
    proxy: Proxy,
) -> werkzeug.Response:
    return proxy.cached_request(path, request, auth.current_user())


@blueprint.route("/<path:path>", methods=["POST", "PATCH", "PUT", "DELETE"])
@inject_proxy
@auth.login_required  # type: ignore
def proxy(
    path: str,
    proxy: Proxy,
) -> werkzeug.Response:
    return proxy.request(path, request, auth.current_user())
