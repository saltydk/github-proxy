import re
from datetime import datetime
from typing import Callable
from typing import Sequence
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

from github_proxy.github_tokens import GitHubToken
from github_proxy.github_tokens import GitHubTokenOrigin
from github_proxy.proxy import Proxy
from github_proxy.proxy import ProxyClientScope


@mock.patch.object(GithubIntegration, "get_access_token")
def test_proxy_cached_request_cache_hit(
    get_access_token_mock: mock.Mock,
    faker: Faker,
    proxy: Proxy,
    requests_mock: requests_mock.Mocker,
    installation_authz_factory: Callable[..., InstallationAuthorization],
):
    get_access_token_mock.return_value = installation_authz_factory(faker.pystr())

    path = faker.uri_path()
    cached_response = werkzeug.Response()
    media_type = faker.mime_type()
    qs = f"{faker.word()}={faker.pystr()}"
    proxy.cache.set(path, qs, media_type, cached_response)

    requests_mock.get(
        proxy.github_api_url + path,
        status_code=304,
    )

    request = Request.from_values(headers=[("Accept", media_type)], query_string=qs)
    client = faker.word()
    proxy.tel_collector = mock.Mock()

    resp = proxy.cached_request(
        path=path,
        request=request,
        client=client,
    )

    assert resp == cached_response
    proxy.tel_collector.collect_proxy_request_metrics.assert_called_once_with(
        client, request, cache_hit=True
    )


@mock.patch.object(GithubIntegration, "get_access_token")
def test_proxy_cached_request_cache_miss_when_using_different_qs(
    get_access_token_mock: mock.Mock,
    faker: Faker,
    proxy: Proxy,
    requests_mock: requests_mock.Mocker,
    installation_authz_factory: Callable[..., InstallationAuthorization],
):
    get_access_token_mock.return_value = installation_authz_factory(faker.pystr())

    path = faker.uri_path()
    cached_response = werkzeug.Response()
    media_type = faker.mime_type()
    qs = f"{faker.word()}={faker.pystr()}"
    proxy.cache.set(path, qs, media_type, cached_response)

    requests_mock.get(
        proxy.github_api_url + path + f"?{qs}",
        status_code=304,
    )

    modified_qs = qs + faker.pystr()

    requests_mock.get(
        proxy.github_api_url + path + f"?{modified_qs}",
        status_code=200,
        headers={"Etag": faker.pystr()},
    )

    request = Request.from_values(
        headers=[("Accept", media_type)], query_string=modified_qs
    )
    client = faker.word()
    proxy.tel_collector = mock.Mock()

    resp = proxy.cached_request(
        path=path,
        request=request,
        client=client,
    )

    assert resp != cached_response
    assert proxy.cache.get(path, modified_qs, media_type) != cached_response
    assert resp == proxy.cache.get(path, modified_qs, media_type)
    proxy.tel_collector.collect_proxy_request_metrics.assert_called_once_with(
        client, request, False
    )


@mock.patch.object(GithubIntegration, "get_access_token")
def test_proxy_cached_request_cache_miss_if_stale_cache_entry(
    get_access_token_mock: mock.Mock,
    faker: Faker,
    proxy: Proxy,
    requests_mock: requests_mock.Mocker,
    installation_authz_factory: Callable[..., InstallationAuthorization],
):
    get_access_token_mock.return_value = installation_authz_factory(faker.pystr())

    path = faker.uri_path()
    media_type = faker.mime_type()
    qs = f"{faker.word()}={faker.pystr()}"
    cached_response = werkzeug.Response()
    proxy.cache.set(path, qs, media_type, cached_response)

    requests_mock.get(
        proxy.github_api_url + path,
        status_code=200,
        headers={"Etag": faker.pystr()},
    )

    request = Request.from_values(headers=[("Accept", media_type)], query_string=qs)
    client = faker.word()
    proxy.tel_collector = mock.Mock()

    resp = proxy.cached_request(
        path=path,
        request=request,
        client=client,
    )

    assert resp != cached_response
    assert proxy.cache.get(path, qs, media_type) != cached_response
    assert resp == proxy.cache.get(path, qs, media_type)
    proxy.tel_collector.collect_proxy_request_metrics.assert_called_once_with(
        client, request, cache_hit=False
    )


