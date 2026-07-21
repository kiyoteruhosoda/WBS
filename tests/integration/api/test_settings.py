def test_get_settings_defaults(client) -> None:
    response = client.get("/api/settings")
    assert response.status_code == 200
    data = response.json()
    assert data["timezone"] == "Asia/Tokyo"
    assert data["language"] == "ja"
    assert data["display_name"]


def test_update_language_and_timezone(client) -> None:
    response = client.put("/api/settings", json={"language": "en", "timezone": "America/New_York"})
    assert response.status_code == 200
    data = response.json()
    assert data["language"] == "en"
    assert data["timezone"] == "America/New_York"

    # 再取得しても保存されている
    data = client.get("/api/settings").json()
    assert data["language"] == "en"
    assert data["timezone"] == "America/New_York"


def test_update_display_name(client) -> None:
    response = client.put("/api/settings", json={"display_name": "Taro"})
    assert response.status_code == 200
    assert response.json()["display_name"] == "Taro"


def test_update_rejects_unknown_timezone(client) -> None:
    response = client.put("/api/settings", json={"timezone": "Mars/Olympus"})
    assert response.status_code == 422


def test_update_rejects_unsupported_language(client) -> None:
    response = client.put("/api/settings", json={"language": "fr"})
    assert response.status_code == 422


def test_partial_update_keeps_other_fields(client) -> None:
    client.put("/api/settings", json={"language": "en"})
    data = client.get("/api/settings").json()
    assert data["language"] == "en"
    assert data["timezone"] == "Asia/Tokyo"
