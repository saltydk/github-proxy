from datetime import datetime
from typing import Callable
from unittest import mock

import pytest
import requests
import requests_mock
from faker import Faker
from github import GithubIntegration
from github.InstallationAuthorization import InstallationAuthorization
from requests.structures import CaseInsensitiveDict
from werkzeug import Request
from werkzeug.test import EnvironBuilder

from github_proxy.config import Config
from github_proxy.github_credentials import GitHubCredentialOrigin
from github_proxy.github_credentials import RateLimited
from github_proxy.proxy import proxy_request


@mock.patch.object(GithubIntegration, "get_access_token")
def test_proxy_request_with_all_credentials_rate_limited(
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
        proxy_request(
            path=path,
            request=Request(builder.get_environ()),
            config=config,
            rate_limited=rate_limited,
        )

    assert len(rate_limited) == 2


@mock.patch.object(GithubIntegration, "get_access_token")
def test_proxy_request_with_some_credentials_rate_limited(
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

    resp = proxy_request(
        path=path,
        request=Request(builder.get_environ()),
        config=config,
        rate_limited=rate_limited,
    )
    assert resp.status_code == 201

    assert len(rate_limited) == 1
    reset_value = rate_limited[(GitHubCredentialOrigin.GITHUB_APP, app_name)]
    assert isinstance(reset_value, datetime)
