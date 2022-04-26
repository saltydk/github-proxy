import os
import re
from pathlib import Path
from unittest.mock import mock_open
from unittest.mock import patch

from faker import Faker
from jinja2 import DictLoader
from jinja2 import Environment

from github_proxy.config import Config
from github_proxy.proxy import ProxyClientScope


def test_config_collect_github_apps(faker: Faker):
    app_name_1 = "foo"
    app_id_1 = str(faker.pyint())
    app_installation_id_1 = str(faker.pyint())
    app_pem_1 = str(faker.text())

    app_name_2 = "bar"
    app_id_2 = str(faker.pyint())
    app_installation_id_2 = str(faker.pyint())
    app_pem_2 = str(faker.text())

    config_dict = {
        f"GITHUB_APP_{app_name_1.upper()}_ID": app_id_1,
        f"GITHUB_APP_{app_name_1.upper()}_INSTALLATION_ID": app_installation_id_1,
        f"GITHUB_APP_{app_name_1.upper()}_PEM": app_pem_1,
        f"GITHUB_APP_{app_name_2.upper()}_ID": app_id_2,
        f"GITHUB_APP_{app_name_2.upper()}_INSTALLATION_ID": app_installation_id_2,
        f"GITHUB_APP_{app_name_2.upper()}_PEM": app_pem_2,
    }

    apps = Config._collect_github_apps(config_dict)

    assert len(apps) == 2

    assert apps[app_name_1].id_ == app_id_1
    assert apps[app_name_1].installation_id == int(app_installation_id_1)
    assert apps[app_name_1].private_key == app_pem_1

    assert apps[app_name_2].id_ == app_id_2
    assert apps[app_name_2].installation_id == int(app_installation_id_2)
    assert apps[app_name_2].private_key == app_pem_2


def test_config_collect_github_pats():
    pat_name_1 = "foo"
    pat_1 = "one"

    pat_name_2 = "bar"
    pat_2 = "two"

    config_dict = {
        f"GITHUB_PAT_{pat_name_1.upper()}": pat_1,
        f"GITHUB_PAT_{pat_name_2.upper()}": pat_2,
    }

    pats = Config._collect_github_pats(config_dict)

    assert len(pats) == 2

    assert pats[pat_name_1] == pat_1
    assert pats[pat_name_2] == pat_2


def test_config_collect_clients_from_yaml_file(faker: Faker):
    token_name_1 = "one"
    token_1 = "foo"

    token_name_2 = "two"
    token_2 = "bar"
    scope_2_method = "GET"
    scope_2_path = ".*"

    client_registry_file_content = f"""---
version: 1
clients:
- name: {token_name_1}
  token: {token_1}
- name: {token_name_2}
  token: {token_2}
  scopes:
  - method: {scope_2_method}
    path: {scope_2_path}
...
    """
    config_dict = {
        "CLIENT_REGISTRY_FILE_PATH": faker.uri_path(),
    }
    with patch.object(Path, "open", mock_open(read_data=client_registry_file_content)):
        clients = Config._collect_clients(config_dict)

    assert len(clients) == 2

    for client in clients:
        if client.name == token_name_1:
            assert client.token == token_1
            assert list(client.scopes) == [ProxyClientScope()]
        elif client.name == token_name_2:
            assert client.token == token_2
            assert list(client.scopes) == [
                ProxyClientScope(
                    method=re.compile(scope_2_method), path=re.compile(scope_2_path)
                )
            ]
        else:
            assert False


def test_config_collect_clients_from_j2_file(faker: Faker):
    token_name_1 = "one"
    token_1 = "foo"

    token_name_2 = "two"
    token_2 = "bar"
    scope_2_method = "GET"
    scope_2_path = ".*"

    client_registry_file_content = f"""---
version: 1
clients:
- name: {token_name_1}
  token: {{{{ env.TOKEN_{token_name_1} }}}}
- name: {token_name_2}
  token: {{{{ env.TOKEN_{token_name_2} }}}}
  scopes:
  - method: {scope_2_method}
    path: {scope_2_path}
...
    """
    template_name = faker.word() + ".j2"
    config_dict = {
        "CLIENT_REGISTRY_FILE_PATH": os.path.join(faker.uri_path(), template_name),
        f"TOKEN_{token_name_1}": token_1,
        f"TOKEN_{token_name_2}": token_2,
    }

    j2_env = Environment(
        loader=DictLoader({template_name: client_registry_file_content})
    )
    clients = Config._collect_clients(config_dict, j2_env)

    assert len(clients) == 2

    for client in clients:
        if client.name == token_name_1:
            assert client.token == token_1
            assert list(client.scopes) == [ProxyClientScope()]
        elif client.name == token_name_2:
            assert client.token == token_2
            assert list(client.scopes) == [
                ProxyClientScope(
                    method=re.compile(scope_2_method), path=re.compile(scope_2_path)
                )
            ]
        else:
            assert False
