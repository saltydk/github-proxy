import json
from typing import Optional
from typing import Sequence
from typing import Tuple

import werkzeug
from redis import Redis

from github_proxy.cache.backend import CacheBackend
from github_proxy.cache.backend import CacheBackendConfig
from github_proxy.cache.backend import Value

SerializedValue = Tuple[str, int, Sequence[Tuple[str, str]]]


def serialize_value(value: Value) -> SerializedValue:
    return (value.data.decode(), value.status_code, value.headers.to_wsgi_list())


def deserialize_value(value: SerializedValue) -> Value:
    data, status_code, headers = value
    return werkzeug.Response(
        response=data,
        status=status_code,
        headers=headers,
    )


class RedisCache(CacheBackend, scheme="redis"):
    def __init__(self, config: CacheBackendConfig):
        super().__init__(config)
        self._client = Redis.from_url(config.cache_backend_url, decode_responses=True)

    def _cached_key(self, resource: str, representation: str) -> str:
        return f"cached:{resource}:{representation}"

    def _get(self, resource: str, representation: str) -> Optional[Value]:
        json_serialized_value = self._client.get(
            self._cached_key(resource, representation)
        )
        if not json_serialized_value:
            return None

        serialized_value = json.loads(json_serialized_value)
        return deserialize_value(serialized_value)

    def _set(self, resource: str, representation: str, value: Value) -> None:
        serialized_value = serialize_value(value)

        self._client.setex(
            name=self._cached_key(resource, representation),
            value=json.dumps(serialized_value),
            time=self.config.cache_ttl,
        )


class SecureRedisCache(RedisCache, scheme="rediss"):
    pass
