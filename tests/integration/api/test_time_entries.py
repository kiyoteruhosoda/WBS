"""打刻の API（task #154）。表（部分一意索引）・持ち主・日をまたぐ打刻を通しで見る。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.infrastructure.auth.auth_settings import SINGLE_USER_ID
from src.infrastructure.database.models import (
    AutoTimeEntryReceiptModel,
    TimeEntryCarvingModel,
    TimeEntryModel,
    UserModel,
)
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


# ── PC の自動記録（WinTrack、task #379 / ADR-0042・Working が正: task #386 / ADR-0045） ──


def _auto(client, *items):
    res = client.post("/api/time-entries/auto", json={"entries": list(items)})
    assert res.status_code == 200, res.text
    return res.json()["results"]


def _span(ref: str, start: datetime, minutes: int, task_id: int, mode: str | None = None) -> dict:
    # 送り手は +09:00 で送る。応答は Z 付きの UTC
    jst = timedelta(hours=9)
    span = {
        "client_ref": ref,
        "started_at": f"{(start + jst).isoformat()}+09:00",
        "ended_at": f"{(start + timedelta(minutes=minutes) + jst).isoformat()}+09:00",
        "task_id": task_id,
    }
    if mode is not None:
        span["mode"] = mode
    return span


def _z(value: datetime) -> str:
    return f"{value.isoformat()}Z"


def _manual_entry(client, start: datetime, minutes: int, task_id: int) -> dict:
    res = client.post(
        "/api/time-entries",
        json={"started_at": _z(start), "ended_at": _z(start + timedelta(minutes=minutes)), "task_id": task_id},
    )
    assert res.status_code == 201, res.text
    return res.json()


def test_fill_entries_are_created_once_and_marked_auto(client, db) -> None:
    task = _task(client, "見積書を作る")
    start = (utcnow() - timedelta(hours=3)).replace(microsecond=0)
    first = _auto(client, _span("3f2b-a", start, 40, task))
    assert [(r["client_ref"], r["status"], r["error"]) for r in first] == [("3f2b-a", "created", None)]
    [entry] = first[0]["entries"]
    assert (entry["source"], entry["auto_mode"]) == ("auto", "fill")
    assert entry["started_at"] == _z(start)
    assert entry["duration_seconds"] == 40 * 60
    assert entry["task_title"] == "見積書を作る"

    # 送り直しは同じ打刻を返し、中身が違っても上書きしない
    again = _auto(client, _span("3f2b-a", start, 90, task, mode="override"))
    assert again[0]["status"] == "duplicate"
    assert [e["id"] for e in again[0]["entries"]] == [entry["id"]]
    assert again[0]["entries"][0]["duration_seconds"] == 40 * 60
    assert db.query(TimeEntryModel).filter(TimeEntryModel.client_ref == "3f2b-a").count() == 1


def test_fill_takes_only_the_free_parts_around_working(client) -> None:
    project = _task(client, "ProjectA")
    working = _task(client, "Working")
    start = (utcnow() - timedelta(hours=4)).replace(microsecond=0)
    _manual_entry(client, start + timedelta(minutes=20), 20, working)
    [result] = _auto(client, _span("gap", start, 60, project, mode="fill"))
    assert result["status"] == "created"
    assert [(e["started_at"], e["ended_at"]) for e in result["entries"]] == [
        (_z(start), _z(start + timedelta(minutes=20))),
        (_z(start + timedelta(minutes=40)), _z(start + timedelta(minutes=60))),
    ]
    # 送り直しは 2 本とも返す
    [again] = _auto(client, _span("gap", start, 60, project))
    assert again["status"] == "duplicate" and len(again["entries"]) == 2
    # 全部覆われていれば covered（エラーではない）
    [covered] = _auto(client, _span("covered", start + timedelta(minutes=20), 20, project))
    assert (covered["status"], covered["entries"], covered["error"]) == ("covered", [], None)


def test_override_carves_working_and_keeps_what_it_was(client, db) -> None:
    working = _task(client, "Working")
    exception = _task(client, "ProjectB")
    start = (utcnow() - timedelta(hours=4)).replace(microsecond=0)
    manual = _manual_entry(client, start, 180, working)
    [result] = _auto(client, _span("ex", start + timedelta(minutes=60), 30, exception, mode="override"))
    assert result["status"] == "created"
    assert [e["auto_mode"] for e in result["entries"]] == ["override"]

    listed = client.get(
        "/api/time-entries", params={"start": _z(start - timedelta(hours=1)), "end": _z(utcnow())}
    ).json()
    assert [(e["started_at"], e["ended_at"], e["source"]) for e in listed] == [
        (_z(start), _z(start + timedelta(minutes=60)), "manual"),
        (_z(start + timedelta(minutes=60)), _z(start + timedelta(minutes=90)), "auto"),
        (_z(start + timedelta(minutes=90)), _z(start + timedelta(minutes=180)), "split"),
    ]
    [carving] = db.query(TimeEntryCarvingModel).all()
    assert (carving.time_entry_id, carving.action, carving.client_ref) == (manual["id"], "split", "ex")
    assert (carving.started_at, carving.ended_at) == (start, start + timedelta(minutes=180))

    # ほかの自動の打刻とは重ねない
    [overlap] = _auto(client, _span("ex2", start + timedelta(minutes=80), 30, exception, mode="override"))
    assert (overlap["status"], overlap["error"]) == ("overlap", "overlaps_automatic_entry")


def test_auto_results_are_per_entry(client) -> None:
    task = _task(client, "設計")
    start = (utcnow() - timedelta(hours=5)).replace(microsecond=0)
    results = _auto(
        client,
        _span("ok", start, 30, task),
        _span("zero-length", start + timedelta(hours=3), 0, task),
        _span("reversed", start + timedelta(hours=1), -10, task),
        _span("old", utcnow() - timedelta(days=8), 30, task),
        _span("future", utcnow() + timedelta(hours=1), 30, task),
        _span("no-task", start + timedelta(hours=2), 30, 999_999),
        _span("mode", start + timedelta(hours=2), 30, task, mode="replace"),
    )
    assert [(r["client_ref"], r["status"], r["error"]) for r in results] == [
        ("ok", "created", None),
        ("zero-length", "invalid", "ended_not_after_started"),
        ("reversed", "invalid", "ended_not_after_started"),
        ("old", "invalid", "too_old"),
        ("future", "invalid", "in_future"),
        ("no-task", "invalid", "task_not_found"),
        ("mode", "invalid", "unknown_mode"),
    ]
    assert all(r["entries"] == [] for r in results[1:])


def test_start_replaces_fill_but_not_override(client) -> None:
    project = _task(client, "ProjectA")
    working = _task(client, "Working")
    start = (utcnow() - timedelta(hours=3)).replace(microsecond=0)
    _auto(client, _span("fill", start, 60, project))
    res = client.post(
        "/api/time-entries/start", json={"task_id": working, "at": _z(start + timedelta(minutes=30))}
    )
    assert res.status_code == 201, res.text
    listed = client.get(
        "/api/time-entries", params={"start": _z(start - timedelta(hours=1)), "end": _z(utcnow())}
    ).json()
    assert [(e["started_at"], e["ended_at"], e["source"]) for e in listed] == [
        (_z(start), _z(start + timedelta(minutes=30)), "auto"),
        (_z(start + timedelta(minutes=30)), None, "timer"),
    ]

    # override（例外作業）が at 以降にあれば始めない
    client.post("/api/time-entries/stop", json={"at": _z(start + timedelta(minutes=40))})
    _auto(client, _span("ex", start + timedelta(minutes=60), 30, project, mode="override"))
    res = client.post(
        "/api/time-entries/start", json={"task_id": working, "at": _z(start + timedelta(minutes=50))}
    )
    assert res.status_code == 409


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


def test_the_receipts_table_refuses_a_second_row_with_the_same_client_ref(client, db) -> None:
    received = utcnow()
    db.add(AutoTimeEntryReceiptModel(user_id=SINGLE_USER_ID, client_ref="r", mode="fill", received_at=received))
    db.commit()
    db.add(AutoTimeEntryReceiptModel(user_id=SINGLE_USER_ID, client_ref="r", mode="override", received_at=received))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_moving_an_entry_onto_another_is_refused(client) -> None:
    """時刻を直してほかの打刻と重なれば 409（task #397 / ADR-0049）。接するだけ・時刻を変えない修正は通す。"""
    task = _task(client, "設計")
    base = (utcnow() - timedelta(hours=5)).replace(microsecond=0)
    first = _manual_entry(client, base, 60, task)
    second = _manual_entry(client, base + timedelta(hours=2), 60, task)
    url = f"/api/time-entries/{first['id']}"

    res = client.patch(url, json={"ended_at": _z(base + timedelta(hours=2, minutes=10))})
    assert res.status_code == 409
    assert res.json()["detail"] == f"the time entry would overlap another time entry (ids={second['id']})"
    # 包むように動かしても同じ
    wrapped = client.patch(
        url, json={"started_at": _z(base + timedelta(hours=1)), "ended_at": _z(base + timedelta(hours=4))}
    )
    assert wrapped.status_code == 409
    assert client.get(url).json()["ended_at"] == _z(base + timedelta(hours=1))

    # 次の打刻の始まりにちょうど接するのは重なりではない
    touching = client.patch(url, json={"ended_at": _z(base + timedelta(hours=2))})
    assert touching.status_code == 200, touching.text


