from datetime import datetime
from typing import Callable
from unittest import mock

import pytest
import requests
import requests_mock
import werkzeug
from faker import Faker
from github import GithubIntegration
from github.InstallationAuthorization import InstallationAuthorization
from requests.structures import CaseInsensitiveDict
from werkzeug import Request
from werkzeug.test import EnvironBuilder

from github_proxy.cache.backend import CacheBackend
from github_proxy.config import Config
from github_proxy.github_credentials import GitHubCredential
from github_proxy.github_credentials import GitHubCredentialOrigin
from github_proxy.github_credentials import RateLimited
from github_proxy.proxy import proxy_cached_request
from github_proxy.proxy import send_gh_request


@mock.patch.object(GithubIntegration, "get_access_token")
def test_proxy_cached_request_cache_hit(
    get_access_token_mock: mock.Mock,
    faker: Faker,
    cache_backend: CacheBackend,
    config: Config,
    requests_mock: requests_mock.Mocker,
    installation_authz_factory: Callable[..., InstallationAuthorization],
):
    get_access_token_mock.return_value = installation_authz_factory(faker.pystr())

    path = faker.uri_path()
    cached_response = werkzeug.Response()
    cache_backend.set(path, cached_response)

    requests_mock.get(
        config.github_api_url + path,
        status_code=304,
    )

    builder = EnvironBuilder()
    request = Request(builder.get_environ())
    tel_collector_mock = mock.Mock()
    client = faker.word()

    resp = proxy_cached_request(
        path=path,
        request=request,
        config=config,
        cache=cache_backend,
        client=client,
        rate_limited={},
        tel_collector=tel_collector_mock,
    )

    assert resp == cached_response
    tel_collector_mock.collect_proxy_request_metrics.assert_called_once_with(
        client, request, cache_hit=True
    )


@mock.patch.object(GithubIntegration, "get_access_token")
def test_proxy_cached_request_cache_miss_if_stale_cache_entry(
    get_access_token_mock: mock.Mock,
    faker: Faker,
    cache_backend: CacheBackend,
    config: Config,
    requests_mock: requests_mock.Mocker,
    installation_authz_factory: Callable[..., InstallationAuthorization],
):
    get_access_token_mock.return_value = installation_authz_factory(faker.pystr())

    path = faker.uri_path()
    cached_response = werkzeug.Response()
    cache_backend.set(path, cached_response)

    requests_mock.get(
        config.github_api_url + path,
        status_code=200,
        headers={"Etag": faker.pystr()},
    )

    builder = EnvironBuilder()
    request = Request(builder.get_environ())
    tel_collector_mock = mock.Mock()
    client = faker.word()

    resp = proxy_cached_request(
        path=path,
        request=request,
        config=config,
        cache=cache_backend,
        client=client,
        rate_limited={},
        tel_collector=tel_collector_mock,
    )

    assert resp != cached_response
    assert cache_backend.get(path) != cached_response
    assert resp == cache_backend.get(path)
    tel_collector_mock.collect_proxy_request_metrics.assert_called_once_with(
        client, request, cache_hit=False
    )


@mock.patch.object(GithubIntegration, "get_access_token")
def test_proxy_cached_request_cache_miss_if_no_cache_entry(
    get_access_token_mock: mock.Mock,
    faker: Faker,
    cache_backend: CacheBackend,
    config: Config,
    requests_mock: requests_mock.Mocker,
    installation_authz_factory: Callable[..., InstallationAuthorization],
):
    get_access_token_mock.return_value = installation_authz_factory(faker.pystr())

    path = faker.uri_path()

    requests_mock.get(
        config.github_api_url + path, status_code=200, headers={"Etag": faker.pystr()}
    )

    builder = EnvironBuilder()
    request = Request(builder.get_environ())
    tel_collector_mock = mock.Mock()
    client = faker.word()

    resp = proxy_cached_request(
        path=path,
        request=request,
        config=config,
        cache=cache_backend,
        client=client,
        rate_limited={},
        tel_collector=tel_collector_mock,
    )

    assert resp == cache_backend.get(path)
    tel_collector_mock.collect_proxy_request_metrics.assert_called_once_with(
        client, request, cache_hit=False
    )


