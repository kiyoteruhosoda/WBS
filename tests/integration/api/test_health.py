def test_healthcheck(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthcheck_via_api_prefix(client) -> None:
    """Path for external monitoring, assuming nginx forwards without stripping the /api/ prefix."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
