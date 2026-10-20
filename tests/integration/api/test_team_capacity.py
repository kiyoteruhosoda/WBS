"""メンバーの 1 日の工数・従事率と、チームの休日・各人の休み・タスクのアサイン比率（task #554 / ADR-0058）。

利用者を 2 人にして、だれが何を入れられるか（管理者・本人）と、根に付くこと・移したときの扱いを見る。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.infrastructure.auth.auth_settings import SINGLE_USER_ID
from src.infrastructure.database.models import UserModel
from src.presentation.api.dependencies import get_current_user, get_db

OTHER_EMAIL = "member@example.com"


def _as_user(user_id: int, email: str) -> Callable[[], AuthenticatedUserDTO]:
    def current() -> AuthenticatedUserDTO:
        return AuthenticatedUserDTO(
            user_id=user_id, email=email, display_name="仲間", timezone="Asia/Tokyo", language="ja",
        )

    return current


@pytest.fixture
def other_id(client) -> int:
    session = next(client.app.dependency_overrides.get(get_db, get_db)())
    try:
        user = UserModel(email=OTHER_EMAIL, display_name="仲間", timezone="Asia/Tokyo")
        session.add(user)
        session.commit()
        return user.id
    finally:
        session.close()


@pytest.fixture
def as_(client, other_id) -> Iterator:
    class Switch:
        def me(self) -> None:
            client.app.dependency_overrides.pop(get_current_user, None)

        def other(self) -> None:
            client.app.dependency_overrides[get_current_user] = _as_user(other_id, OTHER_EMAIL)

    switch = Switch()
    yield switch
    switch.me()


def _project(client, name: str, parent: int | None = None) -> dict:
    res = client.post("/api/projects", json={"name": name, "parent_project_id": parent})
    assert res.status_code == 201, res.text
    return res.json()


def _shared_root(client, other_id: int) -> dict:
    root = _project(client, "根")
    res = client.post(f"/api/projects/{root['id']}/members", json={"user_id": other_id})
    assert res.status_code == 200, res.text
    return root


def _capacity(members: dict, user_id: int) -> tuple[float, int]:
    member = next(m for m in members["members"] if m["user_id"] == user_id)
    return member["daily_hours"], member["engagement_percent"]


# ---- 1 日の工数と従事率（#554 AC1） ------------------------------------------------


def test_members_start_at_8_hours_and_100_percent(client, other_id) -> None:
    root = _shared_root(client, other_id)
    members = client.get(f"/api/projects/{root['id']}/members").json()
    assert _capacity(members, SINGLE_USER_ID) == (8.0, 100)
    assert _capacity(members, other_id) == (8.0, 100)


def test_a_manager_saves_anyones_capacity_from_any_level(client, other_id) -> None:
    root = _shared_root(client, other_id)
    child = _project(client, "子", parent=root["id"])
    res = client.put(
        f"/api/projects/{child['id']}/members/{other_id}/capacity",
        json={"daily_hours": 7.5, "engagement_percent": 50},
    )
    assert res.status_code == 200, res.text
    assert _capacity(res.json(), other_id) == (7.5, 50)
    # 根に付いている（読み直しても残る）
    assert _capacity(client.get(f"/api/projects/{root['id']}/members").json(), other_id) == (7.5, 50)


def test_a_member_changes_only_their_own_capacity(client, as_, other_id) -> None:
    root = _shared_root(client, other_id)
    as_.other()
    url = f"/api/projects/{root['id']}/members"
    mine = client.put(f"{url}/{other_id}/capacity", json={"daily_hours": 6, "engagement_percent": 80})
    assert mine.status_code == 200, mine.text
    assert _capacity(mine.json(), other_id) == (6.0, 80)
    theirs = client.put(f"{url}/{SINGLE_USER_ID}/capacity", json={"daily_hours": 6, "engagement_percent": 80})
    assert theirs.status_code == 403


@pytest.mark.parametrize(
    "body",
    [
        {"daily_hours": 25, "engagement_percent": 100},
        {"daily_hours": -1, "engagement_percent": 100},
        {"daily_hours": 8, "engagement_percent": 101},
        {"daily_hours": 8, "engagement_percent": -5},
    ],
)
def test_capacity_out_of_range_is_422(client, body) -> None:
    root = _project(client, "根")
    res = client.put(f"/api/projects/{root['id']}/members/{SINGLE_USER_ID}/capacity", json=body)
    assert res.status_code == 422, res.text


def test_capacity_of_a_non_member_is_404(client, other_id) -> None:
    root = _project(client, "根")
    res = client.put(
        f"/api/projects/{root['id']}/members/{other_id}/capacity", json={"daily_hours": 8, "engagement_percent": 50},
    )
    assert res.status_code == 404


# ---- チームの休日（#554 AC2） ---------------------------------------------------


def test_team_calendar_defaults_to_monday_to_friday(client) -> None:
    root = _project(client, "根")
    res = client.get(f"/api/projects/{root['id']}/calendar")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["root_project_id"] == root["id"]
    assert body["can_manage"] is True
    assert body["workdays"] == ["MO", "TU", "WE", "TH", "FR"]
    assert body["days_off"] == [] and body["leave"] == []


def test_manager_sets_workdays_on_the_root_and_days_off_on_the_project(client) -> None:
    root = _project(client, "根")
    child = _project(client, "子", parent=root["id"])
    base = f"/api/projects/{child['id']}/calendar"
    res = client.put(f"{base}/workdays", json={"workdays": ["SA", "MO", "TU", "WE", "TH", "FR"]})
    assert res.status_code == 200, res.text
    assert res.json()["workdays"] == ["MO", "TU", "WE", "TH", "FR", "SA"]
    assert client.put(f"{base}/workdays", json={"workdays": []}).status_code == 422
    # 曜日は根に 1 つ
    assert client.get(f"/api/projects/{root['id']}/calendar").json()["workdays"][-1] == "SA"

    client.post(f"{base}/days-off", json={"day": "2026-12-29", "name": "  年末  "})
    client.post(f"{base}/days-off", json={"day": "2026-12-28"})
    res = client.post(f"{base}/days-off", json={"day": "2026-12-29", "name": "年末休み"})
    own = {"project_id": child["id"], "inherited": False}
    assert res.json()["days_off"] == [
        {"day": "2026-12-28", "name": None, **own},
        {"day": "2026-12-29", "name": "年末休み", **own},
    ]
    # 子で足した休日は根には出ない
    assert client.get(f"/api/projects/{root['id']}/calendar").json()["days_off"] == []

    res = client.delete(f"{base}/days-off/2026-12-28")
    assert [d["day"] for d in res.json()["days_off"]] == ["2026-12-29"]
    ranged = client.get(f"{base}", params={"from": "2027-01-01", "to": "2027-12-31"}).json()
    assert ranged["days_off"] == []


def test_a_sub_project_inherits_the_days_off_of_its_ancestors(client) -> None:
    root = _project(client, "根")
    child = _project(client, "子", parent=root["id"])
    grandchild = _project(client, "孫", parent=child["id"])
    client.post(f"/api/projects/{root['id']}/calendar/days-off", json={"day": "2026-11-03", "name": "文化の日"})
    client.post(f"/api/projects/{child['id']}/calendar/days-off", json={"day": "2026-11-04", "name": "子の休み"})
    client.post(f"/api/projects/{grandchild['id']}/calendar/days-off", json={"day": "2026-11-05"})
    view = client.get(f"/api/projects/{grandchild['id']}/calendar").json()
    assert [(d["day"], d["project_id"], d["inherited"]) for d in view["days_off"]] == [
        ("2026-11-03", root["id"], True),
        ("2026-11-04", child["id"], True),
        ("2026-11-05", grandchild["id"], False),
    ]
    # 引き継いだ休日は子からは消せない（親のものはそのまま）
    client.delete(f"/api/projects/{grandchild['id']}/calendar/days-off/2026-11-03")
    view = client.get(f"/api/projects/{grandchild['id']}/calendar").json()
    assert "2026-11-03" in [d["day"] for d in view["days_off"]]
    # 同じ日を子でも足すと、子のものだけを出す
    client.post(f"/api/projects/{child['id']}/calendar/days-off", json={"day": "2026-11-03", "name": "子でも"})
    view = client.get(f"/api/projects/{child['id']}/calendar").json()
    assert view["days_off"][0] == {"day": "2026-11-03", "name": "子でも", "project_id": child["id"], "inherited": False}


def test_japanese_holidays_are_imported_without_overwriting(client) -> None:
    root = _project(client, "根")
    base = f"/api/projects/{root['id']}/calendar"
    client.post(f"{base}/days-off", json={"day": "2026-11-03", "name": "会社の名前"})
    res = client.post(f"{base}/days-off/japan", json={"year": 2026})
    assert res.status_code == 200, res.text
    days = {d["day"]: d["name"] for d in res.json()["days_off"]}
    assert days["2026-11-03"] == "会社の名前"
    assert days["2026-01-01"] == "元日"
    assert "2026-11-23" in days


def test_only_managers_change_the_team_calendar(client, as_, other_id) -> None:
    root = _shared_root(client, other_id)
    base = f"/api/projects/{root['id']}/calendar"
    as_.other()
    assert client.get(base).json()["can_manage"] is False
    assert client.put(f"{base}/workdays", json={"workdays": ["MO"]}).status_code == 403
    assert client.post(f"{base}/days-off", json={"day": "2026-12-29"}).status_code == 403
    assert client.post(f"{base}/days-off/japan", json={"year": 2026}).status_code == 403
    assert client.delete(f"{base}/days-off/2026-12-29").status_code == 403


def test_outsiders_see_no_team_calendar(client, as_) -> None:
    root = _project(client, "根")
    as_.other()
    assert client.get(f"/api/projects/{root['id']}/calendar").status_code == 404


def test_a_sub_project_taken_out_to_the_top_keeps_the_calendar(client) -> None:
    root = _project(client, "根")
    child = _project(client, "子", parent=root["id"])
    client.put(f"/api/projects/{root['id']}/calendar/workdays", json={"workdays": ["MO", "TU"]})
    client.post(f"/api/projects/{root['id']}/calendar/days-off", json={"day": "2026-12-29", "name": "年末"})
    res = client.post(f"/api/projects/{child['id']}/move", json={"parent_project_id": None})
    assert res.status_code == 200, res.text
    moved = client.get(f"/api/projects/{child['id']}/calendar").json()
    assert moved["root_project_id"] == child["id"]
    assert moved["workdays"] == ["MO", "TU"]
    assert moved["days_off"] == [{"day": "2026-12-29", "name": "年末", "project_id": child["id"], "inherited": False}]

    # 根を別の下へ入れると、曜日は移った先の根のものになり、休日は自分の休日として残る
    client.post(f"/api/projects/{child['id']}/calendar/days-off", json={"day": "2026-12-30"})
    res = client.post(f"/api/projects/{child['id']}/move", json={"parent_project_id": root["id"]})
    assert res.status_code == 200, res.text
    back = client.get(f"/api/projects/{child['id']}/calendar").json()
    assert back["root_project_id"] == root["id"]
    assert [(d["day"], d["inherited"]) for d in back["days_off"]] == [("2026-12-29", False), ("2026-12-30", False)]


def test_a_root_with_a_calendar_can_be_deleted(client) -> None:
    root = _project(client, "根")
    client.put(f"/api/projects/{root['id']}/calendar/workdays", json={"workdays": ["MO"]})
    client.post(f"/api/projects/{root['id']}/calendar/days-off", json={"day": "2026-12-29"})
    assert client.delete(f"/api/projects/{root['id']}").status_code == 204


# ---- 各人の休み（#554 AC2） -----------------------------------------------------


def test_member_enters_own_leave_and_the_manager_sees_it(client, as_, other_id) -> None:
    root = _shared_root(client, other_id)
    as_.other()
    res = client.post(f"/api/projects/{root['id']}/members/{other_id}/leave", json={"day": "2026-11-05"})
    assert res.status_code == 200, res.text
    assert client.post(
        f"/api/projects/{root['id']}/members/{SINGLE_USER_ID}/leave", json={"day": "2026-11-05"}
    ).status_code == 403

    as_.me()
    view = client.get(f"/api/projects/{root['id']}/calendar").json()
    assert view["leave"] == [{"user_id": other_id, "day": "2026-11-05", "off_percent": 100}]
    # 管理者は誰の休みでも入れ・消せる
    client.post(f"/api/projects/{root['id']}/members/{other_id}/leave", json={"day": "2026-11-06"})
    res = client.delete(f"/api/projects/{root['id']}/members/{other_id}/leave/2026-11-05")
    assert res.json()["leave"] == [{"user_id": other_id, "day": "2026-11-06", "off_percent": 100}]


def test_a_half_day_off_is_saved_and_changed(client, other_id) -> None:
    root = _shared_root(client, other_id)
    base = f"/api/projects/{root['id']}/members/{other_id}/leave"
    res = client.post(base, json={"day": "2026-11-05", "off_percent": 50})
    assert res.status_code == 200, res.text
    assert res.json()["leave"] == [{"user_id": other_id, "day": "2026-11-05", "off_percent": 50}]
    res = client.post(base, json={"day": "2026-11-05", "off_percent": 100})
    assert res.json()["leave"] == [{"user_id": other_id, "day": "2026-11-05", "off_percent": 100}]
    assert client.post(base, json={"day": "2026-11-05", "off_percent": 0}).status_code == 422
    assert client.post(base, json={"day": "2026-11-05", "off_percent": 101}).status_code == 422


def test_leave_is_the_same_across_projects(client, as_, other_id) -> None:
    first = _shared_root(client, other_id)
    second = _project(client, "別の根")
    client.post(f"/api/projects/{second['id']}/members", json={"user_id": other_id})
    client.post(f"/api/projects/{first['id']}/members/{other_id}/leave", json={"day": "2026-11-05"})
    view = client.get(f"/api/projects/{second['id']}/calendar").json()
    assert view["leave"] == [{"user_id": other_id, "day": "2026-11-05", "off_percent": 100}]


def test_leave_of_a_non_member_is_404(client, other_id) -> None:
    root = _project(client, "根")
    res = client.post(f"/api/projects/{root['id']}/members/{other_id}/leave", json={"day": "2026-11-05"})
    assert res.status_code == 404


# ---- アサイン比率 ------------------------------------------------------------


def test_allocation_percent_is_saved_and_cleared(client) -> None:
    root = _project(client, "根")
    res = client.post("/api/tasks", json={"title": "半分だけ", "project_id": root["id"], "allocation_percent": 50})
    assert res.status_code == 201, res.text
    task = res.json()
    assert task["allocation_percent"] == 50
    res = client.put(f"/api/tasks/{task['id']}", json={"title": "名前だけ"})
    assert res.json()["allocation_percent"] == 50  # 送らなければ触らない
    res = client.put(f"/api/tasks/{task['id']}", json={"allocation_percent": None})
    assert res.json()["allocation_percent"] is None
    assert client.put(f"/api/tasks/{task['id']}", json={"allocation_percent": 0}).status_code == 422
    assert client.put(f"/api/tasks/{task['id']}", json={"allocation_percent": 101}).status_code == 422
