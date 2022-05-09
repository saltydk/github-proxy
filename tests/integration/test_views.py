from flask.testing import FlaskClient

from tests.integration.vcr import vcr


@vcr.use_cassette
def test_caching_proxy_view_returns_uncached_response(
    client: FlaskClient, test_token: str
):
    resp = client.get("/zen", headers={"Authorization": f"token {test_token}"})
    assert resp.status_code == 200


@vcr.use_cassette
def test_caching_proxy_view_returns_cached_response(
    client: FlaskClient, test_token: str
):
    resource = "/users/dedoussis"
    resp1 = client.get(resource, headers={"Authorization": f"token {test_token}"})
    assert resp1.status_code == 200

    resp2 = client.get(resource, headers={"Authorization": f"token {test_token}"})
    assert resp1.status_code == 200

    # Even though the 2nd response did not yield a 304, rate-limit header equality
    # implies that the cached response was returned:
    for header in ["X-RateLimit-Used", "X-RateLimit-Remaining", "X-RateLimit-Reset"]:
        assert resp1.headers[header] == resp2.headers[header]


@vcr.use_cassette
def test_proxy_view_mutation_requests(client: FlaskClient, test_token: str):
    resource = "/markdown"
    resp = client.post(
        resource,
        headers={
            "Authorization": f"token {test_token}",
            "Accept": "application/vnd.github.v3+json",
        },
        json={"text": "text"},
    )
    assert resp.status_code == 200


@vcr.use_cassette
def test_caching_proxy_view_uses_query_string_when_indexing_cache(
    client: FlaskClient, test_token: str
):
    resource = "/repos/pallets/werkzeug/pulls"
    first_page_resp = client.get(
        resource,
        headers={"Authorization": f"token {test_token}"},
        query_string={"state": "closed", "per_page": 10, "page": 1},
    )
    assert first_page_resp.status_code == 200

    second_page_resp = client.get(
        resource,
        headers={"Authorization": f"token {test_token}"},
        query_string={"state": "closed", "per_page": 10, "page": 2},
    )
    assert second_page_resp.status_code == 200

    # second page response MUST not be a cached response of page 1
    assert first_page_resp.headers["Link"] != second_page_resp.headers["Link"]
    for header in ["X-RateLimit-Used", "X-RateLimit-Remaining"]:
        assert first_page_resp.headers[header] != second_page_resp.headers[header]


@vcr.use_cassette
def test_read_only_client_is_not_authorized_to_mutate_resources(
    client: FlaskClient, read_only_token: str
):
    # First we assert that the client can indeed read resources
    resp = client.get("/zen", headers={"Authorization": f"token {read_only_token}"})
    assert resp.status_code == 200

    resp = client.post(
        "/markdown",
        headers={
            "Authorization": f"token {read_only_token}",
            "Accept": "application/vnd.github.v3+json",
        },
        json={"text": "text"},
    )
    assert resp.status_code == 401
