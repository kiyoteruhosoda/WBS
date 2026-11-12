"""Tests for the category and milestone create/edit API.

In particular, verify that "an explicit null clears a field" and
"fields not specified are left unchanged".
"""


def test_create_and_get_category(client) -> None:
    res = client.post("/api/categories", json={"name": "仕事", "color": "#0017C1", "sort_order": 2})
    assert res.status_code == 201
    created = res.json()
    assert created["name"] == "仕事"
    assert created["color"] == "#0017C1"
    assert created["sort_order"] == 2

    fetched = client.get(f"/api/categories/{created['id']}").json()
    assert fetched["name"] == "仕事"
    assert fetched["color"] == "#0017C1"


def test_update_category_clears_color_with_explicit_null(client) -> None:
    cat_id = client.post("/api/categories", json={"name": "私用", "color": "#1E8E4E"}).json()["id"]

    res = client.put(f"/api/categories/{cat_id}", json={"name": "私用", "color": None, "sort_order": 0})
    assert res.status_code == 200
    assert res.json()["color"] is None

    # The cleared value is persisted when fetched again
    assert client.get(f"/api/categories/{cat_id}").json()["color"] is None


def test_update_category_omitted_field_is_unchanged(client) -> None:
    cat_id = client.post("/api/categories", json={"name": "学習", "color": "#B26C00"}).json()["id"]

    # If color is not sent, the existing color is kept
    res = client.put(f"/api/categories/{cat_id}", json={"name": "学習(改)"})
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "学習(改)"
    assert body["color"] == "#B26C00"


def test_create_and_update_milestone_clears_optional_fields(client) -> None:
    created = client.post(
        "/api/milestones",
        json={"name": "v1リリース", "due_date": "2026-08-01", "description": "初回リリース"},
    ).json()
    mid = created["id"]
    assert created["due_date"] == "2026-08-01"
    assert created["description"] == "初回リリース"

    # Clear the due date and description with an explicit null
    res = client.put(
        f"/api/milestones/{mid}",
        json={"name": "v1リリース", "due_date": None, "description": None},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["due_date"] is None
    assert body["description"] is None

    refetched = client.get(f"/api/milestones/{mid}").json()
    assert refetched["due_date"] is None
    assert refetched["description"] is None


def test_update_milestone_omitted_fields_are_unchanged(client) -> None:
    mid = client.post(
        "/api/milestones",
        json={"name": "設計完了", "due_date": "2026-09-15", "description": "設計フェーズ"},
    ).json()["id"]

    # Only name changes, others unspecified → due date and description are kept
    res = client.put(f"/api/milestones/{mid}", json={"name": "設計完了(改)"})
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "設計完了(改)"
    assert body["due_date"] == "2026-09-15"
    assert body["description"] == "設計フェーズ"


def test_delete_category(client) -> None:
    cat_id = client.post("/api/categories", json={"name": "一時"}).json()["id"]
    assert client.delete(f"/api/categories/{cat_id}").status_code == 204
    assert client.get(f"/api/categories/{cat_id}").status_code == 404


def test_delete_milestone(client) -> None:
    mid = client.post("/api/milestones", json={"name": "一時MS"}).json()["id"]
    assert client.delete(f"/api/milestones/{mid}").status_code == 204
    assert client.get(f"/api/milestones/{mid}").status_code == 404
