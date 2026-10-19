"""打刻まわりを Tracker へ移す（task #526 / ADR-0053 の段 0・1。WBS の ADR-0053）。

- 既定（設定なし）: 今までどおり
- 切り替えの 503（``TRACKER_CUTOVER_HOLD``）: 打刻まわりの書き込みは Cookie でも Bearer でも 503（``Retry-After``）。読むのは通す
- 移転モード（``TRACKER_FORWARD_URL``）: Bearer は Tracker へ中継、Cookie の書き込みは 409。
  **WBS の打刻まわりの表は書き換えられない**（#526 AC3）

Tracker は身代わり（``app.state.tracker_relay``）。HTTP の中継そのものは ``tests/unit/infrastructure/test_http_tracker_relay.py``。
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from datetime import timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from src.application.ports.tracker_relay import (
    RelayedResponse,
    RelayRequest,
    TrackerUnreachableError,
)
from src.infrastructure.tracker_move.tracker_move_settings import load_tracker_move_settings
from src.presentation.middleware import tracker_move_middleware
from src.shared.clock import utcnow

FORWARD_URL = "http://api.tracker-test.svc.cluster.local:8000"
TRACKING_TABLES = (
    "time_entries",
    "work_breaks",
    "pc_activity_days",
    "pc_activity_spans",
    "tracking_rules",
    "tracking_rule_books",
    "auto_time_entry_receipts",
    "time_entry_carvings",
    "closing_periods",
    "work_logs",
)
DAY = "2026-10-19"
SPAN = {"started_at": "2026-10-19T01:00:00Z", "ended_at": "2026-10-19T02:00:00Z"}

#: 打刻まわりの書き込みすべて（画面・wbstimer・WinTrack が使うもの）
WRITES: list[tuple[str, str, dict | None]] = [
    ("POST", "/api/time-entries/start", {}),
    ("POST", "/api/time-entries/stop", {}),
    ("POST", "/api/time-entries/auto", {"entries": []}),
    ("POST", "/api/time-entries", {**SPAN, "task_id": None}),
    ("POST", "/api/time-entries/merge", {"entry_ids": [1, 2]}),
    ("POST", "/api/time-entries/assign", {"entry_ids": [1], "task_id": None}),
    ("POST", "/api/time-entries/from-occurrence", {"event_id": 1, "start": SPAN["started_at"]}),
    ("POST", "/api/time-entries/1/split", {"at": "2026-10-19T01:30:00Z"}),
    ("PATCH", "/api/time-entries/1", {"memo": "直した"}),
    ("DELETE", "/api/time-entries/1", None),
    ("PUT", f"/api/breaks/auto/{DAY}", {"time_zone": "Asia/Tokyo", "breaks": [SPAN]}),
    ("PUT", f"/api/pc-activity/{DAY}", {"time_zone": "Asia/Tokyo", "spans": [SPAN]}),
    ("POST", "/api/tracking-rules", {"task_id": 1, "app": "EXCEL.EXE", "title_contains": None}),
    ("PUT", "/api/tracking-rules/order", {"rule_ids": [1]}),
    ("PATCH", "/api/tracking-rules/1", {"app": "WORD.EXE"}),
    ("DELETE", "/api/tracking-rules/1", None),
    ("POST", "/api/closing-periods/2026-10-01/close", None),
    ("POST", "/api/closing-periods/2026-10-01/reopen", None),
]
WRITE_IDS = [f"{m} {p}" for m, p, _ in WRITES]


class FakeTracker:
    """Tracker の api の身代わり。届いた中継を覚え、決めた答えを返す。"""

    def __init__(self) -> None:
        self.requests: list[RelayRequest] = []
        self.answer = RelayedResponse(
            status_code=201,
            headers={"content-type": "application/json", "www-authenticate": "Bearer"},
            body=b'{"from": "tracker"}',
        )
        self.down = False

    async def relay(self, request: RelayRequest) -> RelayedResponse:
        if self.down:
            raise TrackerUnreachableError("ConnectError: refused")
        self.requests.append(request)
        return self.answer

    async def aclose(self) -> None:
        return None


def _token(client_id: str = "wintrack-app") -> str:
    # 署名は確かめない（WBS は名乗りをログの見出しに使うだけ。確かめるのは Tracker）
    return jwt.encode(
        {"sub": "taro", "client_id": client_id},
        "not-the-real-key-only-for-these-tests",
        algorithm="HS256",
    )


def _bearer(client_id: str = "wintrack-app") -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(client_id)}"}


def _send(
    client: TestClient, method: str, path: str, body: dict | None, headers: dict | None = None
):
    return client.request(method, path, json=body, headers=headers or {})


def _snapshot(database_path: str) -> dict[str, list[tuple]]:
    with sqlite3.connect(database_path) as conn:
        return {
            t: conn.execute(f"SELECT * FROM {t} ORDER BY 1").fetchall() for t in TRACKING_TABLES
        }


class RelayLog(logging.Handler):
    """中継の行（``event=tracker.relay``）だけを拾う。"""

    def __init__(self) -> None:
        super().__init__(logging.INFO)
        self.lines: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(record, "event", None) == "tracker.relay":
            self.lines.append(record)


@pytest.fixture
def relay_log() -> Iterator[RelayLog]:
    # create_app がルートの出力先を作り直すので、中継の係のロガーに直に付ける
    logger = logging.getLogger(tracker_move_middleware.__name__)
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

    def make(*, hold: bool = False, forward: bool = False) -> TestClient:
        if hold:
            monkeypatch.setenv("TRACKER_CUTOVER_HOLD", "true")
        else:
            monkeypatch.delenv("TRACKER_CUTOVER_HOLD", raising=False)
        if forward:
            monkeypatch.setenv("TRACKER_FORWARD_URL", FORWARD_URL + "/")
        else:
            monkeypatch.delenv("TRACKER_FORWARD_URL", raising=False)
        monkeypatch.delenv("TRACKER_PUBLIC_URL", raising=False)
        from main import create_app

        app = create_app(db_path=database_path)
        if forward:
            app.state.tracker_relay = FakeTracker()
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.__exit__(None, None, None)


def _seed(client: TestClient) -> int:
    """移す前の WBS に、打刻・止まった打刻・規則を作る。"""
    task_id = client.post("/api/tasks", json={"title": "設計"}).json()["id"]
    now = utcnow()
    hour = timedelta(hours=1)
    res = client.post(
        "/api/time-entries",
        json={
            "started_at": (now - 3 * hour).isoformat() + "Z",
            "ended_at": (now - 2 * hour).isoformat() + "Z",
            "task_id": task_id,
        },
    )
    assert res.status_code == 201, res.text
    assert client.post("/api/time-entries/start", json={"task_id": task_id}).status_code == 201
    res = client.post("/api/tracking-rules", json={"task_id": task_id, "app": "EXCEL.EXE"})
    assert res.status_code == 201, res.text
    return task_id


# ── 既定 ────────────────────────────────────────────────────────────────


def test_by_default_nothing_changes(make_client) -> None:
    client = make_client()
    assert client.get("/api/tracker-move").json() == {
        "mode": "off",
        "url": "https://tracker.nolumia.com",
    }
    assert client.app.state.tracker_relay is None
    _seed(client)
    assert client.get("/api/time-entries/current").json()["entry"] is not None
    assert client.get("/api/today").json()["running"] is not None


# ── 切り替えの 503 ───────────────────────────────────────────────────────


@pytest.mark.parametrize(("method", "path", "body"), WRITES, ids=WRITE_IDS)
@pytest.mark.parametrize("bearer", [False, True], ids=["cookie", "bearer"])
def test_during_the_cutover_every_tracking_write_waits_with_503(
    make_client, database_path, method, path, body, bearer
) -> None:
    _seed(make_client())
    before = _snapshot(database_path)
    client = make_client(hold=True)

    res = _send(client, method, path, body, _bearer() if bearer else None)

    assert res.status_code == 503, res.text
    assert res.headers["Retry-After"] == "120"
    assert res.json()["reason"] == "tracker_cutover"
    assert _snapshot(database_path) == before


def test_during_the_cutover_reading_is_allowed_and_other_writes_are_untouched(make_client) -> None:
    _seed(make_client())
    client = make_client(hold=True)
    assert client.get("/api/tracker-move").json()["mode"] == "hold"
    assert client.get("/api/time-entries/current").status_code == 200
    assert client.get("/api/tracking-rules/editor").status_code == 200
    assert client.get("/api/closing-periods/pending").status_code == 200
    # 打刻まわりの外（タスク・予定）は書ける
    assert client.post("/api/tasks", json={"title": "書ける"}).status_code == 201


# ── 移転モード ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(("method", "path", "body"), WRITES, ids=WRITE_IDS)
def test_after_the_move_the_screens_writes_are_refused_with_409(
    make_client, database_path, method, path, body
) -> None:
    _seed(make_client())
    before = _snapshot(database_path)
    client = make_client(forward=True)

    res = _send(client, method, path, body)

    assert res.status_code == 409, res.text
    assert res.json()["reason"] == "moved_to_tracker"
    assert res.json()["detail"] == "Time tracking has moved to Tracker (tracker.nolumia.com)"
    assert res.json()["tracker_url"] == "https://tracker.nolumia.com"
    assert client.app.state.tracker_relay.requests == []
    assert _snapshot(database_path) == before


@pytest.mark.parametrize(("method", "path", "body"), WRITES, ids=WRITE_IDS)
def test_after_the_move_the_apps_writes_never_reach_wbs_tables(
    make_client, database_path, method, path, body
) -> None:
    """#526 AC3: 移した後、wbstimer・WinTrack の書き込みは WBS の表に入らない（Tracker へ行くか、断られる）。"""
    _seed(make_client())
    before = _snapshot(database_path)
    client = make_client(forward=True)

    res = _send(client, method, path, body, _bearer())

    tracker = client.app.state.tracker_relay
    if path.startswith("/api/closing-periods"):
        # 締めは画面だけの口。中継しない
        assert res.status_code == 409
        assert tracker.requests == []
    else:
        assert res.status_code == 201
        assert [(r.method, r.path) for r in tracker.requests] == [(method, path)]
    assert _snapshot(database_path) == before


