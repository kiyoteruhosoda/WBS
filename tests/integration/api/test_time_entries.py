"""打刻の API（task #154）。表（部分一意索引）・持ち主・日をまたぐ打刻を通しで見る。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime

import pytest
from sqlalchemy.exc import IntegrityError

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.infrastructure.auth.auth_settings import SINGLE_USER_ID
from src.infrastructure.database.models import TimeEntryModel, UserModel
from src.presentation.api.dependencies import get_current_user, get_db

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
        def me(self) -> None:
            client.app.dependency_overrides.pop(get_current_user, None)

        def other(self) -> None:
            client.app.dependency_overrides[get_current_user] = _as_user(other_user_id, OTHER_EMAIL)

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
