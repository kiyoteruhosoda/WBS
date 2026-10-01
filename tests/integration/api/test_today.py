"""「今日」の画面の要約（task #160 / ADR-0015）。

- 今日の区切りは利用者のタイムゾーン（既定の利用者は Asia/Tokyo）
- 実績は今日の分だけ数える（日をまたぐ打刻は 0:00 で切る。走っている打刻は今まで）
- まだ予定を取っていないタスクは、今日やるべきもの（期限切れ・今日か明日が期限・開始日を過ぎた・
  進行中）のうち、残が予定で埋まっていないもの。優先度の点の高い順
- 時刻は Z 付き

「今」は 2026-09-10 03:00 UTC（東京の木曜 12:00）に止める。
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

import pytest

from src.infrastructure.auth.auth_settings import SINGLE_USER_ID
from src.infrastructure.database.models import TimeEntryModel, UserModel
from src.presentation.api.dependencies import get_db

_NOON_IN_TOKYO = datetime(2026, 9, 10, 3, 0)  # naive な UTC（保存値と同じ形）


@pytest.fixture(autouse=True)
def frozen_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.application.user_clock.utcnow", lambda: _NOON_IN_TOKYO)
    monkeypatch.setattr("src.application.use_cases.today_use_cases.utcnow", lambda: _NOON_IN_TOKYO)


@pytest.fixture
def db(client) -> Iterator:
    session = next(client.app.dependency_overrides.get(get_db, get_db)())
    try:
        yield session
    finally:
        session.close()


def _task(client, title: str, **fields) -> dict:
    res = client.post("/api/tasks", json={"title": title, **fields})
    assert res.status_code == 201, res.text
    return res.json()


def _entry(
    db,
    started_at: datetime,
    ended_at: datetime | None,
    task_id: int | None = None,
    user_id: int = SINGLE_USER_ID,
) -> None:
    db.add(
        TimeEntryModel(user_id=user_id, started_at=started_at, ended_at=ended_at, task_id=task_id)
    )
    db.commit()


def _summary(client) -> dict:
    res = client.get("/api/today")
    assert res.status_code == 200, res.text
    return res.json()


def test_an_empty_day_in_the_users_time_zone(client) -> None:
    body = _summary(client)

    assert body["date"] == "2026-09-10"
    assert body["time_zone"] == "Asia/Tokyo"
    assert body["day_start"] == "2026-09-09T15:00:00Z"
    assert body["day_end"] == "2026-09-10T15:00:00Z"
    assert body["server_now"] == "2026-09-10T03:00:00Z"
    assert body["running"] is None
    assert body["entries"] == []
    assert body["total_seconds"] == 0
    assert body["actuals"] == []
    assert body["tasks_to_schedule"] == []


def test_actuals_count_only_today_and_the_running_entry_up_to_now(client, db) -> None:
    design = _task(client, "設計")
    review = _task(client, "レビュー")
    # 今日 10:00〜11:00（東京）
    _entry(db, datetime(2026, 9, 10, 1, 0), datetime(2026, 9, 10, 2, 0), design["id"])
    # 昨日 23:30〜今日 0:30 → 今日の分は 30 分
    _entry(db, datetime(2026, 9, 9, 14, 30), datetime(2026, 9, 9, 15, 30), review["id"])
    # 昨日だけの打刻は出ない
    _entry(db, datetime(2026, 9, 9, 1, 0), datetime(2026, 9, 9, 2, 0), design["id"])
    # 未割当で 11:30 から走っている → 今（12:00）までの 30 分
    _entry(db, datetime(2026, 9, 10, 2, 30), None)

    body = _summary(client)

    assert len(body["entries"]) == 3
    assert all(e["started_at"].endswith("Z") for e in body["entries"])
    assert body["running"] is not None
    assert body["running"]["task_id"] is None
    assert body["running"]["is_running"] is True
    assert body["total_seconds"] == 2 * 3600
    assert body["actuals"] == [
        {"task_id": design["id"], "task_title": "設計", "seconds": 3600},
        {"task_id": review["id"], "task_title": "レビュー", "seconds": 1800},
        {"task_id": None, "task_title": None, "seconds": 1800},
    ]


def test_someone_elses_entries_are_not_counted(client, db) -> None:
    other = UserModel(email="other-today@example.com", display_name="他人")
    db.add(other)
    db.commit()
    _entry(db, datetime(2026, 9, 10, 1, 0), datetime(2026, 9, 10, 2, 0), user_id=other.id)

    body = _summary(client)

    assert body["entries"] == []
    assert body["total_seconds"] == 0


def test_tasks_to_schedule_are_the_unscheduled_ones_due_now(client) -> None:
    overdue = _task(client, "期限切れ・見積なし", due_date="2026-09-09")
    due_today = _task(client, "今日が期限", due_date="2026-09-10", estimated_hours=3)
    due_tomorrow = _task(client, "明日が期限", due_date="2026-09-11", estimated_hours=1)
    doing = _task(client, "進行中", status="DOING", estimated_hours=1)
    booked = _task(client, "予定で埋まった", due_date="2026-09-10", estimated_hours=2)
    # 今日 14:00〜16:00（東京）に 2 時間を取る → 残 2h は埋まる
    res = client.post(
        "/api/calendar/events",
        json={
            "title": "予定で埋まった",
            "start": "2026-09-10T05:00:00Z",
            "duration_minutes": 120,
            "task_id": booked["id"],
        },
    )
    assert res.status_code == 201, res.text
    _task(client, "来週が期限", due_date="2026-09-17", estimated_hours=1)
    _task(client, "待機中", status="WAITING", due_date="2026-09-10", estimated_hours=1)
    _task(client, "完了", status="DONE", due_date="2026-09-10", estimated_hours=1)

    body = _summary(client)
    listed = body["tasks_to_schedule"]

    # 期限切れは点が高い。同じ点なら期限の近い順、期限なしは後ろ
    assert [t["id"] for t in listed] == [
        overdue["id"],
        due_today["id"],
        due_tomorrow["id"],
        doing["id"],
    ]
    assert listed[0]["unscheduled_hours"] is None
    assert listed[1]["unscheduled_hours"] == 3
    assert listed[1]["scheduled_hours"] == 0
    assert listed[1]["created_at"].endswith("Z")


def test_the_dashboard_keeps_only_the_kpi(client) -> None:
    assert client.get("/api/dashboard/kpi").status_code == 200
    assert client.get("/api/dashboard/today").status_code == 404
