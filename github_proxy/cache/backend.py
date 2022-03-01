from abc import ABC
from abc import abstractmethod
from typing import ClassVar
from typing import MutableMapping
from typing import Optional
from typing import Protocol
from typing import Tuple
from typing import Type
from urllib.parse import urlparse

import werkzeug


class CacheBackendConfig(Protocol):
    cache_backend_url: str
    cache_ttl: int


Value = Tuple[werkzeug.Response, str]


class CacheBackend(ABC):
    scheme: ClassVar[str]
    _registry: ClassVar[MutableMapping[str, Type["CacheBackend"]]] = {}

    def __init_subclass__(cls, scheme: str):
        cls.scheme = scheme
        cls._registry[scheme] = cls

    def __init__(self, config: CacheBackendConfig):
        self.config = config

    @abstractmethod
    def get(self, key: str) -> Optional[Value]:
        ...

    @abstractmethod
    def set(self, key: str, value: Value) -> None:
        ...

    @classmethod
    def from_url(cls, url: str) -> Type["CacheBackend"]:
        url_parse_result = urlparse(url)

        if url_parse_result.scheme not in cls._registry:
            raise RuntimeError(f"Cache backend {url_parse_result.scheme} not found")

        return cls._registry[url_parse_result.scheme]
