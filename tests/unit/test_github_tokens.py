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
from github_proxy.github_tokens import GitHubTokenOrigin
from github_proxy.github_tokens import construct_installed_integration
from github_proxy.github_tokens import token_generator


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
def test_token_generator_cache_miss(
    create_token_mock: mock.Mock,
    config: Config,
    faker: Faker,
    installation_authz_factory: Callable[..., InstallationAuthorization],
):
    mock_token = faker.pystr()
    create_token_mock.return_value = installation_authz_factory(mock_token)
    integrations = {
        app_name: construct_installed_integration(
            app_name, config, config.github_api_url
        )
        for app_name in config.github_apps
    }
    tokens = token_generator(integrations, config.github_pats, {})

    app_token = next(tokens)  # app should preced PAT
    assert app_token.origin == GitHubTokenOrigin.GITHUB_APP
    assert app_token.value == mock_token

    pat_token = next(tokens)  # pat comes last
    assert pat_token.origin == GitHubTokenOrigin.USER
    assert isinstance(pat_token.value, str)

    # generator should now be empty
    with pytest.raises(StopIteration):
        next(tokens)

    create_token_mock.assert_called_once()


@mock.patch.object(GithubIntegration, "get_access_token")
def test_token_generator_cache_hit(
    create_token_mock: mock.Mock,
    config: Config,
    faker: Faker,
    installation_authz_factory: Callable[..., InstallationAuthorization],
):
    mock_token = faker.pystr()
    github_app, *_ = config.github_apps.keys()
    ghi, iid = construct_installed_integration(
        github_app, config, config.github_api_url
    )

    ghi._cache[  # type: ignore
        _methodkey(ghi, installation_id=config.github_apps[github_app].installation_id)
    ] = installation_authz_factory(mock_token)

    integrations = {github_app: (ghi, iid)}
    tokens = token_generator(integrations, config.github_pats, {})

    app_token = next(tokens)  # app should preced PAT
    assert app_token.origin == GitHubTokenOrigin.GITHUB_APP
    assert app_token.value == mock_token

    pat_token = next(tokens)  # pat comes last
    assert pat_token.origin == GitHubTokenOrigin.USER
    assert isinstance(pat_token.value, str)

    # generator should now be empty
    with pytest.raises(StopIteration):
        next(tokens)

    # Cache was used
    create_token_mock.assert_not_called()


def test_token_generator_skips_rate_limited_apps(
    config: Config,
    faker: Faker,
    installation_authz_factory: Callable[..., InstallationAuthorization],
):
    mock_token = faker.pystr()
    github_app, *_ = config.github_apps.keys()
    ghi, iid = construct_installed_integration(
        github_app, config, config.github_api_url
    )
    ghi._cache[  # type: ignore
        _methodkey(ghi, installation_id=config.github_apps[github_app].installation_id)
    ] = installation_authz_factory(mock_token)

    integrations = {github_app: (ghi, iid)}

    tokens = token_generator(
        integrations,
        config.github_pats,
        {(GitHubTokenOrigin.GITHUB_APP, github_app): mock.ANY},
    )

    token = next(tokens)
    # next cred is PAT, app is skipped
    assert token.origin == GitHubTokenOrigin.USER
    assert isinstance(token.value, str)

    # generator should now be empty
    with pytest.raises(StopIteration):
        next(tokens)


def test_token_generator_skips_rate_limited_pats(
    config: Config,
    faker: Faker,
    installation_authz_factory: Callable[..., InstallationAuthorization],
):
    mock_token = faker.pystr()
    github_pat, *_ = config.github_pats.keys()
    github_app, *_ = config.github_apps.keys()
    ghi, iid = construct_installed_integration(
        github_app, config, config.github_api_url
    )
    ghi._cache[  # type: ignore
        _methodkey(ghi, installation_id=config.github_apps[github_app].installation_id)
    ] = installation_authz_factory(mock_token)

    integrations = {github_app: (ghi, iid)}

    tokens = token_generator(
        integrations,
        config.github_pats,
        {(GitHubTokenOrigin.USER, github_pat): mock.ANY},
    )

    token = next(tokens)
    # next cred is PAT, app is skipped
    assert token.origin == GitHubTokenOrigin.GITHUB_APP
    assert token.value == mock_token

    # generator should now be empty
    with pytest.raises(StopIteration):
        next(tokens)
