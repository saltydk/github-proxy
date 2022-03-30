from typing import Optional

from cachetools import TTLCache

from github_proxy.cache.backend import CacheBackend
from github_proxy.cache.backend import CacheBackendConfig
from github_proxy.cache.backend import Value


class InMemoryCache(CacheBackend, scheme="inmemory"):
    """Useful for testing purposes"""

    def __init__(self, config: CacheBackendConfig):
        super().__init__(config)
        self._store: TTLCache[str, Value] = TTLCache(
            maxsize=1024, ttl=self.config.cache_ttl
        )

    def _cached_key(self, resource: str, representation: str) -> str:
        return f"{resource}/{representation}"

    def _get(self, resource: str, representation: str) -> Optional[Value]:
        return self._store.get(self._cached_key(resource, representation))

    def _set(self, resource: str, representation: str, value: Value) -> None:
        self._store[self._cached_key(resource, representation)] = value
