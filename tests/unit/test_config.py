from faker import Faker

from github_proxy.config import Config


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


def test_config_collect_tokens():
    token_name_1 = "one"
    token_1 = "foo"

    token_name_2 = "two"
    token_2 = "bar"

    config_dict = {
        f"TOKEN_{token_name_1.upper()}": token_1,
        f"TOKEN_{token_name_2.upper()}": token_2,
    }

    tokens = Config._collect_tokens(config_dict)

    assert len(tokens) == 2

    assert tokens[token_1] == token_name_1
    assert tokens[token_2] == token_name_2
