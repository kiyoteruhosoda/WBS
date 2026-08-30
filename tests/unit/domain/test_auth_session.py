from datetime import datetime, timedelta

from src.domain.entities.auth_session import AuthSession, hash_session_token

NOW = datetime(2026, 8, 30, 12, 0, 0)


def test_raw_token_is_never_stored() -> None:
    session = AuthSession.issue(user_id=1, token="super-secret", now=NOW)
    assert "super-secret" not in session.token_hash
    assert session.token_hash == hash_session_token("super-secret")


def test_matches_only_the_issued_token() -> None:
    session = AuthSession.issue(user_id=1, token="super-secret", now=NOW)
    assert session.matches("super-secret")
    assert not session.matches("super-secre")


def test_expires_after_the_ttl() -> None:
    session = AuthSession.issue(user_id=1, token="t", now=NOW, ttl=timedelta(hours=1))
    assert not session.is_expired(NOW + timedelta(minutes=59))
    # 期限ちょうどは切れている側に倒す
    assert session.is_expired(NOW + timedelta(hours=1))


def test_touch_records_last_seen() -> None:
    session = AuthSession.issue(user_id=1, token="t", now=NOW)
    session.touch(NOW + timedelta(minutes=5))
    assert session.last_seen_at == NOW + timedelta(minutes=5)
    # 最終利用の記録が期限を延ばしてはいけない（絶対期限で切る）
    assert session.expires_at == NOW + timedelta(hours=12)
