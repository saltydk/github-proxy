import os
import secrets
from pathlib import Path
from typing import Iterator

import pytest
import trustme
from faker import Faker
from flask import Flask
from flask.testing import FlaskClient

from github_proxy import blueprint

_TEST_TOKEN = secrets.token_hex()
_READONLY_TOKEN = secrets.token_hex()


@pytest.fixture
def test_token() -> str:
    return _TEST_TOKEN


@pytest.fixture
def read_only_token() -> str:
    return _READONLY_TOKEN


@pytest.fixture
def fake_cert() -> str:
    ca = trustme.CA()
    cert = ca.issue_cert("test-host.example.org")
    return cert.private_key_pem.bytes().decode()


@pytest.fixture
def client_registry_file_path() -> Path:
    return Path(__file__).parent / "fixtures" / "clients.example.yml.j2"


@pytest.fixture
def integration_env(
    test_token: str,
    read_only_token: str,
    faker: Faker,
    fake_cert: str,
    client_registry_file_path: Path,
) -> None:
    test_gh_app_pem = os.environ.get("GITHUB_APP_TEST_PEM", fake_cert)
    test_gh_app_id = os.environ.get("GITHUB_APP_TEST_ID", str(faker.pyint()))
    test_gh_app_installation_id = os.environ.get(
        "GITHUB_APP_TEST_INSTALLATION_ID", "23919646"  # github
    )
    os.environ.clear()
    os.environ["TOKEN_TEST"] = test_token
    os.environ["TOKEN_READ_ONLY"] = read_only_token
    os.environ["GITHUB_APP_TEST_PEM"] = test_gh_app_pem
    os.environ["GITHUB_APP_TEST_ID"] = test_gh_app_id
    os.environ["GITHUB_APP_TEST_INSTALLATION_ID"] = test_gh_app_installation_id
    os.environ["CLIENT_REGISTRY_FILE_PATH"] = str(client_registry_file_path)

    # Caching GitHub tokens entails the risk of re-using cached tokens
    # across different tests. This might cause the silent rise of
    # hidden dependencies between test cases leading to nondeterministic test results.
    os.environ["GITHUB_CREDS_CACHE_MAXSIZE"] = "0"


@pytest.fixture
def flask_app(integration_env: None) -> Flask:
    app = Flask(__name__)
    app.register_blueprint(blueprint)
    return app


@pytest.fixture
def client(flask_app: Flask) -> Iterator[FlaskClient]:
    with flask_app.test_client() as tc:
        yield tc
