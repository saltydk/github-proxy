import os
from typing import Mapping
from typing import Optional

from github_proxy.cache.backend import CacheBackendConfig
from github_proxy.github_tokens import GitHubAppConfig
from github_proxy.github_tokens import GitHubTokenConfig


class Config(GitHubTokenConfig, CacheBackendConfig):
    def __init__(self, config_dict: Optional[Mapping[str, str]] = None):
        if config_dict is None:
            config_dict = os.environ

        self.github_api_url = config_dict.get(
            "GITHUB_API_URL", "https://api.github.com"
        )

        # Configuring the cache that persists GitHub responses:
        self.cache_ttl = int(config_dict.get("CACHE_TTL", "3600"))
        self.cache_backend_url = config_dict.get("CACHE_BACKEND_URL", "inmemory://")

        # Collecting GitHub creds:
        self.github_pats = Config._collect_github_pats(config_dict)
        self.github_apps = Config._collect_github_apps(config_dict)

        # Configuring the inmemory cache that persists GitHub creds:
        self.github_creds_cache_maxsize = int(
            config_dict.get("GITHUB_CREDS_CACHE_MAXSIZE", "256")
        )
        self.github_creds_cache_ttl_padding = int(
            config_dict.get("GITHUB_CREDS_CACHE_TTL_PADDING", "10")
        )

        # Collecting tokens of proxy clients:
        self.tokens = Config._collect_tokens(config_dict)

    @staticmethod
    def _collect_tokens(config_dict: Mapping[str, str]) -> Mapping[str, str]:
        return {
            token: env[len("TOKEN_") :].lower()
            for env, token in config_dict.items()
            if env.startswith("TOKEN_")
        }

    @staticmethod
    def _collect_github_pats(config_dict: Mapping[str, str]) -> Mapping[str, str]:
        return {
            env[len("GITHUB_PAT_") :].lower(): pat
            for env, pat in config_dict.items()
            if env.startswith("GITHUB_PAT_")
        }

    @staticmethod
    def _collect_github_apps(
        config_dict: Mapping[str, str]
    ) -> Mapping[str, GitHubAppConfig]:
        app_names = [
            env[len("GITHUB_APP_") : -len("_ID")].lower()
            for env in config_dict
            if env.startswith("GITHUB_APP_")
            and env.endswith("_ID")
            and not env.endswith("_INSTALLATION_ID")
        ]
        return {
            name: GitHubAppConfig(
                id_=config_dict[f"GITHUB_APP_{name.upper()}_ID"],
                private_key=config_dict[f"GITHUB_APP_{name.upper()}_PEM"],
                installation_id=int(
                    config_dict[f"GITHUB_APP_{name.upper()}_INSTALLATION_ID"]
                ),
            )
            for name in app_names
        }

    def __hash__(self) -> int:  # to satisfy mypy
        return super().__hash__()
