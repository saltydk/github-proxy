from datetime import datetime
from datetime import timedelta
from typing import Callable
from unittest import mock

import pytest
from cachetools import _methodkey  # type: ignore
from faker import Faker
from github import GithubIntegration
from github.InstallationAuthorization import InstallationAuthorization

from github_proxy.config import Config
from github_proxy.github_credentials import CachedGithubIntegration
from github_proxy.github_credentials import GitHubCredentialOrigin
from github_proxy.github_credentials import credential_generator


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


@mock.patch.object(GithubIntegration, "get_access_token")
def test_credentials_generator_cache_miss(
    create_token_mock: mock.Mock,
    config: Config,
    faker: Faker,
    installation_authz_factory: Callable[..., InstallationAuthorization],
):
    mock_token = faker.pystr()
    create_token_mock.return_value = installation_authz_factory(mock_token)
    creds = credential_generator(config.github_api_url, config, {})

    app_cred = next(creds)  # app should preced PAT
    assert app_cred.origin == GitHubCredentialOrigin.GITHUB_APP
    assert app_cred.token == mock_token

    pat_cred = next(creds)  # pat comes last
    assert pat_cred.origin == GitHubCredentialOrigin.USER
    assert isinstance(pat_cred.token, str)

    # generator should now be empty
    with pytest.raises(StopIteration):
        next(creds)

    create_token_mock.assert_called_once()


@mock.patch.object(GithubIntegration, "get_access_token")
def test_credentials_generator_cache_hit(
    create_token_mock: mock.Mock,
    config: Config,
    faker: Faker,
    installation_authz_factory: Callable[..., InstallationAuthorization],
):
    mock_token = faker.pystr()
    github_app, *_ = config.github_apps.keys()
    ghi = CachedGithubIntegration.factory(github_app, config, config.github_api_url)

    ghi._cache[  # type: ignore
        _methodkey(ghi, installation_id=config.github_apps[github_app].installation_id)
    ] = installation_authz_factory(mock_token)

    creds = credential_generator(config.github_api_url, config, {})

    app_cred = next(creds)  # app should preced PAT
    assert app_cred.origin == GitHubCredentialOrigin.GITHUB_APP
    assert app_cred.token == mock_token

    pat_cred = next(creds)  # pat comes last
    assert pat_cred.origin == GitHubCredentialOrigin.USER
    assert isinstance(pat_cred.token, str)

    # generator should now be empty
    with pytest.raises(StopIteration):
        next(creds)

    # Cache was used
    create_token_mock.assert_not_called()


def test_credentials_generator_skips_rate_limited_apps(
    config: Config,
    faker: Faker,
    installation_authz_factory: Callable[..., InstallationAuthorization],
):
    mock_token = faker.pystr()
    github_app, *_ = config.github_apps.keys()
    ghi = CachedGithubIntegration.factory(github_app, config, config.github_api_url)
    ghi._cache[  # type: ignore
        _methodkey(ghi, installation_id=config.github_apps[github_app].installation_id)
    ] = installation_authz_factory(mock_token)

    creds = credential_generator(
        config.github_api_url,
        config,
        {(GitHubCredentialOrigin.GITHUB_APP, github_app): mock.ANY},
    )

    cred = next(creds)
    # next cred is PAT, app is skipped
    assert cred.origin == GitHubCredentialOrigin.USER
    assert isinstance(cred.token, str)

    # generator should now be empty
    with pytest.raises(StopIteration):
        next(creds)


def test_credentials_generator_skips_rate_limited_pats(
    config: Config,
    faker: Faker,
    installation_authz_factory: Callable[..., InstallationAuthorization],
):
    mock_token = faker.pystr()
    github_pat, *_ = config.github_pats.keys()
    github_app, *_ = config.github_apps.keys()
    ghi = CachedGithubIntegration.factory(github_app, config, config.github_api_url)
    ghi._cache[  # type: ignore
        _methodkey(ghi, installation_id=config.github_apps[github_app].installation_id)
    ] = installation_authz_factory(mock_token)

    creds = credential_generator(
        config.github_api_url,
        config,
        {(GitHubCredentialOrigin.USER, github_pat): mock.ANY},
    )

    cred = next(creds)
    # next cred is PAT, app is skipped
    assert cred.origin == GitHubCredentialOrigin.GITHUB_APP
    assert cred.token == mock_token

    # generator should now be empty
    with pytest.raises(StopIteration):
        next(creds)