def test_the_apps_requests_are_handed_to_tracker_as_they_came(make_client, relay_log) -> None:
    client = make_client(forward=True)
    tracker: FakeTracker = client.app.state.tracker_relay
    token = _token("wintrack-app")

    res = client.post(
        "/api/time-entries/auto?dry=1",
        content=b'{"entries": []}',
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )

    assert res.status_code == 201
    assert res.content == b'{"from": "tracker"}'
    assert res.headers["content-type"] == "application/json"
    assert res.headers["www-authenticate"] == "Bearer"
    [sent] = tracker.requests
    assert (sent.method, sent.path, sent.query, sent.body) == (
        "POST",
        "/api/time-entries/auto",
        "dry=1",
        b'{"entries": []}',
    )
    assert sent.headers["authorization"] == f"Bearer {token}"
    [line] = relay_log.lines
    assert (line.method, line.route, line.client_id, line.status_code) == (
        "POST",
        "/api/time-entries/auto",
        "wintrack-app",
        201,
    )


@pytest.mark.parametrize(
    ("path", "route"),
    [
        ("/api/time-entries/current", "/api/time-entries/current"),
        (
            "/api/time-entries?start=2026-10-19T00:00:00Z&end=2026-10-20T00:00:00Z",
            "/api/time-entries",
        ),
        ("/api/breaks?start=2026-10-19T00:00:00Z&end=2026-10-20T00:00:00Z", "/api/breaks"),
        (
            "/api/pc-activity?start=2026-10-19T00:00:00Z&end=2026-10-20T00:00:00Z",
            "/api/pc-activity",
        ),
        ("/api/tracking-rules", "/api/tracking-rules"),
        ("/api/tracking-rules/tasks", "/api/tracking-rules/tasks"),
    ],
)
def test_the_apps_reads_are_relayed_too(make_client, relay_log, path, route) -> None:
    client = make_client(forward=True)
    tracker: FakeTracker = client.app.state.tracker_relay
    tracker.answer = RelayedResponse(200, {"content-type": "application/json"}, b"[]")

    res = client.get(path, headers=_bearer("wbstimer-app"))

    assert (res.status_code, res.content) == (200, b"[]")
    assert [r.path for r in tracker.requests] == [path.split("?")[0]]
    [line] = relay_log.lines
    assert (line.route, line.client_id) == (route, "wbstimer-app")


