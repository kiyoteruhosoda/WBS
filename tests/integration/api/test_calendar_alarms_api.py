"""予定の通知（task #183、ADR-0021）。

- 予定の通知の設定: 作るときに省くと既定（4 つとも入り）、``null`` は通知なし、直すときに省くと今のまま
- この先の通知 ``GET /api/calendar/alarms?from=&to=``: 単発・繰り返し・移した回・飛ばした回・止めた通知・
  終日・期間の上限・他人の予定
- 打刻アプリの Bearer（ADR-0018 を広げた）でも読める。Cookie の口もそのまま

日付は 2026-10-05（月）からの週。既定の利用者は Asia/Tokyo（9:00 JST = 0:00Z）。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.infrastructure.database.models import UserModel
from src.presentation.api.dependencies import get_app_or_web_user, get_db
from tests.integration.api.test_app_bearer import app_client, bearer  # noqa: F401 - fixture を借りる
from tests.integration.api.test_auth import sign_in, sso_provider  # noqa: F401 - fixture を借りる

WEEKLY_MON_WED = {"type": "WEEKLY", "interval": 1, "weekly": {"weekdays": ["MO", "WE"]}}
DEFAULT_ALARM = {
    "enabled": True,
    "notify_15_min": True,
    "notify_5_min": True,
    "notify_1_min": True,
    "notify_at_start": True,
}
AT_START_ONLY = {
    "enabled": True,
    "notify_15_min": False,
    "notify_5_min": False,
    "notify_1_min": False,
    "notify_at_start": True,
}


def _create(client: TestClient, **fields) -> dict:
    body = {"title": "予定", "start": "2026-10-05T01:00:00Z", "duration_minutes": 60, **fields}
    res = client.post("/api/calendar/events", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _alarms(client: TestClient, start: str, end: str, **kwargs) -> list[dict]:
    res = client.get("/api/calendar/alarms", params={"from": start, "to": end}, **kwargs)
    assert res.status_code == 200, res.text
    return res.json()["alarms"]


def _when(alarms: list[dict]) -> list[tuple[str, int]]:
    return [(a["notify_at"], a["minutes_before"]) for a in alarms]


# ── 予定の通知の設定 ────────────────────────────────────────────────────────


def test_a_new_event_gets_the_default_alarm_unless_told_otherwise(client) -> None:
    assert _create(client)["alarm"] == DEFAULT_ALARM
    assert _create(client, alarm=None)["alarm"] is None
    assert _create(client, alarm=AT_START_ONLY)["alarm"] == AT_START_ONLY


def test_updating_without_alarm_keeps_it_and_null_removes_it(client) -> None:
    created = _create(client, alarm=AT_START_ONLY)
    kept = client.put(
        f"/api/calendar/events/{created['id']}",
        json={"title": "改名", "expected_version": created["version"]},
    )
    assert kept.status_code == 200, kept.text
    assert kept.json()["alarm"] == AT_START_ONLY

    removed = client.put(
        f"/api/calendar/events/{created['id']}",
        json={"title": "改名", "alarm": None, "expected_version": kept.json()["version"]},
    )
    assert removed.json()["alarm"] is None


def test_series_edits_carry_the_alarm(client) -> None:
    series = _create(client, title="定例", start="2026-10-05T00:00:00Z", recurrence=WEEKLY_MON_WED,
                     alarm=AT_START_ONLY)
    # この回だけ: 省くと元の系列の通知を引き継ぐ
    split = client.post(
        f"/api/calendar/events/{series['id']}/occurrences/split",
        json={
            "occurrence": {"date": "2026-10-07", "start_time": "09:00"},
            "title": "定例（今回だけ）",
            "start": "2026-10-07T02:00:00Z",
            "duration_minutes": 60,
            "expected_version": series["version"],
        },
    )
    assert split.status_code == 201, split.text
    assert split.json()["alarm"] == AT_START_ONLY

    # この回以降: 送ればそれに変わる
    current = client.get(f"/api/calendar/events/{series['id']}").json()
    following = client.post(
        f"/api/calendar/events/{series['id']}/occurrences/following",
        json={
            "occurrence": {"date": "2026-10-12", "start_time": "09:00"},
            "title": "定例",
            "start": "2026-10-12T00:00:00Z",
            "duration_minutes": 60,
            "recurrence": WEEKLY_MON_WED,
            "alarm": DEFAULT_ALARM,
            "expected_version": current["version"],
        },
    )
    assert following.status_code == 201, following.text
    assert following.json()["alarm"] == DEFAULT_ALARM

    # すべて: null で外せる
    current = client.get(f"/api/calendar/events/{series['id']}").json()
    whole = client.put(
        f"/api/calendar/events/{series['id']}/series",
        json={
            "title": "定例",
            "duration_minutes": 60,
            "recurrence": current["recurrence"],
            "alarm": None,
            "expected_version": current["version"],
        },
    )
    assert whole.status_code == 200, whole.text
    assert whole.json()["alarm"] is None


def test_occurrences_carry_the_alarm_of_their_event(client) -> None:
    _create(client, alarm=AT_START_ONLY)
    [occurrence] = client.get(
        "/api/calendar/occurrences", params={"from": "2026-10-05", "to": "2026-10-05"}
    ).json()
    assert occurrence["alarm"] == AT_START_ONLY


# ── この先の通知 ────────────────────────────────────────────────────────────


def test_a_single_event_rings_at_each_offset_before_its_start(client) -> None:
    created = _create(client, title="打合せ", location="会議室A")
    alarms = _alarms(client, "2026-10-05T00:00:00Z", "2026-10-05T02:00:00Z")
    assert _when(alarms) == [
        ("2026-10-05T00:45:00Z", 15),
        ("2026-10-05T00:55:00Z", 5),
        ("2026-10-05T00:59:00Z", 1),
        ("2026-10-05T01:00:00Z", 0),
    ]
    assert alarms[0] == {
        "id": f"{created['id']}:2026-10-05T01:00:00Z:15",
        "occurrence_id": f"{created['id']}:2026-10-05T01:00:00Z",
        "event_id": created["id"],
        "title": "打合せ",
        "location": "会議室A",
        "task_id": None,
        "task_title": None,
        "starts_at": "2026-10-05T01:00:00Z",
        "duration_minutes": 60,
        "notify_at": "2026-10-05T00:45:00Z",
        "minutes_before": 15,
        "is_recurring": False,
    }


def test_the_window_includes_from_and_excludes_to(client) -> None:
    _create(client)
    res = client.get(
        "/api/calendar/alarms",
        params={"from": "2026-10-05T00:55:00Z", "to": "2026-10-05T01:00:00Z"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["window_start"] == "2026-10-05T00:55:00Z"
    assert body["window_end"] == "2026-10-05T01:00:00Z"
    assert _when(body["alarms"]) == [("2026-10-05T00:55:00Z", 5), ("2026-10-05T00:59:00Z", 1)]


def test_offsets_in_the_query_are_read_as_instants(client) -> None:
    _create(client, alarm=AT_START_ONLY)
    # 10:00 JST = 01:00Z。境目ちょうどは含む
    alarms = _alarms(client, "2026-10-05T10:00:00+09:00", "2026-10-05T10:01:00+09:00")
    assert _when(alarms) == [("2026-10-05T01:00:00Z", 0)]


def test_recurring_events_are_expanded_like_the_calendar(client) -> None:
    series = _create(client, title="定例", start="2026-10-05T00:00:00Z", recurrence=WEEKLY_MON_WED,
                     alarm=AT_START_ONLY)
    alarms = _alarms(client, "2026-10-04T00:00:00Z", "2026-10-11T00:00:00Z")
    assert [(a["starts_at"], a["is_recurring"]) for a in alarms] == [
        ("2026-10-05T00:00:00Z", True),
        ("2026-10-07T00:00:00Z", True),
    ]
    assert {a["event_id"] for a in alarms} == {series["id"]}
    assert alarms[1]["occurrence_id"] == f"{series['id']}:2026-10-07T00:00:00Z"


def test_a_moved_occurrence_rings_where_it_was_moved_to(client) -> None:
    series = _create(client, title="定例", start="2026-10-05T00:00:00Z", recurrence=WEEKLY_MON_WED,
                     alarm=AT_START_ONLY)
    moved = client.post(
        f"/api/calendar/events/{series['id']}/occurrences/move",
        json={
            "occurrence": {"date": "2026-10-07", "start_time": "09:00"},
            "start": "2026-10-08T03:00:00Z",
            "duration_minutes": 30,
            "expected_version": series["version"],
        },
    )
    assert moved.status_code == 200, moved.text
    alarms = _alarms(client, "2026-10-04T00:00:00Z", "2026-10-11T00:00:00Z")
    assert [(a["starts_at"], a["duration_minutes"]) for a in alarms] == [
        ("2026-10-05T00:00:00Z", 60),
        ("2026-10-08T03:00:00Z", 30),
    ]


def test_a_skipped_occurrence_does_not_ring(client) -> None:
    series = _create(client, title="定例", start="2026-10-05T00:00:00Z", recurrence=WEEKLY_MON_WED,
                     alarm=AT_START_ONLY)
    skipped = client.post(
        f"/api/calendar/events/{series['id']}/occurrences/skip",
        json={"occurrence": {"date": "2026-10-05", "start_time": "09:00"},
              "expected_version": series["version"]},
    )
    assert skipped.status_code == 200, skipped.text
    alarms = _alarms(client, "2026-10-04T00:00:00Z", "2026-10-11T00:00:00Z")
    assert [a["starts_at"] for a in alarms] == ["2026-10-07T00:00:00Z"]


def test_events_without_an_enabled_alarm_do_not_ring(client) -> None:
    _create(client, title="通知なし", alarm=None)
    _create(client, title="止めた", alarm={**DEFAULT_ALARM, "enabled": False})
    _create(client, title="どれも選ばない", alarm={**DEFAULT_ALARM, "notify_15_min": False,
                                                   "notify_5_min": False, "notify_1_min": False,
                                                   "notify_at_start": False})
    # 終日（ローカル 0:00 ＋ 1440 分）には意味のある開始時刻が無い
    _create(client, title="終日", start="2026-10-04T15:00:00Z", duration_minutes=1440)
    assert _alarms(client, "2026-10-04T00:00:00Z", "2026-10-06T00:00:00Z") == []


def test_a_linked_task_is_named(client) -> None:
    task = client.post("/api/tasks", json={"title": "設計書"})
    assert task.status_code == 201, task.text
    _create(client, task_id=task.json()["id"], alarm=AT_START_ONLY)
    [alarm] = _alarms(client, "2026-10-05T00:00:00Z", "2026-10-05T02:00:00Z")
    assert (alarm["task_id"], alarm["task_title"]) == (task.json()["id"], "設計書")


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2026-10-05T00:00:00Z", "2026-10-12T00:01:00Z"),  # 7 日を超える
        ("2026-10-05T00:00:00Z", "2026-10-05T00:00:00Z"),  # 空
        ("2026-10-05T01:00:00Z", "2026-10-05T00:00:00Z"),  # 逆
    ],
    ids=["longer-than-7-days", "empty", "reversed"],
)
def test_the_window_is_checked(client, start, end) -> None:
    res = client.get("/api/calendar/alarms", params={"from": start, "to": end})
    assert res.status_code == 422, res.text


def test_a_window_of_exactly_7_days_is_allowed(client) -> None:
    res = client.get(
        "/api/calendar/alarms", params={"from": "2026-10-05T00:00:00Z", "to": "2026-10-12T00:00:00Z"}
    )
    assert res.status_code == 200, res.text


def test_both_ends_are_required(client) -> None:
    assert client.get("/api/calendar/alarms", params={"from": "2026-10-05T00:00:00Z"}).status_code == 422
    assert client.get("/api/calendar/alarms").status_code == 422


def test_other_users_events_are_not_returned(client) -> None:
    _create(client)
    session = next(get_db())
    try:
        other = UserModel(email="other@example.com", display_name="他人")
        session.add(other)
        session.flush()
        other_id = other.id
        session.commit()
    finally:
        session.close()
    client.app.dependency_overrides[get_app_or_web_user] = lambda: AuthenticatedUserDTO(
        user_id=other_id, email="other@example.com", display_name="他人",
        timezone="Asia/Tokyo", language="ja",
    )
    try:
        assert _alarms(client, "2026-10-05T00:00:00Z", "2026-10-05T02:00:00Z") == []
    finally:
        client.app.dependency_overrides.pop(get_app_or_web_user, None)
    assert len(_alarms(client, "2026-10-05T00:00:00Z", "2026-10-05T02:00:00Z")) == 4


# ── 打刻アプリ（Bearer） ────────────────────────────────────────────────────


def _create_on_the_web(client: TestClient, code: str) -> dict:
    sign_in(client, code)
    try:
        return _create(client, time_zone="Asia/Tokyo", alarm=AT_START_ONLY)
    finally:
        client.cookies.clear()


def test_the_app_reads_alarms_with_its_token(app_client) -> None:  # noqa: F811
    created = _create_on_the_web(app_client, "taro-code")
    alarms = _alarms(
        app_client, "2026-10-05T00:00:00Z", "2026-10-05T02:00:00Z", headers=bearer("taro-app")
    )
    assert [(a["event_id"], a["minutes_before"]) for a in alarms] == [(created["id"], 0)]
    # 他人のトークンでは見えない
    assert _alarms(
        app_client, "2026-10-05T00:00:00Z", "2026-10-05T02:00:00Z", headers=bearer("hanako-app")
    ) == []


def test_the_web_still_reads_alarms_with_its_cookie(app_client) -> None:  # noqa: F811
    _create_on_the_web(app_client, "taro-code")
    sign_in(app_client, "taro-code")
    assert len(_alarms(app_client, "2026-10-05T00:00:00Z", "2026-10-05T02:00:00Z")) == 1


@pytest.mark.parametrize("token", ["unknown-token", "other-client", "machine"])
def test_tokens_that_are_not_ours_cannot_read_alarms(app_client, token) -> None:  # noqa: F811
    res = app_client.get(
        "/api/calendar/alarms",
        params={"from": "2026-10-05T00:00:00Z", "to": "2026-10-05T02:00:00Z"},
        headers=bearer(token),
    )
    assert res.status_code == 401


def test_the_token_still_cannot_write_or_read_other_calendar_routes(app_client) -> None:  # noqa: F811
    created = _create_on_the_web(app_client, "taro-code")
    headers = bearer("taro-app")
    assert app_client.get(
        "/api/calendar/occurrences", params={"from": "2026-10-05", "to": "2026-10-05"},
        headers=headers,
    ).status_code == 401
    assert app_client.get(f"/api/calendar/events/{created['id']}", headers=headers).status_code == 401
    assert app_client.post(
        "/api/calendar/events",
        json={"title": "x", "start": "2026-10-05T01:00:00Z", "duration_minutes": 30},
        headers=headers,
    ).status_code == 401
