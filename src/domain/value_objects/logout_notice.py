"""IdP から届いた「このセッションを止めろ」（OpenID Connect Back-Channel Logout 1.0）。

``logout_token`` の**署名・発行者・対象者・有効期限**を確かめるのはインフラ層
（JWT の話なので）。ここが見るのは**それ以外の 4 つ**で、どれも仕様が明示的に
求めているものである（§2.6）。

- ``events`` に back-channel logout のイベントが入っていること
  ——入っていない JWT は「ログアウトの通知」ではない
- ``nonce`` が**入っていない**こと ——入っているものは ID トークンであり、
  それを受け付けると**手元の ID トークンを投げ返すだけでログアウトを起こせる**
- ``sub`` か ``sid`` のどちらかがあること ——どちらも無ければ誰を止めるのか決まらない
- ``jti`` があること ——再送を弾く鍵になる（同じ通知の再送では同じ ``jti`` が来る）
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.domain.exceptions import AuthenticationError
from src.domain.value_objects.federated_identity import FederatedIdentity

#: back-channel logout のイベント名（OpenID Connect Back-Channel Logout 1.0 §2.4）。
LOGOUT_EVENT = "http://schemas.openid.net/event/backchannel-logout"


class InvalidLogoutTokenError(AuthenticationError):
    """``logout_token`` が「ログアウトの通知」として成立していない。

    ⚠ **理由を送り手へ返さない。** この口は未認証で叩けるので、どこまで通ったかを
    教えると、通る形を探す手掛かりになる。
    """


@dataclass(frozen=True)
class LogoutNotice:
    """検証を通った通知。``jti`` は配送の identity で、再送でも変わらない。"""

    jti: str
    identity: FederatedIdentity | None
    session_id: str | None

    @classmethod
    def from_claims(cls, claims: Mapping[str, Any], *, issuer: str) -> LogoutNotice:
        """検証済みのクレームから組み立てる。成立しないものは例外にする。"""
        _ensure_logout_event(claims)
        _ensure_not_an_id_token(claims)
        jti = _text(claims.get("jti"))
        if not jti:
            raise InvalidLogoutTokenError("logout_token has no jti")
        subject = _text(claims.get("sub"))
        session_id = _text(claims.get("sid"))
        if not subject and not session_id:
            # どちらも無ければ「誰の」「どのログインを」止めるのか決まらない。
            raise InvalidLogoutTokenError("logout_token has neither sub nor sid")
        return cls(
            jti=jti,
            identity=FederatedIdentity(issuer=issuer, subject=subject) if subject else None,
            session_id=session_id or None,
        )

    @property
    def scope(self) -> str:
        """記録に出す「どこまで止める通知か」。``sid`` があればその 1 ログインだけ。"""
        return "session" if self.session_id else "subject"


def _ensure_logout_event(claims: Mapping[str, Any]) -> None:
    events = claims.get("events")
    if not isinstance(events, Mapping) or LOGOUT_EVENT not in events:
        raise InvalidLogoutTokenError("logout_token does not carry the logout event")


def _ensure_not_an_id_token(claims: Mapping[str, Any]) -> None:
    """``nonce`` を持つものは受け取らない（仕様が MUST NOT としている）。

    ID トークンと logout token は署名鍵も発行者も対象者も同じなので、**この 1 点だけ**が
    両者を分ける。落とすと、正規に受け取った ID トークンを送り返すだけで
    他人のセッションを落とせる。
    """
    if "nonce" in claims:
        raise InvalidLogoutTokenError("a logout_token must not carry a nonce")


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


__all__ = ["LOGOUT_EVENT", "InvalidLogoutTokenError", "LogoutNotice"]
