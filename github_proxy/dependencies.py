from functools import lru_cache
from functools import wraps
from typing import Any
from typing import Callable
from typing import TypeVar

from github_proxy.cache.backend import CacheBackend
from github_proxy.config import Config


@lru_cache
def get_config() -> Config:
    return Config()


@lru_cache
def get_cache(config: Config) -> CacheBackend:
    cache_backend = CacheBackend.from_url(config.cache_backend_url)
    return cache_backend(config)


T = TypeVar("T")


def inject_config(func: Callable[..., T]) -> Callable[..., T]:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        config = get_config()
        return func(*args, config=config, **kwargs)

    return wrapper


def inject_cache(func: Callable[..., T]) -> Callable[..., T]:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        config = get_config()
        cache = get_cache(config)
        return func(*args, cache=cache, **kwargs)

    return wrapper


def inject_tokens(func: Callable[..., T]) -> Callable[..., T]:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        config = get_config()
        return func(*args, tokens=config.tokens, **kwargs)

    return wrapper
