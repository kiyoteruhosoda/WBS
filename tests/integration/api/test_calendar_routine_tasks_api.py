"""予定の分類（予定 / タスク）と、タスクの回の「済み」（task #190、ADR-0025）。

- 分類は作るときの既定が予定（EVENT）。タスク（TASK）は WBS のタスクに結ぶ（無ければ 422）
- 済みは回ごと（繰り返しは回の鍵 ``series_key``、単発は鍵なし）。予定の版は進まない
- 移した回は元の鍵のまま済みが付いて回る。この回だけ切り出すと済みは新しい単発へ移る
- 系列の開始時刻を変えても済みは同じ回に残る。以降を分けると、以降の済みは新しい系列へ
- 他人の予定・回には付けられない（404）。予定の分類には付けられない（422）。無い回は 404

日付は 2026-10-05（月）からの週。既定の利用者は Asia/Tokyo。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.infrastructure.database.models import UserModel
from src.presentation.api.dependencies import get_current_user, get_db

OTHER_EMAIL = "other@example.com"
DAILY_WEEKDAYS = {
    "type": "WEEKLY", "interval": 1, "weekly": {"weekdays": ["MO", "TU", "WE", "TH", "FR"]},
}


def _as_user(user_id: int, email: str) -> Callable[[], AuthenticatedUserDTO]:
    def current() -> AuthenticatedUserDTO:
        return AuthenticatedUserDTO(
            user_id=user_id, email=email, display_name=email,
            timezone="Asia/Tokyo", language="ja",
        )

    return current


@pytest.fixture
def two_users(client) -> Iterator:
    session = next(get_db())
    try:
        user = UserModel(email=OTHER_EMAIL, display_name="他人")
        session.add(user)
        session.flush()
        other_id = user.id
        session.commit()
    finally:
        session.close()

    class Switch:
        def me(self) -> None:
            client.app.dependency_overrides.pop(get_current_user, None)

        def other(self) -> None:
            client.app.dependency_overrides[get_current_user] = _as_user(other_id, OTHER_EMAIL)

    switch = Switch()
    yield switch
    switch.me()


def _task(client, title: str = "日報") -> int:
    res = client.post("/api/tasks", json={"title": title})
    assert res.status_code in (200, 201), res.text
    return res.json()["id"]


def _create(client, **fields) -> dict:
    body = {"title": "日報", "start": "2026-10-05T00:00:00Z", "duration_minutes": 30, **fields}
    res = client.post("/api/calendar/events", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _routine(client, **fields) -> dict:
    """平日の毎日 9:00〜9:30 のタスク（定常業務）。"""
    task_id = fields.pop("task_id", None) or _task(client)
    return _create(
        client, event_type="TASK", task_id=task_id, recurrence=DAILY_WEEKDAYS, **fields
    )


def _occurrences(client, start: str, end: str) -> list[dict]:
    res = client.get("/api/calendar/occurrences", params={"from": start, "to": end})
    assert res.status_code == 200, res.text
    return res.json()


def _done(client, event_id: int, occurrence: dict | None, done: bool = True):
    return client.put(
        f"/api/calendar/events/{event_id}/done", json={"occurrence": occurrence, "done": done}
    )


def _key(day: str, at: str = "09:00") -> dict:
    return {"date": day, "start_time": at}


def _done_dates(client, start: str, end: str) -> list[str]:
    return [o["date"] for o in _occurrences(client, start, end) if o["is_done"]]


# ── 分類 ────────────────────────────────────────────────────────────────────


def test_event_type_defaults_to_event_and_task_needs_a_task(client) -> None:
    plain = _create(client)
    assert plain["event_type"] == "EVENT"

    # タスクの分類はタスクに結ぶ（打刻・締めで実績を確定するのに要る）
    res = client.post(
        "/api/calendar/events",
        json={"title": "日報", "start": "2026-10-05T00:00:00Z", "duration_minutes": 30,
              "event_type": "TASK"},
    )
    assert res.status_code == 422

    routine = _routine(client)
    assert routine["event_type"] == "TASK"
    occurrences = _occurrences(client, "2026-10-05", "2026-10-09")
    assert [(o["event_type"], o["is_done"]) for o in occurrences if o["event_id"] == routine["id"]] == [
        ("TASK", False)
    ] * 5


def test_event_type_is_kept_unless_given_and_can_be_changed(client) -> None:
    task_id = _task(client)
    created = _create(client, task_id=task_id)
    url = f"/api/calendar/events/{created['id']}"

    # 省くと今のまま
    res = client.put(url, json={"title": "日報", "task_id": task_id})
    assert res.status_code == 200, res.text
    assert res.json()["event_type"] == "EVENT"

    res = client.put(url, json={"title": "日報", "task_id": task_id, "event_type": "TASK"})
    assert res.status_code == 200, res.text
    assert res.json()["event_type"] == "TASK"

    # タスクのまま結びを外すことはできない
    res = client.put(url, json={"title": "日報", "task_id": None})
    assert res.status_code == 422
    assert client.get(url).json()["task_id"] == task_id

    # ドラッグ（分類を送らない詳細の置き換え）でも分類は残る
    res = client.put(
        url,
        json={"title": "日報", "task_id": task_id, "start": "2026-10-05T01:00:00Z",
              "duration_minutes": 30, "color_key": None},
    )
    assert res.status_code == 200, res.text
    assert res.json()["event_type"] == "TASK"


def test_series_update_keeps_or_changes_the_event_type(client) -> None:
    routine = _routine(client)
    url = f"/api/calendar/events/{routine['id']}/series"
    body = {"title": "日報", "duration_minutes": 30, "recurrence": DAILY_WEEKDAYS,
            "task_id": routine["task_id"]}
    res = client.put(url, json=body)
    assert res.status_code == 200, res.text
    assert res.json()["event_type"] == "TASK"
    res = client.put(url, json={**body, "event_type": "EVENT"})
    assert res.status_code == 200, res.text
    assert res.json()["event_type"] == "EVENT"


# ── 済み ────────────────────────────────────────────────────────────────────


def test_each_occurrence_of_a_routine_is_done_separately(client) -> None:
    routine = _routine(client)
    res = _done(client, routine["id"], _key("2026-10-06"))
    assert res.status_code == 200, res.text
    assert res.json() == {
        "event_id": routine["id"],
        "occurrence": {"date": "2026-10-06", "start_time": "09:00"},
        "done": True,
    }
    # 何度付けても同じ
    assert _done(client, routine["id"], _key("2026-10-06")).status_code == 200
    assert _done(client, routine["id"], _key("2026-10-08")).status_code == 200
    assert _done_dates(client, "2026-10-05", "2026-10-09") == ["2026-10-06", "2026-10-08"]

    # 済みは予定の版を進めない（開いている編集画面を 409 にしない）
    assert client.get(f"/api/calendar/events/{routine['id']}").json()["version"] == routine["version"]

    # 外す
    res = _done(client, routine["id"], _key("2026-10-06"), done=False)
    assert res.status_code == 200, res.text
    assert res.json()["done"] is False
    assert _done(client, routine["id"], _key("2026-10-06"), done=False).status_code == 200
    assert _done_dates(client, "2026-10-05", "2026-10-09") == ["2026-10-08"]


def test_single_task_is_done_without_a_key(client) -> None:
    single = _create(client, event_type="TASK", task_id=_task(client))
    assert _done(client, single["id"], None).status_code == 200
    [occurrence] = _occurrences(client, "2026-10-05", "2026-10-05")
    assert occurrence["is_done"] is True

    # 単発を動かしても済みのまま（鍵は予定そのもの）
    res = client.put(
        f"/api/calendar/events/{single['id']}",
        json={"title": "日報", "task_id": single["task_id"], "start": "2026-10-06T00:00:00Z",
              "duration_minutes": 30},
    )
    assert res.status_code == 200, res.text
    [moved] = _occurrences(client, "2026-10-06", "2026-10-06")
    assert moved["is_done"] is True

    # 単発に回の鍵を渡すのは 422
    assert _done(client, single["id"], _key("2026-10-06")).status_code == 422


def test_plain_events_and_missing_occurrences_cannot_be_done(client) -> None:
    plain = _create(client, recurrence=DAILY_WEEKDAYS)
    assert _done(client, plain["id"], _key("2026-10-05")).status_code == 422

    routine = _routine(client)
    # 繰り返しは回の鍵が要る
    assert _done(client, routine["id"], None).status_code == 422
    # 土曜は回が無い・時刻が系列の開始時刻でない
    assert _done(client, routine["id"], _key("2026-10-10")).status_code == 404
    assert _done(client, routine["id"], _key("2026-10-06", "10:00")).status_code == 404
    # 飛ばした回にも付けられない
    url = f"/api/calendar/events/{routine['id']}/occurrences"
    assert client.post(f"{url}/skip", json={"occurrence": _key("2026-10-07")}).status_code == 200
    assert _done(client, routine["id"], _key("2026-10-07")).status_code == 404
    assert _done(client, 999_999, None).status_code == 404


def test_someone_elses_routine_cannot_be_done_or_seen(client, two_users) -> None:
    two_users.other()
    theirs = _routine(client, title="他人の日報")
    assert _done(client, theirs["id"], _key("2026-10-05")).status_code == 200
    two_users.me()

    assert _done(client, theirs["id"], _key("2026-10-06")).status_code == 404
    assert _done(client, theirs["id"], _key("2026-10-05"), done=False).status_code == 404
    assert _occurrences(client, "2026-10-05", "2026-10-09") == []

    # 他人のものは変わっていない
    two_users.other()
    assert _done_dates(client, "2026-10-05", "2026-10-09") == ["2026-10-05"]


def test_a_moved_occurrence_keeps_its_done_mark(client) -> None:
    routine = _routine(client)
    url = f"/api/calendar/events/{routine['id']}/occurrences"
    res = client.post(
        f"{url}/move",
        json={"occurrence": _key("2026-10-07"), "start": "2026-10-10T05:00:00Z",
              "duration_minutes": 30},
    )
    assert res.status_code == 200, res.text
    version = res.json()["version"]

    # 移した回（土曜 14:00）は元の鍵で済みにする
    moved = next(o for o in _occurrences(client, "2026-10-10", "2026-10-10"))
    assert moved["is_moved"] is True
    assert _done(client, routine["id"], moved["series_key"]).status_code == 200
    assert _done_dates(client, "2026-10-05", "2026-10-11") == ["2026-10-10"]

    # 移動を取り消して元の位置へ戻しても、同じ回なので済みのまま
    res = client.post(
        f"{url}/cancel-move",
        json={"occurrence": _key("2026-10-07"), "expected_version": version},
    )
    assert res.status_code == 200, res.text
    assert _done_dates(client, "2026-10-05", "2026-10-11") == ["2026-10-07"]


def test_splitting_this_occurrence_carries_the_done_mark(client) -> None:
    routine = _routine(client)
    assert _done(client, routine["id"], _key("2026-10-07")).status_code == 200
    res = client.post(
        f"/api/calendar/events/{routine['id']}/occurrences/split",
        json={"occurrence": _key("2026-10-07"), "title": "日報（午後）",
              "start": "2026-10-07T05:00:00Z", "duration_minutes": 30},
    )
    assert res.status_code == 201, res.text
    single = res.json()
    # この回だけの単発は分類と結んだタスクを系列から引き継ぐ
    assert (single["event_type"], single["task_id"]) == ("TASK", routine["task_id"])

    occurrences = _occurrences(client, "2026-10-07", "2026-10-07")
    assert [(o["title"], o["is_done"]) for o in occurrences] == [("日報（午後）", True)]
    # 系列へ戻しても（飛ばしを取り消しても）、済みは単発へ移ったので系列の回は済みでない
    url = f"/api/calendar/events/{routine['id']}/occurrences"
    assert client.post(f"{url}/restore", json={"occurrence": _key("2026-10-07")}).status_code == 200
    occurrences = _occurrences(client, "2026-10-07", "2026-10-07")
    assert sorted((o["title"], o["is_done"]) for o in occurrences) == [
        ("日報", False), ("日報（午後）", True),
    ]


def test_changing_the_series_start_time_keeps_done_marks_on_the_same_occurrences(client) -> None:
    routine = _routine(client)
    assert _done(client, routine["id"], _key("2026-10-06")).status_code == 200
    res = client.put(
        f"/api/calendar/events/{routine['id']}/series",
        json={"title": "日報", "duration_minutes": 30, "recurrence": DAILY_WEEKDAYS,
              "task_id": routine["task_id"], "start": "2026-10-05T01:00:00Z"},
    )
    assert res.status_code == 200, res.text
    occurrences = _occurrences(client, "2026-10-05", "2026-10-09")
    assert [(o["date"], o["start_time"]) for o in occurrences if o["is_done"]] == [
        ("2026-10-06", "10:00")
    ]
    # 鍵も新しい開始時刻になっている（外せる）
    assert _done(client, routine["id"], _key("2026-10-06", "10:00"), done=False).status_code == 200
    assert _done_dates(client, "2026-10-05", "2026-10-09") == []


def test_this_and_following_moves_later_done_marks_to_the_new_series(client) -> None:
    routine = _routine(client)
    for day in ("2026-10-05", "2026-10-08"):
        assert _done(client, routine["id"], _key(day)).status_code == 200
    res = client.post(
        f"/api/calendar/events/{routine['id']}/occurrences/following",
        json={"occurrence": _key("2026-10-07"), "title": "日報（新）", "recurrence": DAILY_WEEKDAYS,
              "start": "2026-10-07T00:00:00Z", "duration_minutes": 45},
    )
    assert res.status_code == 201, res.text
    new_series = res.json()
    assert (new_series["event_type"], new_series["task_id"]) == ("TASK", routine["task_id"])

    occurrences = _occurrences(client, "2026-10-05", "2026-10-09")
    assert [(o["date"], o["title"], o["is_done"]) for o in occurrences] == [
        ("2026-10-05", "日報", True),
        ("2026-10-06", "日報", False),
        ("2026-10-07", "日報（新）", False),
        ("2026-10-08", "日報（新）", True),
        ("2026-10-09", "日報（新）", False),
    ]


def test_deleting_a_routine_forgets_its_done_marks(client) -> None:
    routine = _routine(client)
    assert _done(client, routine["id"], _key("2026-10-05")).status_code == 200
    assert client.delete(f"/api/calendar/events/{routine['id']}").status_code == 204

    # 作り直しても済みは引き継がない（⚠ 試験の DB は消した id を使い回しうる。済みが残っていると当たる）
    _routine(client, task_id=routine["task_id"])
    assert _done_dates(client, "2026-10-05", "2026-10-09") == []