@mock.patch.object(GithubIntegration, "get_access_token")
def test_proxy_cached_request_cache_miss_if_no_entry_for_cacheable_resource(
    get_access_token_mock: mock.Mock,
    faker: Faker,
    proxy: Proxy,
    requests_mock: requests_mock.Mocker,
    installation_authz_factory: Callable[..., InstallationAuthorization],
):
    get_access_token_mock.return_value = installation_authz_factory(faker.pystr())

    path = faker.uri_path()
    media_type = faker.mime_type()
    qs = f"{faker.word()}={faker.pystr()}"

    requests_mock.get(
        proxy.github_api_url + path, status_code=200, headers={"Etag": faker.pystr()}
    )

    request = Request.from_values(headers=[("Accept", media_type)], query_string=qs)
    client = faker.word()
    proxy.tel_collector = mock.Mock()

    assert not proxy.cache.get(path, qs, media_type)

    resp = proxy.cached_request(
        path=path,
        request=request,
        client=client,
    )

    assert resp == proxy.cache.get(path, qs, media_type)
    proxy.tel_collector.collect_proxy_request_metrics.assert_called_once_with(
        client, request, False
    )


@mock.patch.object(GithubIntegration, "get_access_token")
def test_proxy_cached_request_does_not_cache_responses_without_cache_headers(
    get_access_token_mock: mock.Mock,
    faker: Faker,
    proxy: Proxy,
    requests_mock: requests_mock.Mocker,
    installation_authz_factory: Callable[..., InstallationAuthorization],
):
    get_access_token_mock.return_value = installation_authz_factory(faker.pystr())

    path = faker.uri_path()
    media_type = faker.mime_type()
    qs = f"{faker.word()}={faker.pystr()}"

    requests_mock.get(
        proxy.github_api_url + path,
        status_code=200,
    )

    request = Request.from_values(headers=[("Accept", media_type)], query_string=qs)
    client = faker.word()
    proxy.tel_collector = mock.Mock()

    resp = proxy.cached_request(
        path=path,
        request=request,
        client=client,
    )

    assert isinstance(resp, werkzeug.Response)
    assert not proxy.cache.get(path, qs, media_type)
    proxy.tel_collector.collect_proxy_request_metrics.assert_called_once_with(
        client,
        request,
        None,
    )


@mock.patch.object(GithubIntegration, "get_access_token")
def test_send_gh_request_with_all_tokens_rate_limited(
    get_access_token_mock: mock.Mock,
    requests_mock: requests_mock.Mocker,
    proxy: Proxy,
    faker: Faker,
    installation_authz_factory: Callable[..., InstallationAuthorization],
):
    get_access_token_mock.return_value = installation_authz_factory(faker.pystr())

    path = faker.uri_path()
    requests_mock.get(
        proxy.github_api_url + path,
        headers={
            "x-ratelimit-reset": "1646414677",
            "x-ratelimit-remaining": "0",
        },
        status_code=403,
    )

    with pytest.raises(RuntimeError):
        proxy._send_gh_request(path=path, request=Request.from_values(method="GET"))

    assert len(proxy.rate_limited) == 2


@mock.patch.object(GithubIntegration, "get_access_token")
def test_send_gh_request_with_some_tokens_rate_limited(
    get_access_token_mock: mock.Mock,
    requests_mock: requests_mock.Mocker,
    proxy: Proxy,
    faker: Faker,
    installation_authz_factory: Callable[..., InstallationAuthorization],
):
    app_name, *_ = proxy.gh_token_config.github_apps.keys()
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

    proxy.tel_collector = mock.Mock()

    resp = proxy._send_gh_request(
        path=path,
        request=Request.from_values(method="GET"),
    )
    assert resp.status_code == 201

    assert len(proxy.rate_limited) == 1
    reset_value = proxy.rate_limited[(GitHubTokenOrigin.GITHUB_APP, app_name)]
    assert isinstance(reset_value, datetime)