def test_the_log_hides_ids_and_days_so_routes_can_be_counted(make_client, relay_log) -> None:
    client = make_client(forward=True)
    client.patch("/api/time-entries/42", json={}, headers=_bearer())
    client.put(f"/api/breaks/auto/{DAY}", json={}, headers=_bearer())
    routes = [r.route for r in relay_log.lines]
    assert routes == ["/api/time-entries/{id}", "/api/breaks/auto/{day}"]


def test_tracker_errors_come_back_as_they_are(make_client) -> None:
    client = make_client(forward=True)
    tracker: FakeTracker = client.app.state.tracker_relay
    tracker.answer = RelayedResponse(401, {"content-type": "application/json"}, b'{"detail": "no"}')
    res = client.get("/api/time-entries/current", headers=_bearer())
    assert (res.status_code, res.json()) == (401, {"detail": "no"})


def test_when_tracker_does_not_answer_the_apps_get_a_5xx_and_keep_their_records(
    make_client,
) -> None:
    client = make_client(forward=True)
    client.app.state.tracker_relay.down = True
    res = client.post("/api/time-entries/auto", json={"entries": []}, headers=_bearer())
    assert res.status_code == 502
    assert res.json()["reason"] == "tracker_unreachable"


def test_after_the_move_the_screen_reads_no_tracking_rows(make_client) -> None:
    _seed(make_client())
    client = make_client(forward=True)
    assert client.get("/api/tracker-move").json() == {
        "mode": "moved",
        "url": "https://tracker.nolumia.com",
    }
    today = client.get("/api/today").json()
    assert (today["running"], today["entries"], today["actuals"], today["total_seconds"]) == (
        None,
        [],
        [],
        0,
    )
    periods = client.get("/api/actuals/periods").json()["periods"]
    assert all(
        p["tracked_task_seconds"] == 0 and p["tracked_off_task_seconds"] == 0 for p in periods
    )