def test_an_entry_that_already_overlaps_can_still_get_a_memo(client) -> None:
    """足す口は重なりを断らない（締めの画面で知らせる。ADR-0012）。時刻を変えない修正は重なっていても通す。"""
    task = _task(client, "設計")
    base = (utcnow() - timedelta(hours=5)).replace(microsecond=0)
    first = _manual_entry(client, base, 60, task)
    _manual_entry(client, base + timedelta(minutes=30), 60, task)
    url = f"/api/time-entries/{first['id']}"
    assert client.patch(url, json={"memo": "重なっている"}).status_code == 200
    # 重なりを解く方向の修正は通る
    assert client.patch(url, json={"ended_at": _z(base + timedelta(minutes=30))}).status_code == 200


def test_the_running_entry_cannot_start_over_a_stopped_one(client) -> None:
    task = _task(client, "設計")
    earlier = _manual_entry(client, (utcnow() - timedelta(hours=3)).replace(microsecond=0), 60, task)
    running = _start(client, task_id=task)["started"]
    url = f"/api/time-entries/{running['id']}"
    res = client.patch(url, json={"started_at": earlier["started_at"]})
    assert res.status_code == 409
    assert res.json()["detail"].endswith(f"(ids={earlier['id']})")
    assert client.patch(url, json={"started_at": earlier["ended_at"]}).status_code == 200


