from datetime import datetime
from datetime import timedelta
from functools import lru_cache
from functools import wraps
from typing import Any
from typing import Callable
from typing import TypeVar

from cachetools import TLRUCache  # type: ignore

from github_proxy.cache.backend import CacheBackend
from github_proxy.config import Config
from github_proxy.github_credentials import RateLimited
from github_proxy.telemetry import TelemetryCollector


@lru_cache
def get_config() -> Config:
    return Config()


@lru_cache
def get_cache(config: Config) -> CacheBackend:
    cache_backend = CacheBackend.from_url(config.cache_backend_url)
    return cache_backend(config)


@lru_cache
def get_rate_limited(config: Config) -> RateLimited:
    def time_to_use(_key: str, value: datetime, now: datetime) -> datetime:
        # Derives the expiration time of the added value.
        # The padding addition below is a safeguard accounting for
        # potential clock drift between the GitHub server and the proxy.
        return value + timedelta(minutes=config.github_creds_cache_ttl_padding)

    return TLRUCache(  # type: ignore
        maxsize=config.github_creds_cache_maxsize,
        ttu=time_to_use,
        timer=datetime.now,
    )


@lru_cache
def get_tel_collector() -> TelemetryCollector:
    return TelemetryCollector()


T = TypeVar("T")


def inject_config(func: Callable[..., T]) -> Callable[..., T]:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        config = get_config()
        return func(*args, config=config, **kwargs)

    return wrapper


def inject_cache(func: Callable[..., T]) -> Callable[..., T]:
    """
    This decorator injects the `CacheBackend` object that is used to
    store GitHub responses.
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        config = get_config()
        cache = get_cache(config)
        return func(*args, cache=cache, **kwargs)

    return wrapper


def inject_tokens(func: Callable[..., T]) -> Callable[..., T]:
    """
    This decorator injects the `tokens` dictionary that maps
    proxy client tokens to client names. This dictionary is used
    for authenticating all incoming proxy requests.
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        config = get_config()
        return func(*args, tokens=config.tokens, **kwargs)

    return wrapper


def inject_rate_limited(func: Callable[..., T]) -> Callable[..., T]:
    """
    This decorator injects the `rate_limited` cache dictionary.
    The purpose of the `rate_limited` dictionary is to store the
    GitHub credentials that are known to be rate-limited so that
    the proxy skips them when attempting to connect to GitHub.
    The `rate_limited` dict is a TLRU cache. Credentials that undergo
    a rate-limit reset, are automagically removed from the dict.
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        config = get_config()
        rate_limited = get_rate_limited(config)
        return func(*args, rate_limited=rate_limited, **kwargs)

    return wrapper


def inject_tel_collector(func: Callable[..., T]) -> Callable[..., T]:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        return func(*args, tel_collector=get_tel_collector(), **kwargs)

    return wrapper
