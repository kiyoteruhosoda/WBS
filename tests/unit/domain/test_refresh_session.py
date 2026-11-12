"""Rules for the per-sign-in record (ADR-0069, ADR-0071)."""

from datetime import datetime, timedelta

from src.domain.entities.refresh_session import RefreshSession, new_identifier

NOW = datetime(2026, 11, 2, 12, 0, 0)


def _session() -> RefreshSession:
    return RefreshSession(id="s", user_id=1, expires_at=NOW + timedelta(days=30), created_at=NOW)


def test_a_sign_in_lives_until_its_expiry() -> None:
    assert not _session().is_expired(NOW + timedelta(days=29))
    assert _session().is_expired(NOW + timedelta(days=30))


def test_identifiers_fit_the_column() -> None:
    assert len(new_identifier()) == 32
