"""実績の見える化の API（task #162 / ADR-0017）。

- 期間ごと: 予定（タスクに結んだ / 結んでいない）と打刻（タスク / 未割当）の差・タスク外の割合・確定実績
- 期間の区切りは利用者のタイムゾーン（Asia/Tokyo）の 0:00。日をまたぐ打刻は 0:00 で割る
- 他人の予定・打刻・実績は数えない
- タスクごと: 残を見直してほしい理由（見積超過・残 0・残が決まらない・確定の後に直していない）
- ガントの実績の帯・カテゴリ別の積み上げ・CSV の書き出し

日付は 2026 年 9 月（「今」より前。打刻は未来の時刻を受けないため）。
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal

import pytest

from src.domain.entities.calendar_event import CalendarEvent
from src.domain.value_objects.event_schedule import SingleEventSchedule
from src.domain.value_objects.time_zone import TimeZoneId
from src.infrastructure.database.models import (
    TaskModel,
    TimeEntryModel,
    UserModel,
    WorkLogModel,
)
from src.infrastructure.repositories.calendar_event_repository import (
    SqlAlchemyCalendarEventRepository,
)
from src.presentation.api.dependencies import get_db


@pytest.fixture
def db(client) -> Iterator:
    session = next(client.app.dependency_overrides.get(get_db, get_db)())
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def tokyo(client, db) -> None:
    db.query(UserModel).update({UserModel.timezone: "Asia/Tokyo"})
    db.commit()


@pytest.fixture
def stranger(db) -> dict:
    """他人と、その人のタスク・予定・打刻・実績（どれも同じ日付に置く）。"""
    other = UserModel(email="other-actuals@example.com", display_name="他人", timezone="Asia/Tokyo")
    db.add(other)
    db.flush()
    task = TaskModel(user_id=other.id, title="他人のタスク")
    db.add(task)
    db.flush()
    db.add(
        TimeEntryModel(
            user_id=other.id,
            started_at=datetime(2026, 9, 2, 1, 0),
            ended_at=datetime(2026, 9, 2, 5, 0),
            task_id=task.id,
        )
    )
    db.add(
        WorkLogModel(
            user_id=other.id, task_id=task.id, work_date=date(2026, 9, 2), hours=Decimal("4")
        )
    )
    SqlAlchemyCalendarEventRepository(db).save(
        CalendarEvent.create_single(
            user_id=other.id,
            title="他人の予定",
            time_zone=TimeZoneId("Asia/Tokyo"),
            schedule=SingleEventSchedule(datetime(2026, 9, 2, 1, 0), 240),
            created_at=datetime(2026, 9, 1, 0, 0),
            task_id=task.id,
        )
    )
    db.commit()
    return {"user_id": other.id, "task_id": task.id}


def _task(client, title: str, **fields) -> dict:
    res = client.post("/api/tasks", json={"title": title, **fields})
    assert res.status_code == 201, res.text
    return res.json()


def _entry(client, start: str, end: str, task_id: int | None = None) -> None:
    res = client.post(
        "/api/time-entries", json={"started_at": start, "ended_at": end, "task_id": task_id}
    )
    assert res.status_code == 201, res.text


def _event(client, start: str, minutes: int, task_id: int | None = None) -> None:
    body = {"title": "作業", "start": start, "duration_minutes": minutes, "task_id": task_id}
    res = client.post("/api/calendar/events", json=body)
    assert res.status_code == 201, res.text


def _work_log(client, task_id: int, work_date: str, hours: float) -> None:
    res = client.post(
        "/api/work-logs", json={"task_id": task_id, "work_date": work_date, "hours": hours}
    )
    assert res.status_code == 201, res.text


def _get(client, path: str, **params) -> dict:
    res = client.get(path, params=params)
    assert res.status_code == 200, res.text
    return res.json()


# ── 期間ごと ─────────────────────────────────────────────────────────────


def test_periods_compare_planned_and_tracked_time_per_closing_period(client, stranger) -> None:
    design = _task(client, "設計")
    # 予定: 9/3 10:00〜11:00（タスク）・9/4 10:00〜10:30（タスクに結ばない）。終日は数えない
    _event(client, "2026-09-03T01:00:00Z", 60, design["id"])
    _event(client, "2026-09-04T01:00:00Z", 30)
    _event(client, "2026-09-06T15:00:00Z", 1440, design["id"])  # 東京の 9/7 終日
    # 打刻: 9/2 10:00〜10:30 の未割当、9/15 23:00〜9/16 1:00 は 0:00 で 2 つの期間へ割る
    _entry(client, "2026-09-02T01:00:00Z", "2026-09-02T01:30:00Z")
    _entry(client, "2026-09-15T14:00:00Z", "2026-09-15T16:00:00Z", design["id"])
    # 確定実績（手で書いた）: 9/16 に 1.5 時間
    _work_log(client, design["id"], "2026-09-16", 1.5)

    body = _get(
        client, "/api/actuals/periods", unit="closing", **{"from": "2026-09-01", "to": "2026-09-30"}
    )

    assert body["unit"] == "closing"
    assert body["time_zone"] == "Asia/Tokyo"
    first, second = body["periods"]
    assert (first["first_day"], first["last_day"]) == ("2026-09-01", "2026-09-15")
    assert (second["first_day"], second["last_day"]) == ("2026-09-16", "2026-09-30")
    assert first["closed"] is False
    assert first["planned_task_seconds"] == 3600
    assert first["planned_off_task_seconds"] == 1800
    assert first["planned_seconds"] == 5400
    assert first["tracked_task_seconds"] == 3600
    assert first["tracked_off_task_seconds"] == 1800
    assert first["tracked_seconds"] == 5400
    assert first["difference_seconds"] == 0
    assert first["planned_off_task_ratio"] == pytest.approx(0.3333)
    assert first["tracked_off_task_ratio"] == pytest.approx(0.3333)
    assert first["confirmed_seconds"] == 0

    assert second["planned_seconds"] == 0
    assert second["tracked_task_seconds"] == 3600
    assert second["tracked_off_task_seconds"] == 0
    assert second["difference_seconds"] == 3600
    assert second["planned_off_task_ratio"] is None
    assert second["tracked_off_task_ratio"] == 0
    assert second["confirmed_seconds"] == 5400


def test_week_and_month_boundaries_follow_the_users_midnight(client) -> None:
    task = _task(client, "実装")
    # 東京の日曜 9/13 23:30〜月曜 9/14 0:30 → 週は 9/7〜13 に 30 分、9/14〜20 に 30 分
    _entry(client, "2026-09-13T14:30:00Z", "2026-09-13T15:30:00Z", task["id"])
    # 東京の 9/1 0:30（UTC では 8/31）→ 9 月に数える
    _entry(client, "2026-08-31T15:30:00Z", "2026-08-31T16:00:00Z", task["id"])

    weeks = _get(
        client, "/api/actuals/periods", unit="week", **{"from": "2026-09-07", "to": "2026-09-14"}
    )
    assert [(p["first_day"], p["tracked_seconds"]) for p in weeks["periods"]] == [
        ("2026-09-07", 1800),
        ("2026-09-14", 1800),
    ]
    assert all(p["closed"] is None for p in weeks["periods"])

    months = _get(
        client, "/api/actuals/periods", unit="month", **{"from": "2026-08-15", "to": "2026-09-01"}
    )
    assert [(p["first_day"], p["last_day"], p["tracked_seconds"]) for p in months["periods"]] == [
        ("2026-08-01", "2026-08-31", 0),
        ("2026-09-01", "2026-09-30", 3600 + 1800),
    ]


def test_someone_elses_time_is_not_counted(client, stranger) -> None:
    body = _get(
        client, "/api/actuals/periods", unit="closing", **{"from": "2026-09-01", "to": "2026-09-15"}
    )
    (period,) = body["periods"]
    assert period["planned_seconds"] == 0
    assert period["tracked_seconds"] == 0
    assert period["confirmed_seconds"] == 0

    breakdown = _get(client, "/api/actuals/breakdown", **{"from": "2026-09-01", "to": "2026-09-15"})
    assert breakdown["groups"] == []

    res = client.get("/api/actuals/export.csv", params={"from": "2026-09-01", "to": "2026-09-15"})
    assert res.status_code == 200
    assert len(list(csv.reader(io.StringIO(res.text.lstrip("﻿"))))) == 1  # 見出しだけ

    assert _get(client, "/api/actuals/gantt") == []
    assert stranger["task_id"] not in [
        r["task"]["id"] for r in _get(client, "/api/actuals/tasks")["rows"]
    ]


def test_closed_flag_follows_the_closing_periods(client) -> None:
    task = _task(client, "設計")
    _entry(client, "2026-09-02T01:00:00Z", "2026-09-02T02:00:00Z", task["id"])
    res = client.post("/api/closing-periods/2026-09-01/close")
    assert res.status_code == 200, res.text

    body = _get(
        client, "/api/actuals/periods", unit="closing", **{"from": "2026-09-01", "to": "2026-09-30"}
    )
    assert [(p["closed"], p["confirmed_seconds"]) for p in body["periods"]] == [
        (True, 3600),
        (False, 0),
    ]


def test_a_range_ending_before_it_starts_is_rejected(client) -> None:
    res = client.get("/api/actuals/periods", params={"from": "2026-09-10", "to": "2026-09-01"})
    assert res.status_code == 422
    res = client.get("/api/actuals/export.csv", params={"from": "2026-09-10", "to": "2026-09-01"})
    assert res.status_code == 422


def test_periods_default_to_the_recent_six(client) -> None:
    body = _get(client, "/api/actuals/periods", unit="month")
    assert len(body["periods"]) == 6


# ── タスクごと・残を見直す ────────────────────────────────────────────────


def _rows(client, **params) -> dict[str, dict]:
    body = _get(client, "/api/actuals/tasks", **params)
    return {r["task"]["title"]: r for r in body["rows"]}


def test_task_rows_carry_estimate_actual_remaining_and_review_reasons(client) -> None:
    over = _task(client, "超過", estimated_hours=2)
    _work_log(client, over["id"], "2026-09-03", 3)
    unknown = _task(client, "見積なし")
    _work_log(client, unknown["id"], "2026-09-04", 1)
    zero = _task(client, "残ゼロ", estimated_hours=5, remaining_hours=0)
    _task(client, "順調", estimated_hours=10)
    done = _task(client, "完了", estimated_hours=1, status="DONE")
    _work_log(client, done["id"], "2026-09-05", 2)

    rows = _rows(client)

    assert rows["超過"]["review_reasons"] == ["over_estimate"]
    assert rows["超過"]["task"]["estimated_hours"] == 2
    assert rows["超過"]["task"]["actual_hours"] == 3
    assert rows["超過"]["task"]["remaining_hours"] == 0
    assert rows["超過"]["actual_first_date"] == "2026-09-03"
    assert rows["超過"]["actual_last_date"] == "2026-09-03"
    assert rows["見積なし"]["review_reasons"] == ["unknown_remaining"]
    assert rows["残ゼロ"]["review_reasons"] == ["no_remaining"]
    assert rows["順調"]["review_reasons"] == []
    assert rows["順調"]["actual_first_date"] is None
    assert rows["完了"]["review_reasons"] == []
    assert zero["id"] in [
        r["task"]["id"] for r in _get(client, "/api/actuals/tasks", review_only=True)["rows"]
    ]
    assert set(_rows(client, review_only=True)) == {"超過", "見積なし", "残ゼロ"}

    # その場で残を入れれば外れる
    res = client.patch(f"/api/tasks/{over['id']}", json={"remaining_hours": 1.5})
    assert res.status_code == 200, res.text
    assert "超過" not in _rows(client, review_only=True)


def test_a_remaining_left_untouched_after_closing_is_asked_again(client) -> None:
    task = _task(client, "設計", estimated_hours=8, remaining_hours=6)
    untouched = _task(client, "手付かず", estimated_hours=8, remaining_hours=6)
    _entry(client, "2026-09-02T01:00:00Z", "2026-09-02T03:00:00Z", task["id"])
    res = client.post("/api/closing-periods/2026-09-01/close")
    assert res.status_code == 200, res.text

    body = _get(client, "/api/actuals/tasks")
    assert body["latest_closed_period"]["first_day"] == "2026-09-01"
    assert body["latest_closed_period"]["closed_at"].endswith("Z")
    rows = {r["task"]["title"]: r for r in body["rows"]}
    assert rows["設計"]["review_reasons"] == ["stale_remaining"]
    assert rows["設計"]["latest_closed_hours"] == 2
    # 締めで実績の入らなかったタスクは聞かない
    assert rows["手付かず"]["review_reasons"] == []
    assert untouched["id"] == rows["手付かず"]["task"]["id"]

    res = client.patch(f"/api/tasks/{task['id']}", json={"remaining_hours": 4})
    assert res.status_code == 200, res.text
    assert _rows(client)["設計"]["review_reasons"] == []


def test_parent_tasks_are_not_asked_for_a_remaining(client) -> None:
    parent = _task(client, "親")
    child = _task(client, "子", estimated_hours=1, parent_task_id=parent["id"])
    _work_log(client, parent["id"], "2026-09-03", 2)
    _work_log(client, child["id"], "2026-09-03", 2)

    rows = _rows(client)
    assert rows["親"]["review_reasons"] == []
    assert rows["子"]["review_reasons"] == ["over_estimate"]


# ── ガント・積み上げ・書き出し ────────────────────────────────────────────


def test_gantt_spans_cover_all_logs_and_days_only_the_asked_range(client) -> None:
    task = _task(client, "設計")
    _work_log(client, task["id"], "2026-09-03", 1)
    _work_log(client, task["id"], "2026-09-10", 2)
    _work_log(client, task["id"], "2026-09-10", 0.5)

    (span,) = _get(client, "/api/actuals/gantt", **{"from": "2026-09-05", "to": "2026-09-30"})

    assert span["task_id"] == task["id"]
    assert (span["first_date"], span["last_date"]) == ("2026-09-03", "2026-09-10")
    assert span["days"] == [{"date": "2026-09-10", "seconds": 9000}]


def test_breakdown_stacks_by_category_and_keeps_off_task_time_apart(client) -> None:
    work = client.post("/api/categories", json={"name": "仕事", "color": "#0017C1"}).json()
    in_work = _task(client, "設計", category_id=work["id"])
    loose = _task(client, "雑務")
    _entry(client, "2026-09-02T01:00:00Z", "2026-09-02T02:00:00Z", in_work["id"])
    _entry(client, "2026-09-02T02:00:00Z", "2026-09-02T02:30:00Z", loose["id"])
    _entry(client, "2026-09-16T01:00:00Z", "2026-09-16T01:15:00Z")

    body = _get(
        client,
        "/api/actuals/breakdown",
        unit="closing",
        group_by="category",
        source="tracked",
        **{"from": "2026-09-01", "to": "2026-09-30"},
    )

    assert body["groups"] == [
        {"key": f"category:{work['id']}", "name": "仕事", "color": "#0017C1"},
        {"key": "none", "name": None, "color": None},
        {"key": "unassigned", "name": None, "color": None},
    ]
    assert [p["seconds_by_group"] for p in body["periods"]] == [
        {f"category:{work['id']}": 3600, "none": 1800},
        {"unassigned": 900},
    ]


def test_breakdown_by_milestone_uses_confirmed_work_logs(client) -> None:
    release = client.post("/api/milestones", json={"name": "リリース"}).json()
    task = _task(client, "設計", milestone_id=release["id"])
    _work_log(client, task["id"], "2026-09-03", 2)

    body = _get(
        client,
        "/api/actuals/breakdown",
        group_by="milestone",
        **{"from": "2026-09-01", "to": "2026-09-15"},
    )

    assert body["source"] == "confirmed"
    assert body["groups"] == [
        {"key": f"milestone:{release['id']}", "name": "リリース", "color": None}
    ]
    assert body["periods"][0]["seconds_by_group"] == {f"milestone:{release['id']}": 7200}


def test_export_writes_period_day_task_and_hours(client) -> None:
    work = client.post("/api/categories", json={"name": "仕事"}).json()
    task = _task(client, "設計, 第 1 版", category_id=work["id"])
    _work_log(client, task["id"], "2026-09-15", 1.25)
    _work_log(client, task["id"], "2026-09-16", 0.5)
    _entry(client, "2026-09-16T01:00:00Z", "2026-09-16T01:20:00Z")

    res = client.get("/api/actuals/export.csv", params={"from": "2026-09-01", "to": "2026-09-30"})

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "attachment" in res.headers["content-disposition"]
    assert res.text.startswith("﻿")
    rows = list(csv.reader(io.StringIO(res.text.lstrip("﻿"))))
    assert rows[0] == [
        "period_start",
        "period_end",
        "date",
        "task_id",
        "task",
        "category",
        "milestone",
        "hours",
        "seconds",
    ]
    assert rows[1:] == [
        [
            "2026-09-01",
            "2026-09-15",
            "2026-09-15",
            str(task["id"]),
            "設計, 第 1 版",
            "仕事",
            "",
            "1.25",
            "4500",
        ],
        [
            "2026-09-16",
            "2026-09-30",
            "2026-09-16",
            str(task["id"]),
            "設計, 第 1 版",
            "仕事",
            "",
            "0.50",
            "1800",
        ],
    ]

    tracked = client.get(
        "/api/actuals/export.csv",
        params={"from": "2026-09-16", "to": "2026-09-16", "source": "tracked"},
    )
    tracked_rows = list(csv.reader(io.StringIO(tracked.text.lstrip("﻿"))))
    assert tracked_rows[1:] == [
        ["2026-09-16", "2026-09-30", "2026-09-16", "", "", "", "", "0.33", "1200"],
    ]
