import os
from time import time
from typing import Optional

import requests
import werkzeug
from prom_night import Registry  # type: ignore

from github_proxy.github_credentials import GitHubCredential
from github_proxy.ratelimit import get_ratelimit_limit
from github_proxy.ratelimit import get_ratelimit_remaining
from github_proxy.ratelimit import get_ratelimit_reset


class TelemetryCollector:
    def __init__(self) -> None:
        self._registry = Registry(
            default_labels={
                "service": os.getenv("SERVICE_NAME", "UNKNOWN"),
                "environment": os.getenv("ENV_NAME", "UNKNOWN"),
                "region": os.getenv("REGION_NAME", "UNKNOWN"),
            }
        )

    def collect_gh_response_metrics(
        self, cred: GitHubCredential, response: requests.Response
    ) -> None:
        metric = self._registry.gauge(
            metric_name="custon_github_ratelimit",
            credential_name=cred.name,
            credential_origin=cred.origin.value,
        )
        remaining = get_ratelimit_remaining(response)
        limit = get_ratelimit_limit(response)
        reset = get_ratelimit_reset(response)

        if remaining is not None:
            metric.labels(field="remaining").set(remaining)

        if limit is not None:
            metric.labels(field="limit").set(limit)

        if reset is not None:
            metric.labels(field="reset_timestamp").set(reset.timestamp())
            metric.labels(field="reset").set(max(0, reset.timestamp() - time()))

    def collect_proxy_request_metrics(
        self,
        client: str,
        request: werkzeug.Request,
        cache_hit: Optional[bool] = None,
    ) -> None:
        metric = self._registry.counter(
            metric_name="custom_github_proxy_request",
            client=client,
            http_method=request.method,
            cache_hit=cache_hit,
        )

        metric.inc()
