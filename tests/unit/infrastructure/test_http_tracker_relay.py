"""Tracker の api へ中継する HTTP の係（task #526 / ADR-0053）。渡すもの・返すものを決めたものだけにする。"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from src.application.ports.tracker_relay import RelayRequest, TrackerUnreachableError
from src.infrastructure.tracker_move.http_tracker_relay import HttpTrackerRelay

BASE = "http://api.tracker-test.svc.cluster.local:8000"


def _relay(handler) -> HttpTrackerRelay:
    return HttpTrackerRelay(BASE, transport=httpx.MockTransport(handler))


def test_the_token_and_body_go_through_but_not_the_wbs_login() -> None:
    seen: list[httpx.Request] = []

    def tracker(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            201,
            json={"results": []},
            headers={"Set-Cookie": "tracker=1", "WWW-Authenticate": "Bearer", "X-Internal": "no"},
        )

    relay = _relay(tracker)
    answer = asyncio.run(
        relay.relay(
            RelayRequest(
                method="POST",
                path="/api/time-entries/auto",
                query="a=1",
                headers={
                    "authorization": "Bearer t0ken",
                    "content-type": "application/json",
                    "cookie": "wbs_session=the-web-login",
                    "x-forwarded-for": "203.0.113.1",
                },
                body=b'{"entries": []}',
            )
        )
    )

    [request] = seen
    assert str(request.url) == f"{BASE}/api/time-entries/auto?a=1"
    assert request.headers["authorization"] == "Bearer t0ken"
    assert request.content == b'{"entries": []}'
    assert "cookie" not in request.headers
    assert "x-forwarded-for" not in request.headers
    assert answer.status_code == 201
    assert answer.body == b'{"results":[]}'
    assert answer.headers == {"content-type": "application/json", "www-authenticate": "Bearer"}


def test_redirects_are_returned_not_followed() -> None:
    relay = _relay(lambda request: httpx.Response(307, headers={"Location": "/elsewhere"}))
    answer = asyncio.run(relay.relay(RelayRequest("GET", "/api/tracking-rules", "", {})))
    assert (answer.status_code, answer.headers["location"]) == (307, "/elsewhere")


def test_an_unreachable_tracker_is_reported() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(TrackerUnreachableError):
        asyncio.run(_relay(refuse).relay(RelayRequest("GET", "/api/time-entries/current", "", {})))
