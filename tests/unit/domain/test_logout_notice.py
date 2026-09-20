"""停止の通知が「ログアウトの通知として成立しているか」の判断。

署名・発行者・対象者・期限の検証はインフラ層（JWT の話）。ここが見るのは
**それ以外の 4 つ**で、どれも落とすと実害が出る。
"""

import pytest

from src.domain.value_objects.logout_notice import (
    LOGOUT_EVENT,
    InvalidLogoutTokenError,
    LogoutNotice,
)

ISSUER = "https://idp.example.com/realms/wbs"


def claims(**overrides):
    base = {"sub": "taro", "jti": "delivery-1", "events": {LOGOUT_EVENT: {}}}
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not None}


def test_a_notice_with_a_subject_addresses_that_person() -> None:
    notice = LogoutNotice.from_claims(claims(), issuer=ISSUER)
    assert notice.identity is not None
    assert (notice.identity.issuer, notice.identity.subject) == (ISSUER, "taro")
    assert notice.session_id is None
    assert notice.scope == "subject"


def test_a_notice_with_a_sid_addresses_one_login() -> None:
    notice = LogoutNotice.from_claims(claims(sid="taro-session"), issuer=ISSUER)
    assert notice.session_id == "taro-session"
    assert notice.scope == "session"


def test_a_sid_alone_is_a_valid_address() -> None:
    """仕様は ``sub`` か ``sid`` のどちらかで足りるとしている（§2.6）。"""
    notice = LogoutNotice.from_claims(claims(sub=None, sid="taro-session"), issuer=ISSUER)
    assert notice.identity is None
    assert notice.session_id == "taro-session"


def test_an_id_token_is_not_a_logout_notice() -> None:
    """⚠ **``nonce`` を持つものを受け取らない**（仕様が MUST NOT としている）。

    ID トークンと ``logout_token`` は署名鍵も発行者も対象者も同じなので、**この 1 点
    だけ**が両者を分ける。落とすと、正規に受け取った ID トークンを送り返すだけで
    他人のセッションを落とせる。
    """
    with pytest.raises(InvalidLogoutTokenError):
        LogoutNotice.from_claims(claims(nonce="n-1"), issuer=ISSUER)


@pytest.mark.parametrize(
    "broken",
    [
        {"events": None},  # イベントが無い＝ログアウトの通知ではない
        {"events": {"http://example.com/other": {}}},  # 別のイベント
        {"jti": None},  # 再送を弾く鍵が無い
        {"sub": None},  # sub も sid も無い（誰を止めるのか決まらない）
    ],
    ids=["no-events", "other-event", "no-jti", "no-address"],
)
def test_a_notice_that_does_not_stand_up_is_refused(broken) -> None:
    with pytest.raises(InvalidLogoutTokenError):
        LogoutNotice.from_claims(claims(**broken), issuer=ISSUER)


def test_the_issuer_spelling_comes_from_the_caller() -> None:
    """⚠ 宛名の発行者は**手元に残した綴り**で持つ（末尾の ``/`` は落ちる）。"""
    notice = LogoutNotice.from_claims(claims(), issuer=f"{ISSUER}/")
    assert notice.identity is not None
    assert notice.identity.issuer == ISSUER
