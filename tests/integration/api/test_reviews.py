"""週次レビューの「今週」は利用者のタイムゾーンで決まる（HANDOVER §14）。

サーバは UTC で動くので、UTC の「今」から週を求めると JST の利用者にとっては
月曜の 0:00〜9:00 のあいだだけ**前の週**が開く。同じ応答のなかの
`overdue_count` は利用者の日付を見ているので、週と日でずれた数字が並ぶ。
"""

from datetime import UTC, datetime

import pytest

# 2026-08-30 15:30 UTC = 2026-08-31 00:30 JST（月曜）。
# UTC 基準なら 2026-W35（月曜 08-24）、JST 基準なら 2026-W36（月曜 08-31）。
_MONDAY_EARLY_MORNING_IN_JST = datetime(2026, 8, 30, 15, 30, tzinfo=UTC)


@pytest.fixture
def frozen_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.application.user_clock.utcnow",
        lambda: _MONDAY_EARLY_MORNING_IN_JST,
    )


def test_weekly_review_defaults_to_the_users_week(client, frozen_now) -> None:
    data = client.get("/api/reviews/weekly").json()

    # 既定のユーザーのタイムゾーンは Asia/Tokyo
    assert data["week"] == "2026-W36"
    assert data["monday"] == "2026-08-31"
    assert data["sunday"] == "2026-09-06"


def test_weekly_review_honours_an_explicit_week(client, frozen_now) -> None:
    data = client.get("/api/reviews/weekly", params={"week": "2026-W35"}).json()

    assert data["week"] == "2026-W35"
    assert data["monday"] == "2026-08-24"
