"""締めの API（task #161）。表（closing_periods・work_logs の列）を通しで見る。

期間は過去（2026-09-01〜15、利用者は Asia/Tokyo）を使う。打刻は未来の時刻を受けないので、
試験の日付は「今」より前に置く。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.infrastructure.database.models import ClosingPeriodModel, UserModel, WorkLogModel
from src.presentation.api.dependencies import get_current_user, get_db

OTHER_EMAIL = "other-closing@example.com"
PERIOD = "2026-09-01"


def _as_user(user_id: int, email: str) -> Callable[[], AuthenticatedUserDTO]:
    def current() -> AuthenticatedUserDTO:
        return AuthenticatedUserDTO(
            user_id=user_id, email=email, display_name=email, timezone="Asia/Tokyo", language="ja"
        )

    return current


@pytest.fixture
def db(client) -> Iterator:
    session = next(client.app.dependency_overrides.get(get_db, get_db)())
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def two_users(client, db):
    user = UserModel(email=OTHER_EMAIL, display_name="他人", timezone="Asia/Tokyo")
    db.add(user)
    db.flush()
    other_id = user.id
    db.commit()

    class Switch:
        def me(self) -> None:
            client.app.dependency_overrides.pop(get_current_user, None)

        def other(self) -> None:
            client.app.dependency_overrides[get_current_user] = _as_user(other_id, OTHER_EMAIL)

    switch = Switch()
    yield switch
    switch.me()


@pytest.fixture(autouse=True)
def tokyo(client, db) -> None:
    db.query(UserModel).update({UserModel.timezone: "Asia/Tokyo"})
    db.commit()


def _task(client, title: str) -> int:
    res = client.post("/api/tasks", json={"title": title})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _entry(client, start: str, end: str, task_id: int | None = None) -> dict:
    res = client.post(
        "/api/time-entries",
        json={"started_at": start, "ended_at": end, "task_id": task_id},
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_close_turns_entries_into_work_logs_and_reopen_removes_them(client, db) -> None:
    design = _task(client, "設計")
    review = _task(client, "レビュー")
    _entry(client, "2026-09-02T09:00:00+09:00", "2026-09-02T12:00:00+09:00", design)
    # 日をまたぐ打刻は 0:00 で割る
    _entry(client, "2026-09-02T23:00:00+09:00", "2026-09-03T01:30:00+09:00", design)
    _entry(client, "2026-09-03T10:00:00+09:00", "2026-09-03T10:20:00+09:00", review)
    manual = client.post(
        "/api/work-logs", json={"task_id": design, "work_date": "2026-09-02", "hours": "1.5"}
    ).json()

    res = client.post(f"/api/closing-periods/{PERIOD}/close")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["period"]["status"] == "closed"
    assert body["period"]["starts_at"] == "2026-08-31T15:00:00Z"
    assert body["period"]["ends_at"] == "2026-09-15T15:00:00Z"
    logs = {(w["task_id"], w["work_date"]): w for w in body["work_logs"]}
    assert {k: v["duration_seconds"] for k, v in logs.items()} == {
        (design, "2026-09-02"): 4 * 3600,
        (design, "2026-09-03"): 90 * 60,
        (review, "2026-09-03"): 20 * 60,
    }
    assert logs[(review, "2026-09-03")]["hours"] == pytest.approx(0.33)
    assert {w["source"] for w in body["work_logs"]} == {"closing"}

    # 締めで作った実績は直接は直させない。手の実績は残る
    closing_log = logs[(design, "2026-09-02")]["id"]
    assert client.put(f"/api/work-logs/{closing_log}", json={"hours": "1"}).status_code == 409
    assert client.delete(f"/api/work-logs/{closing_log}").status_code == 409
    task_logs = client.get("/api/work-logs", params={"task_id": design}).json()
    assert {w["source"] for w in task_logs} == {"closing", "manual"}

    board = client.get(f"/api/closing-periods/{PERIOD}").json()
    assert board["period"]["status"] == "closed"
    assert len(board["entries"]) == 3

    res = client.post(f"/api/closing-periods/{PERIOD}/reopen")
    assert res.status_code == 200, res.text
    assert res.json()["removed_work_logs"] == 3
    remaining = db.query(WorkLogModel).filter(WorkLogModel.deleted_at.is_(None)).all()
    assert [w.id for w in remaining] == [manual["id"]]
    assert remaining[0].source == "manual"
    assert db.query(ClosingPeriodModel).count() == 0
    assert client.post(f"/api/closing-periods/{PERIOD}/reopen").status_code == 409


def test_closed_period_protects_its_entries(client) -> None:
    task_id = _task(client, "実装")
    inside = _entry(client, "2026-09-05T09:00:00+09:00", "2026-09-05T10:00:00+09:00", task_id)
    after = _entry(client, "2026-09-17T09:00:00+09:00", "2026-09-17T10:00:00+09:00", task_id)
    assert client.post(f"/api/closing-periods/{PERIOD}/close").status_code == 200
    assert client.post(f"/api/closing-periods/{PERIOD}/close").status_code == 409

    url = f"/api/time-entries/{inside['id']}"
    assert client.patch(url, json={"memo": "x"}).status_code == 409
    assert client.delete(url).status_code == 409
    assert client.post(f"{url}/split", json={"at": "2026-09-05T09:30:00+09:00"}).status_code == 409
    assert (
        client.post(
            "/api/time-entries/assign", json={"entry_ids": [inside["id"]], "task_id": None}
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/time-entries",
            json={
                "started_at": "2026-09-10T09:00:00+09:00",
                "ended_at": "2026-09-10T10:00:00+09:00",
            },
        ).status_code
        == 409
    )
    # 開いている期間の打刻を、確定した期間へ動かすことも断る
    moved = client.patch(
        f"/api/time-entries/{after['id']}", json={"started_at": "2026-09-15T22:00:00+09:00"}
    )
    assert moved.status_code == 409
    # 開いている期間はそのまま触れる
    assert client.patch(f"/api/time-entries/{after['id']}", json={"memo": "ok"}).status_code == 200


def test_close_refuses_unassigned_entries_then_assign_in_bulk(client) -> None:
    task_id = _task(client, "調査")
    a = _entry(client, "2026-09-04T09:00:00+09:00", "2026-09-04T10:00:00+09:00")
    b = _entry(client, "2026-09-04T11:00:00+09:00", "2026-09-04T12:00:00+09:00")
    res = client.post(f"/api/closing-periods/{PERIOD}/close")
    assert res.status_code == 409

    board = client.get(f"/api/closing-periods/{PERIOD}").json()
    assert board["findings"]["unassigned_entry_ids"] == [a["id"], b["id"]]

    assigned = client.post(
        "/api/time-entries/assign", json={"entry_ids": [a["id"], b["id"]], "task_id": task_id}
    )
    assert assigned.status_code == 200, assigned.text
    assert [e["task_title"] for e in assigned.json()] == ["調査", "調査"]
    assert client.post(f"/api/closing-periods/{PERIOD}/close").status_code == 200


def test_split_and_merge(client) -> None:
    task_id = _task(client, "設計")
    entry = _entry(client, "2026-09-08T09:00:00+09:00", "2026-09-08T12:00:00+09:00", task_id)
    res = client.post(
        f"/api/time-entries/{entry['id']}/split", json={"at": "2026-09-08T10:00:00+09:00"}
    )
    assert res.status_code == 200, res.text
    first, second = res.json()["first"], res.json()["second"]
    assert first["ended_at"] == "2026-09-08T01:00:00Z"
    assert second["started_at"] == "2026-09-08T01:00:00Z"
    assert second["source"] == "split"
    assert second["task_id"] == task_id

    bad = client.post(
        f"/api/time-entries/{entry['id']}/split", json={"at": "2026-09-08T09:00:00+09:00"}
    )
    assert bad.status_code == 422

    merged = client.post("/api/time-entries/merge", json={"entry_ids": [second["id"], first["id"]]})
    assert merged.status_code == 200, merged.text
    assert merged.json()["id"] == first["id"]
    assert merged.json()["duration_seconds"] == 3 * 3600
    assert client.get(f"/api/time-entries/{second['id']}").status_code == 404


def test_others_entries_are_out_of_reach(client, two_users) -> None:
    mine = _entry(
        client, "2026-09-08T09:00:00+09:00", "2026-09-08T10:00:00+09:00", _task(client, "A")
    )
    two_users.other()
    theirs = _entry(client, "2026-09-08T09:00:00+09:00", "2026-09-08T11:00:00+09:00")
    assert (
        client.post(
            f"/api/time-entries/{mine['id']}/split", json={"at": "2026-09-08T09:30:00+09:00"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/time-entries/merge", json={"entry_ids": [mine["id"], theirs["id"]]}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/api/time-entries/assign", json={"entry_ids": [mine["id"]], "task_id": None}
        ).status_code
        == 404
    )
    # 他人の画面には自分の打刻は出ない。他人の未割当があっても、自分の確定は止まらない
    board = client.get(f"/api/closing-periods/{PERIOD}").json()
    assert [e["id"] for e in board["entries"]] == [theirs["id"]]

    two_users.me()
    res = client.post(f"/api/closing-periods/{PERIOD}/close")
    assert res.status_code == 200, res.text
    assert [w["duration_seconds"] for w in res.json()["work_logs"]] == [3600]
    # 自分の確定は他人の打刻を守らない（他人の期間は開いている）
    two_users.other()
    assert client.patch(f"/api/time-entries/{theirs['id']}", json={"memo": "x"}).status_code == 200
    assert client.post(f"/api/closing-periods/{PERIOD}/reopen").status_code == 409


def test_an_occurrence_becomes_a_time_entry_and_missed_ones_are_flagged(client) -> None:
    task_id = _task(client, "定例")
    done = client.post(
        "/api/calendar/events",
        json={
            "title": "定例",
            "start": "2026-09-09T01:00:00Z",
            "duration_minutes": 60,
            "task_id": task_id,
        },
    ).json()
    client.post(
        "/api/calendar/events",
        json={"title": "1on1", "start": "2026-09-10T05:00:00Z", "duration_minutes": 30},
    )

    board = client.get(f"/api/closing-periods/{PERIOD}").json()
    assert sorted(o["title"] for o in board["findings"]["missed_occurrences"]) == ["1on1", "定例"]
    assert len(board["occurrences"]) == 2

    res = client.post(
        "/api/time-entries/from-occurrence",
        json={"event_id": done["id"], "start": "2026-09-09T10:00:00+09:00"},
    )
    assert res.status_code == 201, res.text
    entry = res.json()
    assert entry["source"] == "schedule"
    assert entry["task_id"] == task_id
    assert (entry["started_at"], entry["ended_at"]) == (
        "2026-09-09T01:00:00Z",
        "2026-09-09T02:00:00Z",
    )

    board = client.get(f"/api/closing-periods/{PERIOD}").json()
    assert [o["title"] for o in board["findings"]["missed_occurrences"]] == ["1on1"]
    assert board["daily_totals"] == [
        {
            "work_date": "2026-09-09",
            "task_id": task_id,
            "task_title": "定例",
            "seconds": 3600,
            "project_id": None,
        }
    ]

    wrong = client.post(
        "/api/time-entries/from-occurrence",
        json={"event_id": done["id"], "start": "2026-09-09T11:00:00+09:00"},
    )
    assert wrong.status_code == 404


def test_daily_totals_carry_the_task_project(client) -> None:
    """合計の行にタスクのいまのプロジェクト（task #189）。未割当・未分類は null。"""
    parent = client.post("/api/projects", json={"name": "仕事", "parent_project_id": None}).json()
    child = client.post(
        "/api/projects", json={"name": "案件 A", "parent_project_id": parent["id"]}
    ).json()
    in_child = client.post("/api/tasks", json={"title": "設計", "project_id": child["id"]})
    assert in_child.status_code == 201, in_child.text
    loose = _task(client, "雑務")
    _entry(client, "2026-09-02T09:00:00+09:00", "2026-09-02T10:00:00+09:00", in_child.json()["id"])
    _entry(client, "2026-09-02T10:00:00+09:00", "2026-09-02T10:30:00+09:00", loose)
    _entry(client, "2026-09-02T11:00:00+09:00", "2026-09-02T11:15:00+09:00")

    board = client.get(f"/api/closing-periods/{PERIOD}").json()
    rows = {(t["task_title"], t["project_id"], t["seconds"]) for t in board["daily_totals"]}
    assert rows == {("設計", child["id"], 3600), ("雑務", None, 1800), (None, None, 900)}


def test_pending_periods(client) -> None:
    assert client.get("/api/closing-periods/pending").json()["has_pending"] is False
    _entry(client, "2026-09-02T09:00:00+09:00", "2026-09-02T10:00:00+09:00", _task(client, "A"))
    pending = client.get("/api/closing-periods/pending").json()
    assert pending["has_pending"] is True
    assert pending["pending"][0] == {"first_day": "2026-09-01", "last_day": "2026-09-15"}
    assert client.post(f"/api/closing-periods/{PERIOD}/close").status_code == 200
    after = client.get("/api/closing-periods/pending").json()
    assert {"first_day": "2026-09-01", "last_day": "2026-09-15"} not in after["pending"]


def test_a_period_is_pointed_at_by_its_first_day(client) -> None:
    assert client.get("/api/closing-periods/2026-09-02").status_code == 422
    assert client.post("/api/closing-periods/2026-09-15/close").status_code == 422
