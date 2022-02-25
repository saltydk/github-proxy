from typing import Mapping, Optional

from cachetools import TTLCache

from github_proxy.cache.backend import CacheBackend, CacheBackendConfig, Value


class InMemoryCache(CacheBackend, scheme="inmemory"):
    def __init__(self, config: CacheBackendConfig):
        super().__init__(config)
        self._store: TTLCache[str, Value] = TTLCache(
            maxsize=1024, ttl=self.config.cache_ttl
        )

    def get(self, key: str) -> Optional[Value]:
        return self._store.get(key)

    def set(self, key: str, value: Value) -> None:
        self._store[key] = value
