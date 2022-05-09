# github-proxy

[![CircleCI](https://circleci.com/gh/babylonhealth/github-proxy/tree/master.svg?style=svg)](https://circleci.com/gh/babylonhealth/github-proxy/tree/master) [![Maintainability](https://api.codeclimate.com/v1/badges/8b7eb3a3b43964bc98ed/maintainability)](https://codeclimate.com/repos/6278f1a41d5c1a018e0037ff/maintainability) [![Test Coverage](https://api.codeclimate.com/v1/badges/8b7eb3a3b43964bc98ed/test_coverage)](https://codeclimate.com/repos/6278f1a41d5c1a018e0037ff/test_coverage)

A caching forward proxy to GitHub's REST and GraphQL APIs. GitHub-Proxy is a thin, highly extensible, highly configurable python framework based on [Werkzeug](https://werkzeug.palletsprojects.com/). It comes with out-of-the-box support for Flask and Redis, but can be extended to integrate with other application frameworks, databases, and monitoring tools.

Features:

* Caching of GitHub responses based on [conditional requests](https://docs.github.com/en/rest/overview/resources-in-the-rest-api#conditional-requests).
* Improved and granular monitoring of client usage and [rate-limit](https://docs.github.com/en/rest/overview/resources-in-the-rest-api#rate-limiting) consumption.
* Provides a central and extensible pool of GitHub credentials (either GitHub Apps or user PATs) enabling rotation of rate-limited tokens. Negates the need of managing a GitHub App or bot user account per client.
* Coarse-grained and highly configurable authorization of clients based on API resource scopes.
* 100% compatible with GitHub's REST and GraphQL interfaces as well as the Enterprise API.

## Install

Core framework:

```console
$ pip install github-proxy
```

With support for Redis as a cache backend:

```console
$ pip install github-proxy[redis]
```

With Flask support:

```console
$ pip install github-proxy[flask]
```

Docker image: *(Coming Soon)*

```console
$ docker pull babylonhealth/github-proxy
```

## Usage

Flask integration:

```python
from github_proxy import blueprint

app = Flask(__name__)

app.register_blueprint(blueprint)
app.register_blueprint(
    blueprint, name="github_enterprise_proxy", url_prefix="/api/v3"
)  # enterprise server

if __name__ == "__main__":
    app.run()
```

Core framework (only needed for non-Flask applications):

```python
# Explicitly construct a proxy instance
from github_proxy import Proxy, Config, CacheBackend, TelemetryCollector

config = Config()
proxy = Proxy(
    github_api_url=config.github_api_url,
    github_token_config=config,
    cache=CacheBackend.factory(config),
    rate_limited={},
    clients=config.clients,
    tel_collector=TelemetryCollector.from_type(config.tel_collector_type),
)

# Or inject an instance loaded from the environment
from github_proxy import inject_proxy
from werkzeug import Request, Response

@inject_proxy
def request_handler(proxy: Proxy, request: Request) -> Response
    return proxy.request(request.path, request, "foo-client")
```

## Architecture

The need for such a solution stemmed from Babylon's reliance on [GitOps](https://about.gitlab.com/topics/gitops/) as an operational and change release framework. This led to a high (and at times abusive) usage of the GitHub API through a limited number of GitHub bot users. Frequent rate-limiting and lack of observability in terms of which client/workflow/team is abusing the API resulted in suboptimal developer experience.

High usage clients of the GitHub API are usually CI/CD pipelines and automated tests. These workflows are traditionally implemented as a collection of job processes executing independently to each other. This setup does not allow hot resources (and their Etags) to be shared across different workflows, or even jobs of the same workflow.

The GitHub-Proxy provides a centralised store of Etags that can be shared and re-used amongst its client base, letting workflows take full advantage of [conditional requests](https://docs.github.com/en/rest/overview/resources-in-the-rest-api#conditional-requests) which do not count against the rate limit.

```mermaid
graph LR
  subgraph clients
  A[CI job foo]
  C[CD job bar]
  D[Synthetic test baz]
  end
  A -- Auth via `Authorization: token REDACTED` HTTP header --> B[GitHub Proxy]
  C --> B
  D --> B
  B -- Auth via GitHub App or user PAT --> E[GitHub]
  B -- Read/Write responses of GitHub --> F[(Cache)]
  B -- Reporting of usage --> G[(Telemetry Collector)]
```

Sequence diagrams:

* [Cache hit](./docs/architecture/sequence-diagrams.md#cache-hit)
* [Cache miss](./docs/architecture/sequence-diagrams.md#cache-miss)

## Configuring the proxy

By default, the proxy loads its configuration using the `github_proxy.Config` class from the following 2 sources:

1. Environment variables
2. Client registry file

### Environment variables

* `GITHUB_API_URL`: Base url of the GitHub API server. Suffix with `/api/v3` when proxying to an Enterprise server. Defaults to: `https://api.github.com`.
* `CACHE_TTL`: The TTL (in seconds) of the cache that stores GitHub responses. Defaults to `3600`.
* `CACHE_BACKEND_URL`: URI of the cache backend that stores GitHub responses. The scheme of the URI infers the cache backend type. Defaults to `inmemory://`
* `GITHUB_CREDS_CACHE_MAXSIZE`: The max size of the inmemory cache used for storing rate limited GitHub credentials. Defaults to `256`.
* `GITHUB_CREDS_CACHE_TTL_PADDING`: The TTL padding (in minutes) of the inmemory cache used for storing rate limited GitHub credentials. This padding accounts for the clock drift between the proxy and the GitHub servers. Defaults to `10`.
* `TELEMETRY_COLLECTOR_TYPE`: The type of telemetry collector to be used. Defaults to `noop`.
* `CLIENT_REGISTRY_FILE_PATH`: Path to the client registry file. This is a __required__ variable.
* `GITHUB_PAT_*`: Variable pattern to specify GitHub user PATs that the proxy can use when integrating with the GitHub API. Example variable name: `GITHUB_PAT_BAR`.
* `GITHUB_APP_*_ID`: Variable pattern to specify GitHub App IDs that the proxy can use when integrating with the GitHub API. Example variable name: `GITHUB_APP_BAZ_ID`.
* `GITHUB_APP_*_INSTALLATION_ID`: Variable pattern to specify the GitHub App installation IDs that correspond to each of the GitHub App IDs. Example variable name: `GITHUB_APP_BAZ_INSTALLATION_ID`.
* `GITHUB_APP_*_PEM`: Variable pattern to specify the GitHub App private keys that correspond to each of the GitHub App IDs. Example variable name: `GITHUB_APP_BAZ_PEM`.


### Client registry file

This file specifies which clients are authorized to integrate with the proxy:

```yaml
---
version: 1
clients:
  - name: test
    token: H+hYxlecgRq7yfmhq2COlJk7tpSwDmdsp8thdPsnbnQ=
  - name: read_only
    token: oed4+Uo4s4mgwstjSAY/N+HSOsGwfbX91QxqSOjsVlU=
    scopes:
    - method: GET
      path: .*
...
```

The tokens included in this file (and hence the whole file) must be treated as secret. These are the authorization tokens that clients need to pass to the proxy (instead of a GitHub token).

## Extending the proxy

Adding a new type of cache backend:

```python
from github_proxy import CacheBackend, CacheBackendConfig

class PostgresCacheBackend(CacheBackend, scheme="postgres"):
    # Implement the __init__, _get, _set, and _make_key methods
    # of the CacheBackend interface
    pass
```

Adding a new type of telemetry collector:

```python
from github_proxy import TelemetryCollector

class JaegerTelemetryCollector(TelemetryCollector, type_="jaeger"):
    # Implement the collect_gh_response_metrics and collect_proxy_request_metrics 
    # methods of the TelemetryCollector interface
    pass
```

## Relevant references

1. [Google's magic GitHub proxy](https://github.com/google/magic-github-proxy): Proxy that enables IAM for GitHub API tokens.
2. [Sourcegraph's GitHub proxy](https://github.com/sourcegraph/sourcegraph/tree/main/cmd/github-proxy): Provides enhanced observability.