@mock.patch.object(GithubIntegration, "get_access_token")
def test_proxy_cached_request_does_not_cache_responses_without_cache_headers(
    get_access_token_mock: mock.Mock,
    faker: Faker,
    cache_backend: CacheBackend,
    config: Config,
    requests_mock: requests_mock.Mocker,
    installation_authz_factory: Callable[..., InstallationAuthorization],
):
    get_access_token_mock.return_value = installation_authz_factory(faker.pystr())

    path = faker.uri_path()

    requests_mock.get(
        config.github_api_url + path,
        status_code=200,
    )

    builder = EnvironBuilder()
    request = Request(builder.get_environ())
    tel_collector_mock = mock.Mock()
    client = faker.word()

    resp = proxy_cached_request(
        path=path,
        request=request,
        config=config,
        cache=cache_backend,
        client=client,
        rate_limited={},
        tel_collector=tel_collector_mock,
    )

    assert isinstance(resp, werkzeug.Response)
    assert not cache_backend.get(path)
    tel_collector_mock.collect_proxy_request_metrics.assert_called_once_with(
        client, request, cache_hit=False
    )


@mock.patch.object(GithubIntegration, "get_access_token")
def test_send_gh_request_with_all_credentials_rate_limited(
    get_access_token_mock: mock.Mock,
    requests_mock: requests_mock.Mocker,
    config: Config,
    faker: Faker,
    installation_authz_factory: Callable[..., InstallationAuthorization],
):
    get_access_token_mock.return_value = installation_authz_factory(faker.pystr())

    path = faker.uri_path()
    requests_mock.get(
        config.github_api_url + path,
        headers={
            "x-ratelimit-reset": "1646414677",
            "x-ratelimit-remaining": "0",
        },
        status_code=403,
    )

    builder = EnvironBuilder(method="GET")
    rate_limited: RateLimited = {}

    with pytest.raises(RuntimeError):
        send_gh_request(
            path=path,
            request=Request(builder.get_environ()),
            config=config,
            rate_limited=rate_limited,
            tel_collector=mock.Mock(),
        )

    assert len(rate_limited) == 2


@mock.patch.object(GithubIntegration, "get_access_token")
def test_send_gh_request_with_some_credentials_rate_limited(
    get_access_token_mock: mock.Mock,
    requests_mock: requests_mock.Mocker,
    config: Config,
    faker: Faker,
    installation_authz_factory: Callable[..., InstallationAuthorization],
):
    app_name, *_ = config.github_apps.keys()
    app_token = faker.pystr()
    get_access_token_mock.return_value = installation_authz_factory(app_token)

    path = faker.uri_path()

    def custom_matcher(request: requests.Request) -> requests.Response:
        auth_header = request.headers["Authorization"]
        resp = requests.Response()

        if auth_header.endswith(app_token):
            # only the github app is rate limited
            resp.status_code = 403
            resp.headers = CaseInsensitiveDict(
                {
                    "X-RateLimit-Reset": "1646414677",
                    "X-RateLimit-Remaining": "0",
                }
            )
            return resp

        resp.status_code = 201
        return resp

    requests_mock.add_matcher(custom_matcher)

    builder = EnvironBuilder(method="GET")
    rate_limited: RateLimited = {}

    resp = send_gh_request(
        path=path,
        request=Request(builder.get_environ()),
        config=config,
        rate_limited=rate_limited,
        tel_collector=mock.Mock(),
    )
    assert resp.status_code == 201

    assert len(rate_limited) == 1
    reset_value = rate_limited[(GitHubCredentialOrigin.GITHUB_APP, app_name)]
    assert isinstance(reset_value, datetime)


@mock.patch.object(GithubIntegration, "get_access_token")
def test_send_gh_request_collects_telemetry_metrics(
    get_access_token_mock: mock.Mock,
    requests_mock: requests_mock.Mocker,
    config: Config,
    faker: Faker,
    installation_authz_factory: Callable[..., InstallationAuthorization],
):
    app_name, *_ = config.github_apps.keys()
    app_token = faker.pystr()
    get_access_token_mock.return_value = installation_authz_factory(app_token)

    path = faker.uri_path()
    requests_mock.get(
        config.github_api_url + path,
        headers={
            "x-ratelimit-reset": str(faker.pyint()),
            "x-ratelimit-remaining": "1646414677",
        },
        status_code=200,
    )

    builder = EnvironBuilder(method="GET")
    rate_limited: RateLimited = {}

    tel_collector_mock = mock.Mock()
    _ = send_gh_request(
        path=path,
        request=Request(builder.get_environ()),
        config=config,
        rate_limited=rate_limited,
        tel_collector=tel_collector_mock,
    )

    tel_collector_mock.collect_gh_response_metrics.assert_called_once_with(
        GitHubCredential(
            name=app_name, origin=GitHubCredentialOrigin.GITHUB_APP, token=app_token
        ),
        mock.ANY,
    )
