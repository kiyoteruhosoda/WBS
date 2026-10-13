"""打刻の API（task #154）。表（部分一意索引）・持ち主・日をまたぐ打刻を通しで見る。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.infrastructure.auth.auth_settings import SINGLE_USER_ID
from src.infrastructure.database.models import TimeEntryModel, UserModel
from src.presentation.api.dependencies import get_app_or_web_user, get_current_user, get_db
from src.shared.clock import utcnow

OTHER_EMAIL = "other-timer@example.com"


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
def other_user_id(db) -> int:
    user = UserModel(email=OTHER_EMAIL, display_name="他人")
    db.add(user)
    db.flush()
    user_id = user.id
    db.commit()
    return user_id


@pytest.fixture
def two_users(client, other_user_id):
    class Switch:
        # Start / Stop / 現在の口はアプリからも叩ける別の依存関数（ADR-0018）なので両方を差し替える
        def me(self) -> None:
            client.app.dependency_overrides.pop(get_current_user, None)
            client.app.dependency_overrides.pop(get_app_or_web_user, None)

        def other(self) -> None:
            as_other = _as_user(other_user_id, OTHER_EMAIL)
            client.app.dependency_overrides[get_current_user] = as_other
            client.app.dependency_overrides[get_app_or_web_user] = as_other

    switch = Switch()
    yield switch
    switch.me()


def _task(client, title: str) -> int:
    res = client.post("/api/tasks", json={"title": title})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _start(client, **body):
    res = client.post("/api/time-entries/start", json=body or None)
    assert res.status_code == 201, res.text
    return res.json()


def test_nothing_is_running_at_first(client) -> None:
    res = client.get("/api/time-entries/current")
    assert res.status_code == 200
    body = res.json()
    assert body["entry"] is None
    assert body["server_now"].endswith("Z")


def test_start_without_a_body_then_stop(client) -> None:
    res = client.post("/api/time-entries/start")
    assert res.status_code == 201, res.text
    started = res.json()["started"]
    assert started["is_running"] is True
    assert started["task_id"] is None
    assert started["source"] == "timer"
    assert started["started_at"].endswith("Z")
    assert res.json()["stopped"] is None

    current = client.get("/api/time-entries/current").json()["entry"]
    assert current["id"] == started["id"]

    stopped = client.post("/api/time-entries/stop").json()["stopped"]
    assert stopped["id"] == started["id"]
    assert stopped["is_running"] is False
    assert stopped["ended_at"].endswith("Z")
    assert client.get("/api/time-entries/current").json()["entry"] is None


def test_start_while_running_switches(client) -> None:
    first_task = _task(client, "設計")
    second_task = _task(client, "実装")
    first = _start(client, task_id=first_task)["started"]

    switched = _start(client, task_id=second_task)
    assert switched["stopped"]["id"] == first["id"]
    assert switched["stopped"]["ended_at"] == switched["started"]["started_at"]
    assert switched["started"]["task_id"] == second_task
    assert switched["started"]["task_title"] == "実装"
    assert client.get("/api/time-entries/current").json()["entry"]["id"] == switched["started"]["id"]


def test_start_without_task_takes_the_previous_task(client) -> None:
    task_id = _task(client, "レビュー")
    _start(client, task_id=task_id)
    client.post("/api/time-entries/stop")
    again = _start(client)["started"]
    assert again["task_id"] == task_id
    assert again["task_title"] == "レビュー"


def test_explicit_null_task_starts_unassigned(client) -> None:
    _start(client, task_id=_task(client, "A"))
    assert _start(client, task_id=None)["started"]["task_id"] is None


def test_double_start_leaves_one_running_entry(client, db) -> None:
    _start(client)
    _start(client)
    rows = db.query(TimeEntryModel).filter(TimeEntryModel.user_id == SINGLE_USER_ID).all()
    assert len(rows) == 2
    assert sum(1 for r in rows if r.ended_at is None) == 1


def test_stop_is_idempotent(client) -> None:
    _start(client)
    first = client.post("/api/time-entries/stop")
    second = client.post("/api/time-entries/stop")
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["stopped"] is not None
    assert second.json()["stopped"] is None


def test_the_table_refuses_a_second_running_row(client, db) -> None:
    db.add(TimeEntryModel(user_id=SINGLE_USER_ID, started_at=datetime(2026, 9, 1, 0, 0)))
    db.commit()
    db.add(TimeEntryModel(user_id=SINGLE_USER_ID, started_at=datetime(2026, 9, 1, 1, 0)))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    # 止まった打刻は何本でも持てる
    db.add(TimeEntryModel(user_id=SINGLE_USER_ID, started_at=datetime(2026, 9, 1, 2, 0),
                          ended_at=datetime(2026, 9, 1, 3, 0)))
    db.add(TimeEntryModel(user_id=SINGLE_USER_ID, started_at=datetime(2026, 9, 1, 4, 0),
                          ended_at=datetime(2026, 9, 1, 5, 0)))
    db.commit()


def test_cannot_start_on_someone_elses_task(client, two_users) -> None:
    two_users.other()
    theirs = _task(client, "他人のタスク")
    two_users.me()
    res = client.post("/api/time-entries/start", json={"task_id": theirs})
    assert res.status_code == 404
    assert client.get("/api/time-entries/current").json()["entry"] is None


def test_someone_elses_entry_is_out_of_reach(client, two_users) -> None:
    two_users.other()
    theirs = _start(client)["started"]
    two_users.me()

    assert client.get("/api/time-entries/current").json()["entry"] is None
    assert client.post("/api/time-entries/stop").json()["stopped"] is None
    assert client.get(f"/api/time-entries/{theirs['id']}").status_code == 404
    assert client.patch(f"/api/time-entries/{theirs['id']}", json={"memo": "x"}).status_code == 404
    assert client.delete(f"/api/time-entries/{theirs['id']}").status_code == 404
    listed = client.get(
        "/api/time-entries", params={"start": "2000-01-01T00:00:00Z", "end": "2100-01-01T00:00:00Z"}
    ).json()
    assert listed == []

    # 自分が Start しても他人の打刻は止まらない（1 人 1 本は利用者ごと）
    _start(client)
    two_users.other()
    still = client.get("/api/time-entries/current").json()["entry"]
    assert still["id"] == theirs["id"]
    assert still["is_running"] is True


def test_an_entry_across_midnight_is_listed_on_both_days(client) -> None:
    entry = _start(client)["started"]
    client.post("/api/time-entries/stop")
    # JST 9/10 23:00〜9/11 1:00 に直す
    res = client.patch(
        f"/api/time-entries/{entry['id']}",
        json={"started_at": "2026-09-10T23:00:00+09:00", "ended_at": "2026-09-11T01:00:00+09:00"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["started_at"] == "2026-09-10T14:00:00Z"
    assert res.json()["duration_seconds"] == 2 * 3600

    def day(d: str) -> list[int]:
        nxt = f"2026-09-{int(d) + 1:02d}"
        res = client.get(
            "/api/time-entries",
            params={"start": f"2026-09-{d}T00:00:00+09:00", "end": f"{nxt}T00:00:00+09:00"},
        )
        assert res.status_code == 200, res.text
        return [e["id"] for e in res.json()]

    assert day("10") == [entry["id"]]
    assert day("11") == [entry["id"]]
    assert day("12") == []


def test_a_long_entry_is_marked(client) -> None:
    entry = _start(client)["started"]
    client.post("/api/time-entries/stop")
    res = client.patch(
        f"/api/time-entries/{entry['id']}",
        json={"started_at": "2026-09-01T00:00:00Z", "ended_at": "2026-09-01T12:30:00Z"},
    )
    assert res.json()["is_long_running"] is True


def test_list_requires_an_offset(client) -> None:
    res = client.get(
        "/api/time-entries", params={"start": "2026-09-01T00:00:00", "end": "2026-09-02T00:00:00"}
    )
    assert res.status_code == 422


def test_update_rejects_reopening_and_bad_ranges(client) -> None:
    entry = _start(client)["started"]
    client.post("/api/time-entries/stop")
    url = f"/api/time-entries/{entry['id']}"
    assert client.patch(url, json={"ended_at": None}).status_code == 422
    assert client.patch(
        url, json={"started_at": "2026-09-01T02:00:00Z", "ended_at": "2026-09-01T01:00:00Z"}
    ).status_code == 422
    assert client.patch(url, json={"ended_at": "2100-01-01T00:00:00Z"}).status_code == 422


def test_task_and_memo_can_be_changed_on_the_running_entry(client) -> None:
    task_id = _task(client, "打ち合わせ")
    entry = _start(client, task_id=None)["started"]
    res = client.patch(f"/api/time-entries/{entry['id']}", json={"task_id": task_id, "memo": "定例"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["is_running"] is True
    assert body["task_title"] == "打ち合わせ"
    assert body["memo"] == "定例"


def test_delete(client) -> None:
    entry = _start(client)["started"]
    assert client.delete(f"/api/time-entries/{entry['id']}").status_code == 204
    assert client.get(f"/api/time-entries/{entry['id']}").status_code == 404
    assert client.get("/api/time-entries/current").json()["entry"] is None


def test_start_and_stop_at_the_pressed_time(client) -> None:
    """アプリが電波の無いときに溜めた押下を、押した時刻で送る（ADR-0018）。"""
    pressed = (utcnow() - timedelta(hours=3)).replace(microsecond=0)
    started = _start(client, at=f"{(pressed + timedelta(hours=9)).isoformat()}+09:00")["started"]
    assert started["started_at"] == f"{pressed.isoformat()}Z"
    stop_at = pressed + timedelta(minutes=90)
    res = client.post("/api/time-entries/stop", json={"at": f"{stop_at.isoformat()}Z"})
    assert res.status_code == 200, res.text
    assert res.json()["stopped"]["ended_at"] == f"{stop_at.isoformat()}Z"
    assert res.json()["stopped"]["duration_seconds"] == 90 * 60


def test_a_pressed_time_needs_an_offset_and_must_not_be_in_the_future(client) -> None:
    naive = (utcnow() - timedelta(hours=1)).replace(microsecond=0).isoformat()
    assert client.post("/api/time-entries/start", json={"at": naive}).status_code == 422
    assert client.post("/api/time-entries/start", json={"at": "2100-01-01T00:00:00Z"}).status_code == 422
    # 範囲の外の時刻は、止める打刻が無くても断る（送り手の時計の狂いに気づけるように）
    assert client.post("/api/time-entries/stop", json={"at": "2100-01-01T00:00:00Z"}).status_code == 422


# ── PC の自動記録（WinTrack、task #379 / ADR-0042） ─────────────────────────


def _auto(client, *items):
    res = client.post("/api/time-entries/auto", json={"entries": list(items)})
    assert res.status_code == 200, res.text
    return res.json()["results"]


def _span(ref: str, start: datetime, minutes: int, task_id: int) -> dict:
    # 送り手は +09:00 で送る。応答は Z 付きの UTC
    jst = timedelta(hours=9)
    return {
        "client_ref": ref,
        "started_at": f"{(start + jst).isoformat()}+09:00",
        "ended_at": f"{(start + timedelta(minutes=minutes) + jst).isoformat()}+09:00",
        "task_id": task_id,
    }


def test_auto_entries_are_created_once_and_marked_auto(client, db) -> None:
    task = _task(client, "見積書を作る")
    start = (utcnow() - timedelta(hours=3)).replace(microsecond=0)
    first = _auto(client, _span("3f2b-a", start, 40, task))
    assert [(r["client_ref"], r["status"], r["error"]) for r in first] == [("3f2b-a", "created", None)]
    entry = first[0]["entry"]
    assert entry["source"] == "auto"
    assert entry["started_at"] == f"{start.isoformat()}Z"
    assert entry["duration_seconds"] == 40 * 60
    assert entry["task_title"] == "見積書を作る"

    # 送り直しは同じ打刻を返し、中身が違っても上書きしない
    again = _auto(client, _span("3f2b-a", start, 90, task))
    assert again[0]["status"] == "duplicate"
    assert again[0]["entry"]["id"] == entry["id"]
    assert again[0]["entry"]["duration_seconds"] == 40 * 60
    assert db.query(TimeEntryModel).filter(TimeEntryModel.client_ref == "3f2b-a").count() == 1


def test_auto_results_are_per_entry(client) -> None:
    task = _task(client, "設計")
    _start(client, task_id=task)  # 走っている打刻（終わりが無いものとして重なる）
    start = (utcnow() - timedelta(hours=5)).replace(microsecond=0)
    results = _auto(
        client,
        _span("ok", start, 30, task),
        _span("overlap", start + timedelta(minutes=10), 30, task),
        _span("zero-length", start + timedelta(hours=3), 0, task),
        _span("reversed", start + timedelta(hours=1), -10, task),
        _span("old", utcnow() - timedelta(days=8), 30, task),
        _span("future", utcnow() + timedelta(hours=1), 30, task),
        _span("no-task", start + timedelta(hours=2), 30, 999_999),
    )
    assert [(r["client_ref"], r["status"]) for r in results] == [
        ("ok", "created"),
        ("overlap", "overlap"),
        ("zero-length", "invalid"),
        ("reversed", "invalid"),
        ("old", "invalid"),
        ("future", "invalid"),
        ("no-task", "invalid"),
    ]
    assert all(r["entry"] is None and r["error"] for r in results[1:])


def test_an_auto_entry_after_the_running_timer_started_overlaps_it(client) -> None:
    task = _task(client, "設計")
    _start(client, task_id=task, at=f"{(utcnow() - timedelta(hours=1)).replace(microsecond=0).isoformat()}Z")
    start = (utcnow() - timedelta(minutes=30)).replace(microsecond=0)
    assert _auto(client, _span("x", start, 10, task))[0]["status"] == "overlap"


def test_auto_entries_need_a_task_and_at_most_two_hundred(client) -> None:
    task = _task(client, "設計")
    start = (utcnow() - timedelta(days=6)).replace(microsecond=0)
    no_task = _span("a", start, 10, task)
    del no_task["task_id"]
    assert client.post("/api/time-entries/auto", json={"entries": [no_task]}).status_code == 422
    assert client.post("/api/time-entries/auto", json={"entries": []}).status_code == 422
    many = [_span(str(i), start + timedelta(minutes=i), 1, task) for i in range(201)]
    assert client.post("/api/time-entries/auto", json={"entries": many}).status_code == 422
    naive = _span("n", start, 10, task)
    naive["started_at"] = start.isoformat()
    assert client.post("/api/time-entries/auto", json={"entries": [naive]}).status_code == 422


def test_the_same_client_ref_of_another_user_is_their_own(client, two_users) -> None:
    mine = _task(client, "私の")
    start = (utcnow() - timedelta(hours=3)).replace(microsecond=0)
    assert _auto(client, _span("same", start, 10, mine))[0]["status"] == "created"
    two_users.other()
    theirs = _task(client, "他人の")
    assert _auto(client, _span("same", start, 10, mine))[0]["status"] == "invalid"
    assert _auto(client, _span("same", start, 10, theirs))[0]["status"] == "created"


def test_the_table_refuses_a_second_row_with_the_same_client_ref(client, db) -> None:
    started_at = utcnow() - timedelta(hours=2)
    db.add(TimeEntryModel(user_id=SINGLE_USER_ID, started_at=started_at,
                          ended_at=started_at + timedelta(minutes=5), source="auto", client_ref="r"))
    db.commit()
    db.add(TimeEntryModel(user_id=SINGLE_USER_ID, started_at=started_at + timedelta(minutes=10),
                          ended_at=started_at + timedelta(minutes=15), source="auto", client_ref="r"))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
