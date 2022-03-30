import logging
from abc import ABC
from abc import abstractmethod
from typing import ClassVar
from typing import MutableMapping
from typing import Optional
from typing import Protocol
from typing import Type
from urllib.parse import urlparse

import werkzeug

logger = logging.getLogger(__name__)

Value = werkzeug.Response


class CacheBackendConfig(Protocol):
    cache_backend_url: str
    cache_ttl: int


class CacheBackend(ABC):
    scheme: ClassVar[str]
    _registry: ClassVar[MutableMapping[str, Type["CacheBackend"]]] = {}

    def __init_subclass__(cls, scheme: str):
        cls.scheme = scheme
        cls._registry[scheme] = cls

    def __init__(self, config: CacheBackendConfig):
        self.config = config

    @abstractmethod
    def _get(self, resource: str, representation: str) -> Optional[Value]:
        ...

    @abstractmethod
    def _set(self, resource: str, representation: str, value: Value) -> None:
        ...

    def get(self, resource: str, representation: str) -> Optional[Value]:
        try:
            return self._get(resource, representation)
        except Exception as e:
            logger.error(
                "Failed retrieving %s %s with error: %s", resource, representation, e
            )
            return None

    def set(self, resource: str, representation: str, value: Value) -> None:
        try:
            self._set(resource, representation, value)
        except Exception as e:
            logger.error(
                "Failed setting %s with error: %s", resource, representation, e
            )

    @classmethod
    def factory(cls, config: CacheBackendConfig) -> "CacheBackend":
        url_parse_result = urlparse(config.cache_backend_url)

        if url_parse_result.scheme not in cls._registry:
            raise RuntimeError(f"Cache backend {url_parse_result.scheme} not found")

        return cls._registry[url_parse_result.scheme](config)
