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
from github_proxy.proxy import Proxy
from github_proxy.telemetry import TelemetryCollector


@lru_cache
def get_config() -> Config:
    return Config()


@lru_cache
def get_tel_collector() -> TelemetryCollector:
    return TelemetryCollector()


@lru_cache
def get_proxy(config: Config, tel_collector: TelemetryCollector) -> Proxy:
    def time_to_use(_key: str, value: datetime, now: datetime) -> datetime:
        # Derives the expiration time of the added value.
        # The padding addition below is a safeguard accounting for
        # potential clock drift between the GitHub server and the proxy.
        return value + timedelta(minutes=config.github_creds_cache_ttl_padding)

    return Proxy(
        github_api_url=config.github_api_url,
        github_credentials_config=config,
        cache=CacheBackend.factory(config),
        rate_limited=TLRUCache(
            maxsize=config.github_creds_cache_maxsize,
            ttu=time_to_use,
            timer=datetime.now,
        ),
        tel_collector=tel_collector,
    )


T = TypeVar("T")


def inject_tel_collector(func: Callable[..., T]) -> Callable[..., T]:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        return func(*args, tel_collector=get_tel_collector(), **kwargs)

    return wrapper


def inject_proxy(func: Callable[..., T]) -> Callable[..., T]:
    """
    This decorator injects the `Proxy` instance singleton that provides
    callables for proxying requests to GitHub.
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        config = get_config()
        tel_collector = get_tel_collector()
        proxy = get_proxy(config, tel_collector)
        return func(*args, proxy=proxy, **kwargs)

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
