"""認可コードフロー 1 回分の往復を覚えておくためのエンティティ。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from src.domain.exceptions import ValidationError
from src.domain.value_objects.redirect_target import RedirectTarget

DEFAULT_LOGIN_TRANSACTION_TTL = timedelta(minutes=10)


@dataclass
class LoginTransaction:
    """``/auth/login`` で作り ``/auth/callback`` で使い切る一時データ。

    - ``state``: コールバックが自分の出した要求への返答かを確かめる（CSRF 対策）
    - ``nonce``: ID トークンが自分の要求に対して発行されたものかを確かめる（リプレイ対策）
    - ``code_verifier``: PKCE。認可コードを盗まれても交換できないようにする

    ブラウザのセッションではなくサーバ側に置くのは、コールバックが別タブ・別
    プロセスへ戻ることがあるため。使ったら必ず消す（同じコードの再送を通さない）。
    """

    state: str
    nonce: str
    code_verifier: str
    redirect_target: RedirectTarget
    created_at: datetime
    expires_at: datetime
    id: int | None = None

    @classmethod
    def issue(
        cls,
        *,
        state: str,
        nonce: str,
        code_verifier: str,
        redirect_target: RedirectTarget,
        now: datetime,
        ttl: timedelta = DEFAULT_LOGIN_TRANSACTION_TTL,
    ) -> LoginTransaction:
        if not state or not nonce or not code_verifier:
            raise ValidationError("state, nonce and code_verifier are required")
        return cls(
            state=state,
            nonce=nonce,
            code_verifier=code_verifier,
            redirect_target=redirect_target,
            created_at=now,
            expires_at=now + ttl,
        )

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at
