import operator
from datetime import datetime
from datetime import timedelta
from enum import Enum
from typing import Hashable
from typing import Iterator
from typing import Mapping
from typing import MutableMapping
from typing import NamedTuple
from typing import Optional
from typing import Protocol
from typing import Tuple
from typing import Union

from cachetools import TLRUCache  # type: ignore
from cachetools import cachedmethod
from github import GithubIntegration
from github.InstallationAuthorization import InstallationAuthorization


class GitHubAppConfig(NamedTuple):
    private_key: str
    id_: str
    installation_id: int


class GitHubTokenConfig(Hashable, Protocol):
    github_apps: Mapping[str, GitHubAppConfig]
    github_pats: Mapping[str, str]
    github_creds_cache_maxsize: int
    github_creds_cache_ttl_padding: int


class GitHubTokenOrigin(Enum):
    USER = "User"
    GITHUB_APP = "GitHub App"


class GitHubToken(NamedTuple):
    name: str
    origin: GitHubTokenOrigin
    value: str


RateLimited = MutableMapping[Tuple[GitHubTokenOrigin, str], datetime]

InstalledIntegration = Tuple[GithubIntegration, int]


def construct_installed_integration(
    app_name: str, config: GitHubTokenConfig, base_url: str
) -> InstalledIntegration:
    app_config = config.github_apps[app_name]
    return (
        CachedGithubIntegration(
            integration_id=app_config.id_,
            private_key=app_config.private_key,
            base_url=base_url,
            cache_maxsize=config.github_creds_cache_maxsize,
            cache_ttl_padding=config.github_creds_cache_ttl_padding,
        ),
        app_config.installation_id,
    )


class CachedGithubIntegration(GithubIntegration):
    """
    The GithubIntegration class is a utility of the PyGithub library
    for the purposes of obtaining access tokens for the installation of
    a GitHub App.
    Obtaining an installation access token is a 2-step process that invonlves
    the creation of a signed JWT, and a network call to the installations
    API. The returned access token expires after 1 hour.

    See https://docs.github.com/en/developers/apps/building-github-apps/authenticating-with-github-apps#authenticating-as-an-installation # noqa: E501
    for details.

    The purpose of this abstraction is to add a TLRU caching layer on top of the
    GithubIntegration class, so that a new token is generated ONLY if the existing
    one has expired.
    """

    def __init__(
        self,
        integration_id: Union[int, str],
        private_key: str,
        base_url: str,
        cache_maxsize: int,
        cache_ttl_padding: int,
    ) -> None:
        super().__init__(integration_id, private_key, base_url)

        def ttu(_key: str, value: InstallationAuthorization, now: datetime) -> datetime:
            # Derives the expiration time of the added value.

            # We are using timestamps returned from the GitHub servers
            # to mark item expiration. Hence, we cannot take advantage of monotonic
            # clock timestamps for the TTL comparison. The padding substraction
            # below is a safeguard against potential clock drift between
            # the GitHub server and the proxy.
            return value.expires_at - timedelta(minutes=cache_ttl_padding)

        self._cache = TLRUCache(
            maxsize=cache_maxsize,
            ttu=ttu,
            timer=datetime.utcnow,
        )

    @cachedmethod(operator.attrgetter("_cache"))
    def get_access_token(
        self, installation_id: int, user_id: Optional[int] = None
    ) -> InstallationAuthorization:
        return super().get_access_token(installation_id, user_id)


def token_generator(
    integrations: Mapping[str, InstalledIntegration],
    pats: Mapping[str, str],
    rate_limited: RateLimited,
) -> Iterator[GitHubToken]:
    """
    Lazy generator of GitHub tokens. Generates both GitHub App
    and user PAT tokens. Skips rate-limited ones.
    """
    # GitHub apps take precedence
    for app_name, (ghi, installation_id) in integrations.items():
        if (GitHubTokenOrigin.GITHUB_APP, app_name) in rate_limited:
            # rate-limited apps are skipped
            continue

        installation_authz = ghi.get_access_token(installation_id=installation_id)

        yield GitHubToken(
            name=app_name,
            origin=GitHubTokenOrigin.GITHUB_APP,
            value=installation_authz.token,
        )

    # Since there are no more apps, we can now yield GitHub user PATs
    for pat_name, pat in pats.items():
        if (GitHubTokenOrigin.USER, pat_name) in rate_limited:
            # rate-limited pats are skipped
            continue

        yield GitHubToken(
            name=pat_name,
            origin=GitHubTokenOrigin.USER,
            value=pat,
        )