def test_fill_is_extended_when_the_same_run_goes_on(client, db) -> None:
    """同じ client_ref で終わりだけ遅くなったら、増えた分だけ伸ばす（ADR-0050）。"""
    task = _task(client, "問い合わせ対応")
    start = (utcnow() - timedelta(hours=4)).replace(microsecond=0)
    [first] = _auto(client, _span("run", start, 30, task))
    assert first["status"] == "created"

    [longer] = _auto(client, _span("run", start, 70, task))
    assert longer["status"] == "extended"
    assert [(e["id"], e["started_at"], e["ended_at"]) for e in longer["entries"]] == [
        (first["entries"][0]["id"], _z(start), _z(start + timedelta(minutes=70)))
    ]
    # 同じ終わりの送り直しは、伸ばさずにそのまま返す
    [again] = _auto(client, _span("run", start, 70, task))
    assert again["status"] == "duplicate"
    assert again["entries"][0]["ended_at"] == _z(start + timedelta(minutes=70))
    assert db.query(TimeEntryModel).filter(TimeEntryModel.client_ref == "run").count() == 1


def test_an_extension_fills_around_working_in_the_new_part(client) -> None:
    project = _task(client, "ProjectA")
    working = _task(client, "Working")
    start = (utcnow() - timedelta(hours=4)).replace(microsecond=0)
    _auto(client, _span("run", start, 30, project))
    _manual_entry(client, start + timedelta(minutes=40), 10, working)

    [longer] = _auto(client, _span("run", start, 60, project))
    assert longer["status"] == "extended"
    assert [(e["started_at"], e["ended_at"]) for e in longer["entries"]] == [
        (_z(start), _z(start + timedelta(minutes=40))),
        (_z(start + timedelta(minutes=50)), _z(start + timedelta(minutes=60))),
    ]