def test_after_the_move_the_kept_routes_still_answer_from_wbs(make_client) -> None:
    client = make_client(forward=True)
    tracker: FakeTracker = client.app.state.tracker_relay
    # 予定のアラーム（段 2 で Scheduler へ）・App Links・WinTrack の更新の中継は WBS に残す
    assert client.get("/api/calendar/alarms", headers=_bearer("wbstimer-app")).status_code != 409
    assert client.get("/.well-known/assetlinks.json").status_code != 409
    assert client.get("/api/wintrack/releases/RELEASES", headers=_bearer()).status_code != 409
    assert client.post("/api/tasks", json={"title": "タスクは WBS"}).status_code == 201
    assert tracker.requests == []


def test_the_settings_are_read_from_the_environment(monkeypatch) -> None:
    for name in ("TRACKER_CUTOVER_HOLD", "TRACKER_FORWARD_URL", "TRACKER_PUBLIC_URL"):
        monkeypatch.delenv(name, raising=False)
    assert load_tracker_move_settings().phase.value == "off"

    monkeypatch.setenv("TRACKER_CUTOVER_HOLD", "true")
    monkeypatch.setenv("TRACKER_FORWARD_URL", FORWARD_URL + "/")
    monkeypatch.setenv("TRACKER_PUBLIC_URL", "https://tracker-stg.nolumia.com/")
    settings = load_tracker_move_settings()
    # 両方入っていれば 503 が先（書き込みは待たせる。Bearer の読みは中継）
    assert (settings.phase.value, settings.moved) == ("hold", True)
    assert settings.forward_url == FORWARD_URL
    assert settings.public_url == "https://tracker-stg.nolumia.com"

    monkeypatch.setenv("TRACKER_CUTOVER_HOLD", "false")
    assert load_tracker_move_settings().phase.value == "moved"
