import logging
import re
from dataclasses import dataclass
from functools import cached_property
from typing import Mapping
from typing import Optional
from typing import Sequence

import requests
import werkzeug

from github_proxy.cache.backend import CacheBackend
from github_proxy.github_tokens import GitHubTokenConfig
from github_proxy.github_tokens import InstalledIntegration
from github_proxy.github_tokens import RateLimited
from github_proxy.github_tokens import construct_installed_integration
from github_proxy.github_tokens import token_generator
from github_proxy.ratelimit import get_ratelimit_reset
from github_proxy.ratelimit import is_rate_limited
from github_proxy.telemetry import TelemetryCollector

logger = logging.getLogger(__name__)


# As per RFC 2616 https://datatracker.ietf.org/doc/html/rfc2616#section-13.5.1
# hop-by-hop headers must not be forwarded by the proxy
HOP_BY_HOP_HEADERS = {
    "Connection",
    "Proxy-Connection",
    "Keep-Alive",
    "Transfer-Encoding",
    "TE",
    "Te",
    "Trailer",
    "Upgrade",
    "Proxy-Authorization",
    "Proxy-Authenticate",
}

# The host header should be automatically rewritten to the URL of the request target
# (ie api.github.com)
REQUEST_FILTERED_HEADERS = {"Host", *HOP_BY_HOP_HEADERS}

# Content-Length and Encoding headers are removed to prevent bad framing
RESPONSE_FILTERED_HEADERS = {"Content-Length", "Content-Encoding", *HOP_BY_HOP_HEADERS}

MATCH_ALL = re.compile(r".*")


@dataclass
class ProxyClientScope:
    method: re.Pattern = MATCH_ALL  # type: ignore
    path: re.Pattern = MATCH_ALL  # type: ignore


@dataclass
class ProxyClient:
    token: str
    name: str
    scopes: Sequence[ProxyClientScope] = (ProxyClientScope(),)


def validate_clients(clients: Sequence[ProxyClient]) -> None:
    taken_tokens = set()
    taken_names = set()
    for client in clients:
        if client.token in taken_tokens:
            raise ValueError("Duplicate client token found")

        if client.name in taken_names:
            raise ValueError(f"Duplicate client name found: {client.name}")

        taken_tokens.add(client.token)
        taken_names.add(client.name)


