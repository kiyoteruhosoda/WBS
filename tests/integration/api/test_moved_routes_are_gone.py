"""Routes moved to Tracker and Scheduler, and the "Today" and weekly review routes, are gone (task #543 AC2 / ADR-0070).

The relocation-mode relay (ADR-0053, 0054) was removed too, so even with a Bearer token nothing is relayed: 404.
"""

from __future__ import annotations

import pytest

GONE = [
    # Time tracking (Tracker's ADR-0053)
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
    # Schedules (Scheduler's ADR-0054)
    ("get", "/api/calendar/events"),
    ("post", "/api/calendar/events"),
    ("get", "/api/calendar/alarms"),
    ("get", "/api/calendars"),
    ("get", "/api/calendar-view-presets"),
    # Device notifications (Web Push)
    ("get", "/api/push/settings"),
    ("post", "/api/push/subscriptions"),
    # Relocation-mode status
    ("get", "/api/tracker-move"),
    ("get", "/api/scheduler-move"),
    # "Today" and weekly review
    ("get", "/api/today"),
    ("get", "/api/reviews/weekly"),
    # Time-tracking app sign-in return URL and App Links (wbstimer moved to Tracker)
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