@mock.patch.object(GithubIntegration, "get_access_token")
def test_send_gh_request_collects_telemetry_metrics(
    get_access_token_mock: mock.Mock,
    requests_mock: requests_mock.Mocker,
    proxy: Proxy,
    faker: Faker,
    installation_authz_factory: Callable[..., InstallationAuthorization],
):
    app_name, *_ = proxy.gh_token_config.github_apps.keys()
    app_token = faker.pystr()
    get_access_token_mock.return_value = installation_authz_factory(app_token)

    path = faker.uri_path()
    requests_mock.get(
        proxy.github_api_url + path,
        headers={
            "x-ratelimit-reset": str(faker.pyint()),
            "x-ratelimit-remaining": "1646414677",
        },
        status_code=200,
    )

    proxy.tel_collector = mock.Mock()

    _ = proxy._send_gh_request(
        path=path,
        request=Request.from_values(method="GET"),
    )

    proxy.tel_collector.collect_gh_response_metrics.assert_called_once_with(
        GitHubToken(
            name=app_name, origin=GitHubTokenOrigin.GITHUB_APP, value=app_token
        ),
        mock.ANY,
    )


@pytest.mark.parametrize(
    argnames=["status_code", "expected_result"],
    argvalues=[(200, True), (401, False)],
    ids=["health_success", "health_faulure"],
)
@mock.patch.object(GithubIntegration, "get_access_token")
def test_health(
    get_access_token_mock: mock.Mock,
    status_code: int,
    expected_result: bool,
    requests_mock: requests_mock.Mocker,
    proxy: Proxy,
    faker: Faker,
    installation_authz_factory: Callable[..., InstallationAuthorization],
):
    app_token = faker.pystr()
    get_access_token_mock.return_value = installation_authz_factory(app_token)

    requests_mock.get(
        proxy.github_api_url + "zen",
        status_code=status_code,
    )

    assert proxy.health() is expected_result


@pytest.mark.parametrize(
    argnames=["name", "scopes", "proxy_request", "decision"],
    argvalues=[
        (
            "admin",
            [ProxyClientScope(method=re.compile(r".*"), path=re.compile(r".*"))],
            Request.from_values(method="DELETE", path="/orgs/babylonhealth"),
            True,
        ),
        (
            "read_only",
            [ProxyClientScope(method=re.compile("GET"), path=re.compile(r".*"))],
            Request.from_values(method="GET", path="/orgs/babylonhealth"),
            True,
        ),
        (
            "read_only",
            [ProxyClientScope(method=re.compile("GET"), path=re.compile(r".*"))],
            Request.from_values(method="DELETE", path="/orgs/babylonhealth"),
            False,
        ),
        (
            "cyrus_team",
            [
                ProxyClientScope(
                    method=re.compile(r".*"), path=re.compile(r"/repos/bbln/cyrus/.*")
                )
            ],
            Request.from_values(
                method="DELETE", path="/api/v3/repos/bbln/cyrus/issues/1"
            ),
            True,
        ),
    ],
    ids=[
        "client_with_default_full_access_scope_can_mutate_resources",
        "read_only_client_can_get_resources",
        "read_only_client_cannot_mutate_resources",
        "api_v3_is_stripped_when_matching_path",
    ],
)
def test_auth_for_registered_clients(
    name: str,
    scopes: Sequence[ProxyClientScope],
    proxy_request: werkzeug.Request,
    decision: bool,
    proxy: Proxy,
    faker: Faker,
):
    token = faker.pystr()
    proxy.client_tokens = {token: (name, scopes)}
    assert (proxy.auth(token, proxy_request) == name) is decision


def test_auth_for_unnknown_client_fails(
    faker: Faker,
    proxy: Proxy,
):
    proxy.client_tokens = {}
    assert not proxy.auth(faker.pystr(), Request.from_values(method="GET", path="/zen"))
