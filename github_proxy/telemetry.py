from abc import ABC
from abc import abstractmethod
from typing import ClassVar
from typing import MutableMapping
from typing import Optional
from typing import Type

import requests
import werkzeug

from github_proxy.github_tokens import GitHubToken


class TelemetryCollector(ABC):
    _registry: ClassVar[MutableMapping[str, Type["TelemetryCollector"]]] = {}
    type_: ClassVar[str]

    def __init_subclass__(cls, type_: str) -> None:
        cls._registry[type_] = cls
        cls.type_ = type_

    @abstractmethod
    def collect_gh_response_metrics(
        self, token: GitHubToken, response: requests.Response
    ) -> None:
        ...

    @abstractmethod
    def collect_proxy_request_metrics(
        self,
        client: str,
        request: werkzeug.Request,
        cache_hit: Optional[bool] = None,
    ) -> None:
        ...

    @classmethod
    def from_type(cls, type_: str) -> "TelemetryCollector":
        if type_ not in cls._registry:
            raise RuntimeError(f"{type_} telemetry collector not found")

        return cls._registry[type_]()


class NoopTelemetryCollector(TelemetryCollector, type_="noop"):
    pass
