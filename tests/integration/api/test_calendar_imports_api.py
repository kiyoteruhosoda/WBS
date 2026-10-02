"""取り込んだカレンダー（task #196、ADR-0037）。

- ファイルか URL（1 回だけ・購読）を読んで、読み取り専用のカレンダーを作る。読めなければ作らない
- 取り込んだ回は ``/calendars/imported-occurrences`` だけに出る（予定の回の一覧・計画・締めには入らない）
- 取り込んだカレンダーには WBS の予定を入れられない
- 購読しない URL は保存しない。購読する URL は封じて保存し、手掛かりだけを返す
- 読み込み直すと丸ごと入れ替わる。購読の失敗は理由を覚え、中身は前のまま
- 消すと回と読み込みの状態も消える

URL を読む口は試験用の偽物に差し替える（外へは出ない）。利用者は Asia/Tokyo。回は今日からの相対で作る。
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

import pytest
from sqlalchemy import text

from src.application.ports.calendar_feed import CalendarFeedError, FeedFailure, NoFeedUrlCipher
from src.infrastructure.calendar_feed.url_cipher import AesGcmFeedUrlCipher
from src.infrastructure.database.models import UserModel
from src.presentation.api.dependencies import build_calendar_import_use_cases, get_db
from src.shared.clock import utcnow

FEED_URL = "https://calendar.example.com/calendar/ical/me/private-0123456789abcdef/basic.ics"
TODAY = utcnow().date()


def _day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).strftime("%Y%m%d")


def _iso(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


def _ics(*events: str) -> str:
    return "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n" + "".join(events) + "END:VCALENDAR\r\n"


def _timed(uid: str, title: str, offset: int, hhmm_utc: str = "010000") -> str:
    return (
        f"BEGIN:VEVENT\r\nUID:{uid}\r\nSUMMARY:{title}\r\n"
        f"DTSTART:{_day(offset)}T{hhmm_utc}Z\r\nDTEND:{_day(offset)}T020000Z\r\nEND:VEVENT\r\n"
    )


def _all_day(uid: str, title: str, offset: int, days: int) -> str:
    return (
        f"BEGIN:VEVENT\r\nUID:{uid}\r\nSUMMARY:{title}\r\n"
        f"DTSTART;VALUE=DATE:{_day(offset)}\r\nDTEND;VALUE=DATE:{_day(offset + days)}\r\nEND:VEVENT\r\n"
    )


TWO_EVENTS = _ics(_timed("a", "会議", 2), _all_day("b", "出張", 3, 2))


class FakeFetcher:
    """URL ごとの中身を返す。無い URL・``failure`` を置いた URL は読めない。"""

    def __init__(self) -> None:
        self.contents: dict[str, str] = {}
        self.failures: dict[str, FeedFailure] = {}
        self.calls: list[str] = []

    def fetch(self, url: str) -> bytes:
        self.calls.append(url)
        if url in self.failures:
            raise CalendarFeedError(self.failures[url])
        if url not in self.contents:
            raise CalendarFeedError(FeedFailure.NOT_FOUND)
        return self.contents[url].encode("utf-8")


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
def fetcher(client) -> FakeFetcher:
    fake = FakeFetcher()
    client.app.state.calendar_feed_fetcher = fake
    client.app.state.calendar_feed_cipher = AesGcmFeedUrlCipher(bytes(range(32)))
    return fake


def _create(client, source: dict, name: str = "会社の予定"):
    return client.post(
        "/api/calendars/imported", json={"name": name, "color_key": "GRAPE", "source": source}
    )


def _file(content: str = TWO_EVENTS) -> dict:
    return {"type": "FILE", "content": content}


def _imported(client, offset_from: int = 0, offset_to: int = 10) -> list[dict]:
    res = client.get(
        "/api/calendars/imported-occurrences",
        params={"from": _iso(offset_from), "to": _iso(offset_to), "time_zone": "Asia/Tokyo"},
    )
    assert res.status_code == 200, res.text
    return res.json()


def _sealed_urls(db) -> list[str | None]:
    return [row[0] for row in db.execute(text("SELECT feed_url_sealed FROM calendar_imports"))]


def test_a_file_becomes_a_read_only_calendar(client, fetcher) -> None:
    res = _create(client, _file())
    assert res.status_code == 201, res.text
    calendar = res.json()
    assert calendar["kind"] == "IMPORTED" and calendar["is_visible"] is True
    status = calendar["imported"]
    assert status["source"] == "FILE" and status["event_count"] == 2
    assert status["is_subscribed"] is False and status["url_hint"] is None
    listed = {c["id"]: c for c in client.get("/api/calendars").json()}
    assert listed[calendar["id"]]["imported"]["event_count"] == 2

    occurrences = _imported(client)
    meeting = next(o for o in occurrences if o["title"] == "会議")
    # 01:00Z は東京の 10:00、長さ 60 分
    assert (meeting["date"], meeting["start_time"], meeting["duration_minutes"]) == (_iso(2), "10:00", 60)
    assert meeting["calendar_id"] == calendar["id"] and meeting["calendar_color_key"] == "GRAPE"
    trip = [o for o in occurrences if o["title"] == "出張"]
    assert [o["date"] for o in trip] == [_iso(3), _iso(4)] and all(o["is_all_day"] for o in trip)
    assert fetcher.calls == []

    # 予定の回の一覧には出ない（計画・締め・打刻はこちらを見る）
    planned = client.get(
        "/api/calendar/occurrences", params={"from": _iso(0), "to": _iso(10), "time_zone": "Asia/Tokyo"}
    ).json()
    assert {o["title"] for o in planned}.isdisjoint({"会議", "出張"})


def test_events_cannot_be_put_into_an_imported_calendar(client, fetcher) -> None:
    calendar = _create(client, _file()).json()
    res = client.post(
        "/api/calendar/events",
        json={
            "title": "入れたい", "start": f"{_iso(2)}T03:00:00Z", "duration_minutes": 30,
            "calendar_id": calendar["id"],
        },
    )
    assert res.status_code == 422, res.text


def test_unreadable_content_creates_nothing(client, fetcher) -> None:
    before = len(client.get("/api/calendars").json())
    res = _create(client, _file("<html>sign in</html>"))
    assert res.status_code == 422 and res.json()["reason"] == "not_icalendar"
    res = _create(client, {"type": "URL", "url": "https://calendar.example.com/missing.ics"})
    assert res.status_code == 422 and res.json()["reason"] == "not_found"
    assert len(client.get("/api/calendars").json()) == before


def test_a_url_read_once_is_not_kept(client, fetcher, db) -> None:
    fetcher.contents[FEED_URL] = TWO_EVENTS
    res = _create(client, {"type": "URL", "url": FEED_URL, "subscribe": False})
    assert res.status_code == 201, res.text
    calendar = res.json()
    assert calendar["imported"]["source"] == "URL" and calendar["imported"]["is_subscribed"] is False
    assert _sealed_urls(db) == [None]
    assert client.post(f"/api/calendars/{calendar['id']}/refresh").status_code == 409


def test_a_subscription_keeps_only_a_sealed_url_and_reads_again(client, fetcher, db) -> None:
    fetcher.contents[FEED_URL] = TWO_EVENTS
    calendar = _create(client, {"type": "URL", "url": FEED_URL, "subscribe": True}).json()
    status = calendar["imported"]
    assert status["is_subscribed"] is True
    assert status["url_hint"] == "calendar.example.com …/basic.ics"
    [sealed] = _sealed_urls(db)
    assert sealed is not None and "private-0123456789abcdef" not in sealed
    assert "private-0123456789abcdef" not in client.get("/api/calendars").text

    # 中身が変わったら今すぐ読み込み直せる（丸ごと入れ替わる）
    fetcher.contents[FEED_URL] = _ics(_timed("c", "新しい会議", 5))
    res = client.post(f"/api/calendars/{calendar['id']}/refresh")
    assert res.status_code == 200 and res.json()["event_count"] == 1
    assert [o["title"] for o in _imported(client)] == ["新しい会議"]

    # 読めなければ理由を覚え、中身は前のまま
    fetcher.failures[FEED_URL] = FeedFailure.FORBIDDEN
    res = client.post(f"/api/calendars/{calendar['id']}/refresh")
    assert res.status_code == 422 and res.json()["reason"] == "forbidden"
    listed = {c["id"]: c for c in client.get("/api/calendars").json()}
    assert listed[calendar["id"]]["imported"]["last_error"] == "forbidden"
    assert [o["title"] for o in _imported(client)] == ["新しい会議"]

    # 購読をやめると URL を忘れる（回は残す）
    res = client.delete(f"/api/calendars/{calendar['id']}/subscription")
    assert res.status_code == 200 and res.json()["is_subscribed"] is False
    assert _sealed_urls(db) == [None]
    assert [o["title"] for o in _imported(client)] == ["新しい会議"]


def test_reimporting_a_file_replaces_and_stops_the_subscription(client, fetcher, db) -> None:
    fetcher.contents[FEED_URL] = TWO_EVENTS
    calendar = _create(client, {"type": "URL", "url": FEED_URL, "subscribe": True}).json()
    res = client.post(
        f"/api/calendars/{calendar['id']}/import", json=_file(_ics(_timed("d", "ファイルの会議", 1)))
    )
    assert res.status_code == 200, res.text
    assert res.json()["source"] == "FILE" and res.json()["is_subscribed"] is False
    assert _sealed_urls(db) == [None]
    assert [o["title"] for o in _imported(client)] == ["ファイルの会議"]


def test_only_an_imported_calendar_can_be_read_into(client, fetcher) -> None:
    own = client.post("/api/calendars", json={"name": "手で作った"}).json()
    res = client.post(f"/api/calendars/{own['id']}/import", json=_file())
    assert res.status_code == 422


def test_without_a_key_a_url_can_be_read_once_but_not_subscribed(client, fetcher) -> None:
    client.app.state.calendar_feed_cipher = NoFeedUrlCipher()
    fetcher.contents[FEED_URL] = TWO_EVENTS
    assert client.get("/api/calendars/import-settings").json() == {
        "subscription_available": False, "refresh_interval_minutes": 15,
    }
    before = len(client.get("/api/calendars").json())
    res = _create(client, {"type": "URL", "url": FEED_URL, "subscribe": True})
    assert res.status_code == 422 and res.json()["reason"] == "subscription_unavailable"
    assert fetcher.calls == []
    assert len(client.get("/api/calendars").json()) == before
    assert _create(client, {"type": "URL", "url": FEED_URL}).status_code == 201


def test_deleting_removes_the_occurrences_and_the_state(client, fetcher, db) -> None:
    fetcher.contents[FEED_URL] = TWO_EVENTS
    calendar = _create(client, {"type": "URL", "url": FEED_URL, "subscribe": True}).json()
    res = client.delete(f"/api/calendars/{calendar['id']}")
    assert res.status_code == 200 and res.json()["moved_event_count"] == 0
    assert _imported(client) == []
    assert db.execute(text("SELECT COUNT(*) FROM calendar_imports")).scalar() == 0
    assert db.execute(text("SELECT COUNT(*) FROM calendar_imported_occurrences")).scalar() == 0


def test_due_subscriptions_are_read_again(client, fetcher, db) -> None:
    fetcher.contents[FEED_URL] = TWO_EVENTS
    calendar = _create(client, {"type": "URL", "url": FEED_URL, "subscribe": True}).json()
    imports = build_calendar_import_use_cases(
        db, client.app.state.calendar_feed_fetcher, client.app.state.calendar_feed_cipher
    )
    # 読んだばかりなので、まだ間隔が来ていない
    assert imports.refresh_due_subscriptions() == 0
    db.execute(
        text("UPDATE calendar_imports SET last_attempt_at = :at"),
        {"at": utcnow() - timedelta(minutes=20)},
    )
    db.commit()
    fetcher.contents[FEED_URL] = _ics(_timed("e", "定期で読んだ会議", 3))
    assert imports.refresh_due_subscriptions() == 1
    assert [o["title"] for o in _imported(client)] == ["定期で読んだ会議"]
    listed = {c["id"]: c for c in client.get("/api/calendars").json()}
    assert listed[calendar["id"]]["imported"]["event_count"] == 1
