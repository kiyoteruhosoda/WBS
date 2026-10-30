from unittest.mock import patch


def test_shutdown_disabled_without_token(client) -> None:
    response = client.post("/admin/shutdown")
    assert response.status_code == 403
    assert "ADMIN_TOKEN" in response.json()["detail"]


def test_shutdown_rejected_with_wrong_token(client, monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "secret")
    response = client.post("/admin/shutdown", headers={"X-Admin-Token": "wrong"})
    assert response.status_code == 401


def test_shutdown_rejected_without_a_token_or_with_a_non_ascii_one(client, monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "secret")
    assert client.post("/admin/shutdown").status_code == 401
    # 比べる前に bytes にする（str のまま比べると ASCII 以外で TypeError になり 500 に化ける）
    assert client.post("/admin/shutdown", headers={"X-Admin-Token": "秘密".encode()}).status_code == 401


def test_shutdown_accepted_with_correct_token(client, monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "secret")
    with patch("os.kill") as mock_kill:
        response = client.post("/admin/shutdown", headers={"X-Admin-Token": "secret"})
    assert response.status_code == 202
    assert response.json() == {"message": "shutdown initiated"}
    mock_kill.assert_called_once()
