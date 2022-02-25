import json
from typing import ItemsView, Optional, Tuple, TypedDict

import werkzeug
from redis import Redis

from github_proxy.cache.backend import CacheBackend, CacheBackendConfig, Value


class HashValue(TypedDict):
    etag: str
    response_object: str


class RedisCache(CacheBackend, scheme="redis"):
    def __init__(self, config: CacheBackendConfig):
        super().__init__(config)
        self._client = Redis.from_url(config.cache_backend_url, decode_responses=True)

    def _cached_key(self, key_suffix: str) -> str:
        return f"cached:{key_suffix}"

    def get(self, key: str) -> Optional[Value]:
        hash_value = self._client.hgetall(self._cached_key(key))
        if not hash_value:
            return None

        data, status_code, headers = json.loads(hash_value["response_object"])

        return (
            werkzeug.Response(
                response=data,
                status=status_code,
                headers=headers,
            ),
            hash_value["etag"],
        )

    def set(self, key: str, value: Value) -> None:
        serialised_data = value[0].data.decode()
        serialised_status = value[0].status_code
        serialised_headers = value[0].headers.to_wsgi_list()

        self._client.hset(
            name=self._cached_key(key),
            mapping=HashValue(
                response_object=json.dumps(
                    [serialised_data, serialised_status, serialised_headers]
                ),
                etag=value[1],
            ),
        )
