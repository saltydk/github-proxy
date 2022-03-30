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
