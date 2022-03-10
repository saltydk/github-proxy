import socket
from datetime import datetime
from datetime import timedelta
from typing import Callable
from typing import Tuple
from unittest.mock import Mock

import pytest
from faker import Faker
from github.InstallationAuthorization import InstallationAuthorization

from github_proxy.cache import InMemoryCache
from github_proxy.cache.backend import CacheBackend
from github_proxy.config import Config
from github_proxy.config import GitHubAppConfig

_true_socket = socket.socket


def disable_socket() -> None:
    """Disable the internet"""

    def guarded(*args, **kwargs):
        raise RuntimeError("A unit test tried to connect to the internet.")

    socket.socket = guarded  # type: ignore


def enable_socket() -> None:
    """Re-enable the internet"""
    socket.socket = _true_socket  # type: ignore


@pytest.fixture(autouse=True)
def socket_disabled():
    """
    Disable socket.socket for the duration of this test function.
    Ensures that no actual provider will be used within any of the tests.
    """
    disable_socket()
    yield
    enable_socket()


@pytest.fixture
def github_app_config_factory(faker: Faker) -> Callable[..., GitHubAppConfig]:
    def factory(
        id_: str = str(faker.pyint()),
        installation_id: int = faker.pyint(),
        private_key: str = faker.pystr(),
    ) -> GitHubAppConfig:
        return GitHubAppConfig(
            id_=id_, installation_id=installation_id, private_key=private_key
        )

    return factory


@pytest.fixture
def github_app_config(
    github_app_config_factory: Callable[..., GitHubAppConfig]
) -> GitHubAppConfig:
    return github_app_config_factory()


@pytest.fixture
def config_factory(
    faker: Faker, github_app_config: GitHubAppConfig
) -> Callable[..., Config]:
    def factory(
        app_name: str = faker.word(),
        app_config: GitHubAppConfig = github_app_config,
        pat: Tuple[str, str] = (faker.word(), faker.pystr()),
    ) -> Config:
        return Mock(  # type: ignore
            github_apps={app_name: app_config},
            github_pats={pat[0]: pat[1]},
            github_api_url=faker.url(),
            github_creds_cache_ttl_padding=0,
            github_creds_cache_maxsize=512,
            cache_ttl=3600,
        )

    return factory


@pytest.fixture
def config(config_factory: Callable[..., Config]) -> Config:
    return config_factory()


@pytest.fixture
def installation_authz_factory() -> Callable[..., InstallationAuthorization]:
    def factory(token: str) -> InstallationAuthorization:
        return InstallationAuthorization(
            requester=None,
            headers={},
            attributes={
                "token": token,
                "expires_at": (datetime.utcnow() + timedelta(days=3)).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
            },
            completed=True,
        )

    return factory


@pytest.fixture
def cache_backend(config: Config) -> CacheBackend:
    return InMemoryCache(config)
