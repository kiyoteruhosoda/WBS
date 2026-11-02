"""ログインごとの控えの決まり（ADR-0069）。"""

from datetime import datetime, timedelta

from src.domain.entities.refresh_session import REUSE_GRACE, RefreshSession, RefreshStanding

NOW = datetime(2026, 11, 2, 12, 0, 0)


def _session(**overrides) -> RefreshSession:
    return RefreshSession(
        **{
            "id": "s",
            "user_id": 1,
            "current_jti": "now",
            "previous_jti": "before",
            "rotated_at": NOW,
            "expires_at": NOW + timedelta(days=14),
            "created_at": NOW,
            **overrides,
        }
    )


def test_the_current_token_stands() -> None:
    assert _session().standing_of("now", NOW) is RefreshStanding.CURRENT


def test_the_previous_token_stands_within_the_grace() -> None:
    assert _session().standing_of("before", NOW + REUSE_GRACE) is RefreshStanding.JUST_ROTATED


def test_the_previous_token_is_reuse_after_the_grace() -> None:
    after = NOW + REUSE_GRACE + timedelta(seconds=1)
    assert _session().standing_of("before", after) is RefreshStanding.REUSED


def test_any_other_token_is_reuse() -> None:
    assert _session().standing_of("older", NOW) is RefreshStanding.REUSED


def test_a_session_that_never_rotated_has_no_previous_token() -> None:
    session = _session(previous_jti=None, rotated_at=None)
    assert session.standing_of("before", NOW) is RefreshStanding.REUSED


def test_expiry() -> None:
    session = _session(expires_at=NOW)
    assert session.is_expired(NOW)
    assert not session.is_expired(NOW - timedelta(seconds=1))
