"""予定まわりを Scheduler へ移す（task #535 / Scheduler の ADR-0054 の段 0・1。WBS の ADR-0054）。

- 既定（設定なし）: 今までどおり
- 切り替えの 503（``SCHEDULER_CUTOVER_HOLD``）: 予定まわりの書き込みは Cookie でも Bearer でも 503（``Retry-After``）。読むのは通す
- 移転モード（``SCHEDULER_FORWARD_URL``）: Bearer の予定のアラームは Scheduler へ中継、ほかの書き込みは 409。
  **WBS の予定の表は書き換えられない**
- 打刻の関所（``TRACKER_*``）と並べても、互いの口に触らない

Scheduler は身代わり（``app.state.scheduler_relay``）。HTTP の中継そのものは
``tests/unit/infrastructure/test_http_scheduler_relay.py``。
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from datetime import timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from src.application.ports.scheduler_relay import (
    SchedulerRelayedResponse,
    SchedulerRelayRequest,
    SchedulerUnreachableError,
)
from src.application.ports.tracker_relay import RelayedResponse, RelayRequest
from src.infrastructure.scheduler_move.scheduler_move_settings import load_scheduler_move_settings
from src.presentation.middleware import scheduler_move_middleware
from src.shared.clock import isoformat_utc, utcnow

FORWARD_URL = "http://api.scheduler-test.svc.cluster.local:8000"
TRACKER_FORWARD_URL = "http://api.tracker-test.svc.cluster.local:8000"
CALENDAR_TABLES = (
    "calendars",
    "calendar_days_off",
    "calendar_imports",
    "calendar_imported_occurrences",
    "calendar_view_presets",
    "calendar_events",
    "calendar_event_exceptions",
    "calendar_event_moves",
    "calendar_event_completions",
)
DAY = "2026-10-13"
START = "2026-10-05T00:00:00Z"
ALARMS = "/api/calendar/alarms?from=2026-10-05T00:00:00Z&to=2026-10-06T00:00:00Z"

#: 予定まわりの書き込みすべて（画面が使うもの。関所は本文を読む前に断るので、本文は形だけ）
WRITES: list[tuple[str, str, dict | None]] = [
    ("POST", "/api/calendar/events", {"title": "予定", "start": START, "duration_minutes": 60}),
    ("PUT", "/api/calendar/events/1", {"title": "直した", "expected_version": 1}),
    ("PUT", "/api/calendar/events/1/series", {"title": "直した", "expected_version": 1}),
    ("DELETE", "/api/calendar/events/1", None),
    ("POST", "/api/calendar/events/1/occurrences/following", {"original_start": START}),
    ("POST", "/api/calendar/events/1/occurrences/split", {"original_start": START}),
    ("POST", "/api/calendar/events/1/occurrences/skip", {"original_start": START}),
    ("POST", "/api/calendar/events/1/occurrences/restore", {"original_start": START}),
    ("POST", "/api/calendar/events/1/occurrences/move", {"original_start": START, "start": START}),
    ("POST", "/api/calendar/events/1/occurrences/cancel-move", {"original_start": START}),
    ("PUT", "/api/calendar/events/1/done", {"original_start": START, "done": True}),
    ("POST", "/api/calendar/events/1/occurrences/delete-following", {"original_start": START}),
    ("POST", "/api/calendars", {"name": "仕事", "color_key": "TOMATO"}),
    ("PUT", "/api/calendars/order", {"calendar_ids": [1]}),
    ("PUT", "/api/calendars/visibility", {"visible_calendar_ids": [1]}),
    ("POST", "/api/calendars/imported", {"name": "Outlook", "url": "https://example.com/a.ics"}),
    ("PUT", "/api/calendars/1", {"name": "直した"}),
    ("POST", "/api/calendars/1/import", {"url": "https://example.com/a.ics"}),
    ("POST", "/api/calendars/1/refresh", None),
    ("DELETE", "/api/calendars/1/subscription", None),
    ("DELETE", "/api/calendars/1", None),
    ("POST", "/api/calendars/1/days-off", {"date": DAY, "name": "旅行"}),
    ("DELETE", f"/api/calendars/1/days-off/{DAY}", None),
    ("POST", "/api/calendars/1/days-off/japan", {"year": 2026}),
    ("POST", "/api/calendar-view-presets", {"name": "仕事だけ", "calendar_ids": [1]}),
    ("PUT", "/api/calendar-view-presets/1", {"name": "直した", "calendar_ids": [1]}),
    ("DELETE", "/api/calendar-view-presets/1", None),
    ("POST", "/api/calendar-view-presets/1/apply", None),
]
WRITE_IDS = [f"{m} {p}" for m, p, _ in WRITES]


class FakeScheduler:
    """Scheduler の api の身代わり。届いた中継を覚え、決めた答えを返す。"""

    def __init__(self) -> None:
        self.requests: list[SchedulerRelayRequest] = []
        self.answer = SchedulerRelayedResponse(
            status_code=200,
            headers={"content-type": "application/json", "www-authenticate": "Bearer"},
            body=b'{"from": "scheduler"}',
        )
        self.down = False

    async def relay(self, request: SchedulerRelayRequest) -> SchedulerRelayedResponse:
        if self.down:
            raise SchedulerUnreachableError("ConnectError: refused")
        self.requests.append(request)
        return self.answer

    async def aclose(self) -> None:
        return None


class FakeTracker:
    """打刻の関所の身代わり（2 つの関所が互いに触らないことを見るだけ）。"""

    def __init__(self) -> None:
        self.requests: list[RelayRequest] = []

    async def relay(self, request: RelayRequest) -> RelayedResponse:
        self.requests.append(request)
        return RelayedResponse(201, {"content-type": "application/json"}, b'{"from": "tracker"}')

    async def aclose(self) -> None:
        return None


def _token(client_id: str = "wbstimer-app") -> str:
    # 署名は確かめない（WBS は名乗りをログの見出しに使うだけ。確かめるのは Scheduler）
    return jwt.encode(
        {"sub": "taro", "client_id": client_id},
        "not-the-real-key-only-for-these-tests",
        algorithm="HS256",
    )


def _bearer(client_id: str = "wbstimer-app") -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(client_id)}"}


def _send(
    client: TestClient, method: str, path: str, body: dict | None, headers: dict | None = None
):
    return client.request(method, path, json=body, headers=headers or {})


def _snapshot(database_path: str) -> dict[str, list[tuple]]:
    with sqlite3.connect(database_path) as conn:
        return {
            t: conn.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall() for t in CALENDAR_TABLES
        }


class RelayLog(logging.Handler):
    """中継の行（``event=scheduler.relay``）だけを拾う。"""

    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.lines: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(record, "event", None) == "scheduler.relay":
            self.lines.append(record)


@pytest.fixture
def relay_log() -> Iterator[RelayLog]:
    # create_app がルートの出力先を作り直すので、中継の係のロガーに直に付ける
    logger = logging.getLogger(scheduler_move_middleware.__name__)
    handler = RelayLog()
    logger.addHandler(handler)
    level = logger.level
    logger.setLevel(logging.INFO)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)


@pytest.fixture
def make_client(database_path, monkeypatch) -> Iterator:
    clients: list[TestClient] = []

    def make(*, hold: bool = False, forward: bool = False, tracker: bool = False) -> TestClient:
        if hold:
            monkeypatch.setenv("SCHEDULER_CUTOVER_HOLD", "true")
        else:
            monkeypatch.delenv("SCHEDULER_CUTOVER_HOLD", raising=False)
        if forward:
            monkeypatch.setenv("SCHEDULER_FORWARD_URL", FORWARD_URL + "/")
        else:
            monkeypatch.delenv("SCHEDULER_FORWARD_URL", raising=False)
        monkeypatch.delenv("SCHEDULER_PUBLIC_URL", raising=False)
        monkeypatch.delenv("TRACKER_CUTOVER_HOLD", raising=False)
        if tracker:
            monkeypatch.setenv("TRACKER_FORWARD_URL", TRACKER_FORWARD_URL)
        else:
            monkeypatch.delenv("TRACKER_FORWARD_URL", raising=False)
        from main import create_app

        app = create_app(db_path=database_path)
        if forward:
            app.state.scheduler_relay = FakeScheduler()
        if tracker:
            app.state.tracker_relay = FakeTracker()
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def _seed(client: TestClient) -> tuple[int, int]:
    """移す前の WBS に、予定（明日）を結んだタスクとまだ時間を取っていないタスク・カレンダー・
    表示の組み合わせを作る。返すのは (予定を結んだタスク, 時間を取っていないタスク)。"""
    due = utcnow().date().isoformat()
    task_id = client.post("/api/tasks", json={"title": "設計", "due_date": due}).json()["id"]
    unbooked_id = client.post("/api/tasks", json={"title": "未定", "due_date": due}).json()["id"]
    # 予定の開始は分ちょうど（秒があると 422）
    tomorrow = isoformat_utc((utcnow() + timedelta(days=1)).replace(second=0, microsecond=0))
    res = client.post(
        "/api/calendar/events",
        json={"title": "設計の時間", "start": tomorrow, "duration_minutes": 90, "task_id": task_id},
    )
    assert res.status_code == 201, res.text
    res = client.post("/api/calendars", json={"name": "仕事", "color_key": "TOMATO"})
    assert res.status_code == 201, res.text
    calendar_id = res.json()["id"]
    res = client.post(
        "/api/calendar-view-presets", json={"name": "仕事だけ", "calendar_ids": [calendar_id]}
    )
    assert res.status_code == 201, res.text
    return task_id, unbooked_id


def _task(client: TestClient, task_id: int) -> dict:
    return next(t for t in client.get("/api/tasks").json() if t["id"] == task_id)


# ── 既定 ────────────────────────────────────────────────────────────────


def test_by_default_nothing_changes(make_client) -> None:
    client = make_client()
    assert client.get("/api/scheduler-move").json() == {
        "mode": "off",
        "url": "https://scheduler.nolumia.com",
    }
    assert client.app.state.scheduler_relay is None
    task_id, unbooked_id = _seed(client)
    assert _task(client, task_id)["scheduled_hours"] == 1.5
    assert [t["id"] for t in client.get("/api/today").json()["tasks_to_schedule"]] == [unbooked_id]
    assert (
        client.post("/api/calendars", json={"name": "家", "color_key": "TOMATO"}).status_code == 201
    )


# ── 切り替えの 503 ───────────────────────────────────────────────────────


@pytest.mark.parametrize(("method", "path", "body"), WRITES, ids=WRITE_IDS)
@pytest.mark.parametrize("bearer", [False, True], ids=["cookie", "bearer"])
def test_during_the_cutover_every_calendar_write_waits_with_503(
    make_client, database_path, method, path, body, bearer
) -> None:
    _seed(make_client())
    before = _snapshot(database_path)
    client = make_client(hold=True)

    res = _send(client, method, path, body, _bearer() if bearer else None)

    assert res.status_code == 503, res.text
    assert res.headers["Retry-After"] == "120"
    assert res.json()["reason"] == "scheduler_cutover"
    assert _snapshot(database_path) == before


def test_during_the_cutover_reading_is_allowed_and_other_writes_are_untouched(make_client) -> None:
    _seed(make_client())
    client = make_client(hold=True)
    assert client.get("/api/scheduler-move").json()["mode"] == "hold"
    assert client.get("/api/calendars").status_code == 200
    assert client.get("/api/calendar/occurrences?from=2026-10-05&to=2026-10-11").status_code == 200
    assert client.get("/api/calendar-view-presets").status_code == 200
    assert client.get(ALARMS, headers=_bearer()).status_code == 200
    # 予定まわりの外（タスク・打刻）は書ける
    assert client.post("/api/tasks", json={"title": "書ける"}).status_code == 201
    assert client.post("/api/time-entries/start", json={}).status_code == 201


def test_during_the_cutover_imported_calendars_are_not_refreshed(make_client, monkeypatch) -> None:
    """購読の読み込み直しも予定の表に書くので、切り替えの間と移した後は動かさない。"""
    import main

    started: list[object] = []
    monkeypatch.setattr(
        main, "start_calendar_feed_refresh_worker", lambda *args: started.append(args)
    )
    make_client()
    assert len(started) == 1
    make_client(hold=True)
    make_client(forward=True)
    assert len(started) == 1


# ── 移転モード ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(("method", "path", "body"), WRITES, ids=WRITE_IDS)
@pytest.mark.parametrize("bearer", [False, True], ids=["cookie", "bearer"])
def test_after_the_move_calendar_writes_are_refused_with_409(
    make_client, database_path, method, path, body, bearer
) -> None:
    """移した後、WBS の予定の表は書き換えられない（画面からでも、Bearer でも。中継もしない）。"""
    _seed(make_client())
    before = _snapshot(database_path)
    client = make_client(forward=True)

    res = _send(client, method, path, body, _bearer() if bearer else None)

    assert res.status_code == 409, res.text
    assert res.json()["reason"] == "moved_to_scheduler"
    assert res.json()["detail"] == "Calendar has moved to Scheduler (scheduler.nolumia.com)"
    assert res.json()["scheduler_url"] == "https://scheduler.nolumia.com"
    assert client.app.state.scheduler_relay.requests == []
    assert _snapshot(database_path) == before


def test_the_apps_alarm_request_is_handed_to_scheduler_as_it_came(make_client, relay_log) -> None:
    client = make_client(forward=True)
    scheduler: FakeScheduler = client.app.state.scheduler_relay
    token = _token("wbstimer-app")

    res = client.get(ALARMS, headers={"Authorization": f"Bearer {token}", "Cookie": "wbs=web"})

    assert res.status_code == 200
    assert res.content == b'{"from": "scheduler"}'
    assert res.headers["content-type"] == "application/json"
    assert res.headers["www-authenticate"] == "Bearer"
    [sent] = scheduler.requests
    assert (sent.method, sent.path, sent.query) == (
        "GET",
        "/api/calendar/alarms",
        "from=2026-10-05T00:00:00Z&to=2026-10-06T00:00:00Z",
    )
    assert sent.headers["authorization"] == f"Bearer {token}"
    [line] = relay_log.lines
    assert (line.method, line.route, line.client_id, line.status_code) == (
        "GET",
        "/api/calendar/alarms",
        "wbstimer-app",
        200,
    )


def test_the_apps_other_calendar_reads_are_not_relayed(make_client, relay_log) -> None:
    """予定まわりで Bearer を受けるのはアラームの口だけ。ほかは今までどおり WBS が答える（中継しない）。"""
    client = make_client(forward=True)
    res = client.get("/api/calendars", headers=_bearer())
    assert res.status_code != 409
    assert client.app.state.scheduler_relay.requests == []
    assert relay_log.lines == []


def test_scheduler_errors_come_back_as_they_are(make_client) -> None:
    client = make_client(forward=True)
    scheduler: FakeScheduler = client.app.state.scheduler_relay
    scheduler.answer = SchedulerRelayedResponse(
        401, {"content-type": "application/json"}, b'{"detail": "no"}'
    )
    res = client.get(ALARMS, headers=_bearer())
    assert (res.status_code, res.json()) == (401, {"detail": "no"})


def test_when_scheduler_does_not_answer_the_app_gets_a_5xx(make_client) -> None:
    client = make_client(forward=True)
    client.app.state.scheduler_relay.down = True
    res = client.get(ALARMS, headers=_bearer())
    assert res.status_code == 502
    assert res.json()["reason"] == "scheduler_unreachable"


def test_after_the_move_the_screen_still_reads_the_frozen_calendar(make_client) -> None:
    """Cookie の読みは通す（古いタブが壊れて見えないように。新しい画面は読まない）。"""
    _seed(make_client())
    client = make_client(forward=True)
    assert client.get("/api/calendars").status_code == 200
    assert client.get(ALARMS).status_code == 200
    assert client.app.state.scheduler_relay.requests == []


def test_after_the_move_the_server_reads_no_calendar_rows(make_client) -> None:
    task_id, _unbooked_id = _seed(make_client())
    client = make_client(forward=True)
    assert client.get("/api/scheduler-move").json() == {
        "mode": "moved",
        "url": "https://scheduler.nolumia.com",
    }
    task = _task(client, task_id)
    assert (task["scheduled_hours"], task["unscheduled_hours"]) == (None, None)
    assert client.get("/api/today").json()["tasks_to_schedule"] == []
    periods = client.get("/api/actuals/periods").json()["periods"]
    assert all(
        p["planned_task_seconds"] == 0 and p["planned_off_task_seconds"] == 0 for p in periods
    )
    # タスクそのものは WBS のまま
    assert client.post("/api/tasks", json={"title": "タスクは WBS"}).status_code == 201


# ── 打刻の関所と並べる ──────────────────────────────────────────────────


def test_the_two_gates_do_not_touch_each_others_routes(make_client, relay_log) -> None:
    client = make_client(forward=True, tracker=True)
    scheduler: FakeScheduler = client.app.state.scheduler_relay
    tracker: FakeTracker = client.app.state.tracker_relay

    assert client.post("/api/time-entries/start", json={}, headers=_bearer()).status_code == 201
    assert client.get(ALARMS, headers=_bearer()).status_code == 200
    # 画面からの書き込みは、それぞれの関所が自分の理由で断る
    assert client.post("/api/time-entries/start", json={}).json()["reason"] == "moved_to_tracker"
    res = client.post("/api/calendars", json={"name": "家", "color_key": "TOMATO"})
    assert res.json()["reason"] == "moved_to_scheduler"

    assert [r.path for r in tracker.requests] == ["/api/time-entries/start"]
    assert [r.path for r in scheduler.requests] == ["/api/calendar/alarms"]
    assert client.get("/api/tracker-move").json()["mode"] == "moved"
    assert client.get("/api/scheduler-move").json()["mode"] == "moved"


def test_the_settings_are_read_from_the_environment(monkeypatch) -> None:
    for name in ("SCHEDULER_CUTOVER_HOLD", "SCHEDULER_FORWARD_URL", "SCHEDULER_PUBLIC_URL"):
        monkeypatch.delenv(name, raising=False)
    assert load_scheduler_move_settings().phase.value == "off"
    assert load_scheduler_move_settings().frozen is False

    monkeypatch.setenv("SCHEDULER_CUTOVER_HOLD", "true")
    monkeypatch.setenv("SCHEDULER_FORWARD_URL", FORWARD_URL + "/")
    monkeypatch.setenv("SCHEDULER_PUBLIC_URL", "https://schedulerstg.nolumia.com/")
    settings = load_scheduler_move_settings()
    # 両方入っていれば 503 が先（書き込みは待たせる。Bearer の読みは中継）
    assert (settings.phase.value, settings.moved, settings.frozen) == ("hold", True, True)
    assert settings.forward_url == FORWARD_URL
    assert settings.public_url == "https://schedulerstg.nolumia.com"

    monkeypatch.setenv("SCHEDULER_CUTOVER_HOLD", "false")
    assert load_scheduler_move_settings().phase.value == "moved"
