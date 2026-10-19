"""Scheduler の api へ中継する HTTP の係（task #535 / WBS の ADR-0054）。渡すもの・返すものを決めたものだけにする。"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from src.application.ports.scheduler_relay import SchedulerRelayRequest, SchedulerUnreachableError
from src.infrastructure.scheduler_move.http_scheduler_relay import HttpSchedulerRelay

BASE = "http://api.scheduler-test.svc.cluster.local:8000"
ALARMS = "/api/calendar/alarms"


def _relay(handler) -> HttpSchedulerRelay:
    return HttpSchedulerRelay(BASE, transport=httpx.MockTransport(handler))


def test_the_token_goes_through_but_not_the_wbs_login() -> None:
    seen: list[httpx.Request] = []

    def scheduler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={"alarms": []},
            headers={"Set-Cookie": "scheduler=1", "WWW-Authenticate": "Bearer", "X-Internal": "no"},
        )

    answer = asyncio.run(
        _relay(scheduler).relay(
            SchedulerRelayRequest(
                method="GET",
                path=ALARMS,
                query="from=2026-10-05T00:00:00Z&to=2026-10-06T00:00:00Z",
                headers={
                    "authorization": "Bearer t0ken",
                    "accept": "application/json",
                    "cookie": "wbs_session=the-web-login",
                    "x-forwarded-for": "203.0.113.1",
                },
            )
        )
    )

    [request] = seen
    assert str(request.url) == (f"{BASE}{ALARMS}?from=2026-10-05T00:00:00Z&to=2026-10-06T00:00:00Z")
    assert request.headers["authorization"] == "Bearer t0ken"
    assert "cookie" not in request.headers
    assert "x-forwarded-for" not in request.headers
    assert answer.status_code == 200
    assert answer.body == b'{"alarms":[]}'
    assert answer.headers == {"content-type": "application/json", "www-authenticate": "Bearer"}


def test_redirects_are_returned_not_followed() -> None:
    relay = _relay(lambda request: httpx.Response(307, headers={"Location": "/elsewhere"}))
    answer = asyncio.run(relay.relay(SchedulerRelayRequest("GET", ALARMS, "", {})))
    assert (answer.status_code, answer.headers["location"]) == (307, "/elsewhere")


def test_an_unreachable_scheduler_is_reported() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(SchedulerUnreachableError):
        asyncio.run(_relay(refuse).relay(SchedulerRelayRequest("GET", ALARMS, "", {})))