class Proxy:
    def __init__(
        self,
        github_api_url: str,
        github_token_config: GitHubTokenConfig,
        cache: CacheBackend,
        rate_limited: RateLimited,
        tel_collector: TelemetryCollector,
        clients: Sequence[ProxyClient] = (),
    ) -> None:
        """
        :param github_api_url: Base url of the GitHub API server
        :param github_token_config: Config that collects all the available
                                          GitHub user PATs and GitHub Apps. This
                                          config object is used during GitHub token
                                          generation.
        :param cache: The purpose of this object is to cache the responses of the
                      GitHub API so that future requests on the same resources can be
                      served by the cache.
        :param rate_limited: Dictionary to store the GitHub tokens that are known
                             to be rate-limited so that the proxy skips them when
                             attempting to connect to GitHub. The `rate_limited` dict
                             should ideally be a TLRU cache so that tokens that
                             undergo a rate-limit reset, get automagically removed from
                             the dict.
        :param tel_collector: Object collecting telemetry metrics on various points
                              within the control flow.
        """
        self.github_api_url = github_api_url
        self.gh_token_config = github_token_config
        validate_clients(clients)
        self.client_tokens = {
            client.token: (client.name, client.scopes) for client in clients
        }
        self.cache = cache
        self.rate_limited = rate_limited
        self.tel_collector = tel_collector

        # Since all proxy transactions eventually hit the same GitHub host, it is
        # preferred to re-use TCP connections (connection pooling). The requests.Session
        # object offers this functionality, however it also persists Cookies across
        # requests, which could lead to cookies being shared across completely separate
        # clients.
        # As of today, the GitHub REST API does not make any use of cookies,
        # hence it is safe to use a single cookie persisting session across all clients.
        # If this changes in the future, we could switch to having a session per client.
        self.requester = requests.Session()

    def auth(self, token: str, request: werkzeug.Request) -> Optional[str]:
        if token in self.client_tokens:
            name, scopes = self.client_tokens[token]

            request_path = request.path[len("/api/v3") :]

            for scope in scopes:
                method_match = scope.method.match(
                    request.method.lower()
                ) or scope.method.match(request.method.upper())
                if method_match and scope.path.match(request_path):
                    return name

        return None

    @cached_property
    def integrations(self) -> Mapping[str, InstalledIntegration]:
        return {
            app_name: construct_installed_integration(
                app_name, self.gh_token_config, self.github_api_url
            )
            for app_name in self.gh_token_config.github_apps
        }

    def request(
        self, path: str, request: werkzeug.Request, client: str
    ) -> werkzeug.Response:
        logger.info("%s client requesting %s %s", client, request.method, path)
        self.tel_collector.collect_proxy_request_metrics(client, request)
        return self._send_gh_request(path, request)

    def cached_request(
        self, path: str, request: werkzeug.Request, client: str
    ) -> werkzeug.Response:
        media_type = request.accept_mimetypes.best
        qs = request.query_string.decode() or None
        logger.info(
            "%s client requesting %s %s %s, with Etag: %s, Last-Modified: %s",
            client,
            path,
            qs,
            media_type,
            request.headers.get("If-None-Match"),
            request.headers.get("If-Modified-Since"),
        )

        # The requested media type MUST be combined with the path and the
        # query string when indexing cached resources. The GitHub API may return
        # a completely different response based on the requested MIME type.
        # See more: https://docs.github.com/en/rest/overview/media-types
        cached_response = self.cache.get(path, qs, media_type)

        if cached_response is None:  # cache miss
            resp = self._send_gh_request(path, request)
            etag_value, _ = resp.get_etag()
            cache_hit = None

            if etag_value or resp.last_modified:
                # TODO: Writing to cache should happen asyncronously
                self.cache.set(path, qs, media_type, resp)
                # cache miss can only happen if resource is cacheable:
                cache_hit = False

            self.tel_collector.collect_proxy_request_metrics(client, request, cache_hit)
            return resp

        # conditional request
        resp = self._send_gh_request(
            path,
            request,
            etag=cached_response.headers.get("Etag"),
            last_modified=cached_response.headers.get("Last-Modified"),
        )
        if resp.status_code != 304:
            self.cache.set(path, qs, media_type, resp)
            self.tel_collector.collect_proxy_request_metrics(
                client, request, cache_hit=False
            )
            return resp

        self.tel_collector.collect_proxy_request_metrics(
            client, request, cache_hit=True
        )
        return cached_response  # cache hit

    def _send_gh_request(
        self,
        path: str,
        request: werkzeug.Request,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None,
    ) -> werkzeug.Response:
        # Filter request headers
        headers = {
            k: v
            for k, v in request.headers.items()
            if k not in REQUEST_FILTERED_HEADERS
        }

        # Adding cache headers:
        # Note that it is not necessary to send both cache headers.
        # It is preferred to send only the If-Modified-Since header (if available),
        # since it can be reused across different GitHub tokens.
        # Etags on the other hand, are token specific.
        # For example, if the token of a GitHub app is renewed,
        # it cannot reuse the Etags of the previous expired token (whereas
        # the Last-Modified timestamp would still work).
        if last_modified is not None:
            headers["If-Modified-Since"] = last_modified
        elif etag is not None:
            headers["If-None-Match"] = etag

        for token in token_generator(
            self.integrations, self.gh_token_config.github_pats, self.rate_limited
        ):
            logger.info("Using %s %s token", token.origin.value, token.name)
            # Adding auth
            headers["Authorization"] = f"token {token.value}"

            resp = self.requester.request(
                method=request.method.lower(),
                url=f'{self.github_api_url.rstrip("/")}/{path}',
                data=request.data,
                headers=headers,
                params=request.args.to_dict(),
            )
            self.tel_collector.collect_gh_response_metrics(token, resp)

            if is_rate_limited(resp):
                reset = get_ratelimit_reset(resp)
                if reset:
                    self.rate_limited[(token.origin, token.name)] = reset
                    logger.warning(
                        "%s %s is rate limited. Resetting at %s",
                        token.origin.value,
                        token.name,
                        reset,
                    )
            else:
                # Filter response headers
                for h in RESPONSE_FILTERED_HEADERS:
                    resp.headers.pop(h, None)

                return werkzeug.Response(
                    response=resp.content,
                    status=resp.status_code,
                    headers=resp.headers.items(),
                )

        raise RuntimeError("All available GitHub tokens are rate limited")

    def health(self) -> bool:
        resp = self.cached_request("zen", werkzeug.Request.from_values(), "healthcheck")
        return resp.status_code == 200