@pytest.mark.parametrize(
    "changed",
    [{"task": "other"}, {"minutes_from": 5}, {"mode": "override"}, {"minutes": 20}],
    ids=["another-task", "another-start", "another-mode", "earlier-end"],
)
def test_other_differences_are_not_extensions(client, changed) -> None:
    task = _task(client, "設計")
    other = _task(client, "別のタスク")
    start = (utcnow() - timedelta(hours=4)).replace(microsecond=0)
    _auto(client, _span("run", start, 30, task))
    [result] = _auto(
        client,
        _span(
            "run",
            start + timedelta(minutes=changed.get("minutes_from", 0)),
            changed.get("minutes", 60),
            other if "task" in changed else task,
            mode=changed.get("mode"),
        ),
    )
    assert result["status"] == "duplicate"
    assert [(e["started_at"], e["ended_at"]) for e in result["entries"]] == [
        (_z(start), _z(start + timedelta(minutes=30)))
    ]


def test_override_is_extended_by_carving_working_further(client) -> None:
    working = _task(client, "Working")
    exception = _task(client, "ProjectB")
    start = (utcnow() - timedelta(hours=4)).replace(microsecond=0)
    _manual_entry(client, start, 180, working)
    _auto(client, _span("ex", start + timedelta(minutes=60), 30, exception, mode="override"))

    [longer] = _auto(client, _span("ex", start + timedelta(minutes=60), 50, exception, mode="override"))
    assert longer["status"] == "extended"
    listed = client.get(
        "/api/time-entries", params={"start": _z(start - timedelta(hours=1)), "end": _z(utcnow())}
    ).json()
    assert [(e["started_at"], e["ended_at"], e["source"]) for e in listed] == [
        (_z(start), _z(start + timedelta(minutes=60)), "manual"),
        (_z(start + timedelta(minutes=60)), _z(start + timedelta(minutes=110)), "auto"),
        (_z(start + timedelta(minutes=110)), _z(start + timedelta(minutes=180)), "split"),
    ]


def test_an_override_extension_steps_around_other_automatic_entries(client) -> None:
    project = _task(client, "ProjectA")
    exception = _task(client, "ProjectB")
    start = (utcnow() - timedelta(hours=4)).replace(microsecond=0)
    _auto(client, _span("ex", start, 30, exception, mode="override"))
    _auto(client, _span("fill", start + timedelta(minutes=30), 10, project))

    [longer] = _auto(client, _span("ex", start, 60, exception, mode="override"))
    assert longer["status"] == "extended"
    assert [(e["started_at"], e["ended_at"]) for e in longer["entries"]] == [
        (_z(start), _z(start + timedelta(minutes=30))),
        (_z(start + timedelta(minutes=40)), _z(start + timedelta(minutes=60))),
    ]
