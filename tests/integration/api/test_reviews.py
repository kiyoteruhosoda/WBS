"""週次レビューの「今週」は利用者のタイムゾーンで決まる（HANDOVER §14）。

サーバは UTC で動くので、UTC の「今」から週を求めると JST の利用者にとっては
月曜の 0:00〜9:00 のあいだだけ**前の週**が開く。同じ応答のなかの
`overdue_count` は利用者の日付を見ているので、週と日でずれた数字が並ぶ。
"""

from datetime import datetime

import pytest

# 2026-08-30 15:30 UTC = 2026-08-31 00:30 JST（月曜）。
# UTC 基準なら 2026-W35（月曜 08-24）、JST 基準なら 2026-W36（月曜 08-31）。
_MONDAY_EARLY_MORNING_IN_JST = datetime(2026, 8, 30, 15, 30)  # naive な UTC（保存値と同じ形）


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


def test_a_task_finished_monday_morning_jst_counts_in_that_week(client, frozen_now) -> None:
    """週の区切りは利用者の日付、保存値は UTC。突き合わせは UTC の半開区間で行う。

    JST の月曜 8:00 に終えたタスクは UTC では日曜 23:00。利用者の日付をそのまま
    DATETIME 列と比べると、前の週にも今の週にも入らずどこからも数えられない。
    """
    import sqlalchemy as sa

    from src.infrastructure.database.models import TaskModel
    from src.presentation.api.dependencies import get_db

    task_id = client.post("/api/tasks", json={"title": "月曜の朝に終えた"}).json()["id"]
    db = next(client.app.dependency_overrides.get(get_db, get_db)())
    db.execute(
        sa.update(TaskModel)
        .where(TaskModel.id == task_id)
        .values(status="DONE", completed_at=datetime(2026, 8, 30, 23, 0))
    )
    db.commit()

    assert client.get("/api/reviews/weekly", params={"week": "2026-W36"}).json()["completed_count"] == 1
    assert client.get("/api/reviews/weekly", params={"week": "2026-W35"}).json()["completed_count"] == 0


def test_an_unreadable_week_is_rejected_rather_than_crashing(client) -> None:
    for bad in ("abc", "2026-W99", ""):
        assert client.get("/api/reviews/weekly", params={"week": bad}).status_code == 422, bad
