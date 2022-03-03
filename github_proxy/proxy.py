from typing import Optional

import requests
import werkzeug

from github_proxy.config import Config


def proxy_request(
    path: str,
    request: werkzeug.Request,
    config: Config,
    etag: Optional[str] = None,
    last_modified: Optional[str] = None,
) -> werkzeug.Response:
    # filter request headers
    headers = {
        k: v for k, v in request.headers.items() if k not in {"Connection", "Host"}
    }

    # add auth
    headers["Authorization"] = f"token {config.github_pat}"

    # add cache headers
    if etag is not None:
        headers["If-None-Match"] = etag

    if last_modified is not None:
        headers["If-Modified-Since"] = last_modified

    resp = requests.request(
        method=request.method.lower(),
        url=f'{config.github_api_url.rstrip("/")}/{path}',
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
