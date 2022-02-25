from injector import Binder, Injector, Module, provider, singleton

from github_proxy.cache import CacheBackend
from github_proxy.config import Config


def configure_config(binder: Binder) -> None:
    binder.bind(Config, to=Config(), scope=singleton)


class CacheBackendModule(Module):
    @singleton
    @provider
    def provide_cache_backend(self, config: Config) -> CacheBackend:
        backend_cls = CacheBackend.from_url(config.cache_backend_url)
        return backend_cls(config)


dep_injector = Injector([configure_config, CacheBackendModule])
