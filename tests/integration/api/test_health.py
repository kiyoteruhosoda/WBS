def test_healthcheck(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthcheck_via_api_prefix(client) -> None:
    """nginx が /api/ プレフィックスを剥がさず転送する前提の外形監視用パス。"""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
