"""Tracker・Scheduler へ移した口と「今日」・週次レビューの口は無い（task #543 AC2 / ADR-0070）。

移転モードの中継（ADR-0053・0054）も外したので、Bearer で来ても中継せず 404。
"""

from __future__ import annotations

import pytest

GONE = [
    # 打刻まわり（Tracker の ADR-0053）
    ("get", "/api/time-entries"),
    ("get", "/api/time-entries/current"),
    ("post", "/api/time-entries/start"),
    ("post", "/api/time-entries/stop"),
    ("post", "/api/time-entries/auto"),
    ("patch", "/api/time-entries/1"),
    ("get", "/api/breaks"),
    ("put", "/api/breaks/auto/2026-11-03"),
    ("get", "/api/pc-activity"),
    ("put", "/api/pc-activity/2026-11-03"),
    ("get", "/api/tracking-rules"),
    ("get", "/api/tracking-rules/tasks"),
    ("get", "/api/closing-periods"),
    ("post", "/api/closing-periods/2026-09-01/close"),
    ("get", "/api/wintrack/releases/RELEASES"),
    # 予定まわり（Scheduler の ADR-0054）
    ("get", "/api/calendar/events"),
    ("post", "/api/calendar/events"),
    ("get", "/api/calendar/alarms"),
    ("get", "/api/calendars"),
    ("get", "/api/calendar-view-presets"),
    # 端末への通知（Web Push）
    ("get", "/api/push/settings"),
    ("post", "/api/push/subscriptions"),
    # 移転モードの状態
    ("get", "/api/tracker-move"),
    ("get", "/api/scheduler-move"),
    # 「今日」と週次レビュー
    ("get", "/api/today"),
    ("get", "/api/reviews/weekly"),
    # 打刻アプリのログインの戻り先と App Links（wbstimer は Tracker へ移った）
    ("get", "/.well-known/assetlinks.json"),
]


@pytest.mark.parametrize(("method", "path"), GONE)
def test_moved_routes_are_not_found(client, method: str, path: str) -> None:
    assert client.request(method, path, json={}).status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", "/api/time-entries/current"), ("get", "/api/calendar/alarms")],
)
def test_bearer_requests_are_not_relayed_any_more(client, method: str, path: str) -> None:
    res = client.request(method, path, headers={"Authorization": "Bearer anything"})
    assert res.status_code == 404


def test_the_project_routes_stay(client) -> None:
    for path in ("/api/tasks", "/api/gantt", "/api/actuals/tasks", "/api/projects"):
        assert client.get(path).status_code == 200, path
