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
    def _get(self, key: str) -> Optional[Value]:
        ...

    @abstractmethod
    def _set(self, key: str, value: Value) -> None:
        ...

    @abstractmethod
    def _make_key(
        self, resource: str, filter_: Optional[str], representation: str
    ) -> str:
        ...

    def get(
        self, resource: str, filter_: Optional[str], representation: str
    ) -> Optional[Value]:
        key = self._make_key(resource, filter_, representation)
        try:
            return self._get(key)
        except Exception as e:
            logger.error("Failed retrieving %s with error: %s", key, e)
            return None

    def set(
        self, resource: str, filter_: Optional[str], representation: str, value: Value
    ) -> None:
        key = self._make_key(resource, filter_, representation)
        try:
            self._set(key, value)
        except Exception as e:
            logger.error("Failed setting %s with error: %s", key, e)

    @classmethod
    def factory(cls, config: CacheBackendConfig) -> "CacheBackend":
        url_parse_result = urlparse(config.cache_backend_url)

        if url_parse_result.scheme not in cls._registry:
            raise RuntimeError(f"Cache backend {url_parse_result.scheme} not found")

        return cls._registry[url_parse_result.scheme](config)
