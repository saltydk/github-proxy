import os
from typing import Mapping
from typing import Optional


class Config:
    def __init__(self, config_dict: Optional[Mapping[str, str]] = None):
        if config_dict is None:
            config_dict = os.environ

        self.github_api_url = config_dict.get(
            "GITHUB_API_URL", "https://api.github.com"
        )
        self.github_pat = config_dict["GITHUB_PAT"]
        self.cache_ttl = int(config_dict.get("CACHE_TTL", "3600"))
        self.cache_backend_url = config_dict.get("CACHE_BACKEND_URL", "inmemory://")
        self.tokens = {
            token: env[len("TOKEN_") :].lower()
            for env, token in config_dict.items()
            if env.startswith("TOKEN_")
        }
