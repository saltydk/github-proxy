import logging
from typing import Optional

import requests
import werkzeug

from github_proxy.cache.backend import CacheBackend
from github_proxy.github_credentials import GitHubCredentialsConfig
from github_proxy.github_credentials import RateLimited
from github_proxy.github_credentials import credential_generator
from github_proxy.ratelimit import get_ratelimit_reset
from github_proxy.ratelimit import is_rate_limited
from github_proxy.telemetry import TelemetryCollector

logger = logging.getLogger(__name__)


REQUEST_FILTERED_HEADERS = {"Connection", "Host"}
RESPONSE_FILTERED_HEADERS = {"Content-Length", "Content-Encoding", "Transfer-Encoding"}


class Proxy:
    def __init__(
        self,
        github_api_url: str,
        github_credentials_config: GitHubCredentialsConfig,
        cache: CacheBackend,
        rate_limited: RateLimited,
        tel_collector: TelemetryCollector,
    ) -> None:
        """
        :param github_api_url: Base url of the GitHub API server
        :param github_credentials_config: Config that collects all the available
                                          GitHub user PATs and GitHub Apps. This
                                          config object is used during GitHub token
                                          generation.
        :param cache: The purpose of this object is to cache the responses of the
                      GitHub API so that future requests on the same resources can be
                      served by the cache.
        :param rate_limited: Dictionary to store the GitHub credentials that are known
                             to be rate-limited so that the proxy skips them when
                             attempting to connect to GitHub. The `rate_limited` dict
                             should ideally be a TLRU cache so that credentials that
                             undergo a rate-limit reset, get automagically removed from
                             the dict.
        :param tel_collector: Object collecting telemetry metrics on various points
                              within the control flow.
        """
        self.github_api_url = github_api_url
        self.gh_cred_config = github_credentials_config
        self.cache = cache
        self.rate_limited = rate_limited
        self.tel_collector = tel_collector

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
        logger.info(
            "%s client requesting %s %s, with Etag: %s, Last-Modified: %s",
            client,
            path,
            media_type,
            request.headers.get("If-None-Match"),
            request.headers.get("If-Modified-Since"),
        )

        # The requested media type MUST be combined with the path
        # when indexing cached resources. The GitHub API may return a
        # completely different response based on the requested MIME type.
        # See more: https://docs.github.com/en/rest/overview/media-types
        cached_response = self.cache.get(path, media_type)

        if cached_response is None:  # cache miss
            resp = self._send_gh_request(path, request)
            etag_value, _ = resp.get_etag()
            if etag_value or resp.last_modified:
                # TODO: Writing to cache should happen asyncronously
                self.cache.set(path, media_type, resp)

            self.tel_collector.collect_proxy_request_metrics(
                client, request, cache_hit=False
            )
            return resp

        # conditional request
        resp = self._send_gh_request(
            path,
            request,
            etag=cached_response.headers.get("Etag"),
            last_modified=cached_response.headers.get("Last-Modified"),
        )
        if resp.status_code != 304:
            self.cache.set(path, media_type, resp)
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

        for cred in credential_generator(
            self.github_api_url, self.gh_cred_config, self.rate_limited
        ):
            logger.info("Using %s %s credential", cred.origin.value, cred.name)
            # Adding auth
            headers["Authorization"] = f"token {cred.token}"

            resp = requests.request(
                method=request.method.lower(),
                url=f'{self.github_api_url.rstrip("/")}/{path}',
                data=request.data,
                headers=headers,
                params=request.args.to_dict(),
            )
            self.tel_collector.collect_gh_response_metrics(cred, resp)

            if is_rate_limited(resp):
                reset = get_ratelimit_reset(resp)
                if reset:
                    self.rate_limited[(cred.origin, cred.name)] = reset
                    logger.warning(
                        "%s %s credential is rate limited. Resetting at %s",
                        cred.origin.value,
                        cred.name,
                        reset,
                    )
            else:
                # Filter response headers
                for h in RESPONSE_FILTERED_HEADERS:
                    resp.headers.pop(h, None)

                return werkzeug.Response(
                    response=resp.text,
                    status=resp.status_code,
                    headers=resp.headers.items(),
                )

        raise RuntimeError("All available GitHub credentials are rate limited")

    def health(self) -> bool:
        resp = self.cached_request("zen", werkzeug.Request.from_values(), "healthcheck")
        return resp.status_code == 200
