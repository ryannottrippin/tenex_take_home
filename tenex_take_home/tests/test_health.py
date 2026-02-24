"""
Tests for GET /health

The health endpoint is unauthenticated and exists so load balancers and
operators can verify the backend process is alive.  It requires no external
services, so no mocking is needed.
"""


def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_health_returns_correct_body(client):
    response = client.get("/health")
    assert response.json() == {"status": "healthy"}


def test_health_is_accessible_without_auth(client):
    """No session cookie — endpoint must still succeed."""
    response = client.get("/health")
    assert response.status_code == 200
