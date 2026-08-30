"""ログイン後のセッション。"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta

DEFAULT_SESSION_TTL = timedelta(hours=12)


def hash_session_token(token: str) -> str:
    """セッショントークンの保存形。

    生のトークンは Cookie として利用者のブラウザにしかない。DB へは SHA-256 の
    ハッシュだけを置く（DB が漏れてもセッションを再現できないようにする）。
    トークン自体が十分な乱数なので、パスワードのようなストレッチは要らない。
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass
class AuthSession:
    user_id: int
    token_hash: str
    issued_at: datetime
    expires_at: datetime
    last_seen_at: datetime
    id: int | None = None

    @classmethod
    def issue(
        cls,
        *,
        user_id: int,
        token: str,
        now: datetime,
        ttl: timedelta = DEFAULT_SESSION_TTL,
    ) -> AuthSession:
        return cls(
            user_id=user_id,
            token_hash=hash_session_token(token),
            issued_at=now,
            expires_at=now + ttl,
            last_seen_at=now,
        )

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def matches(self, token: str) -> bool:
        return hmac.compare_digest(self.token_hash, hash_session_token(token))

    def touch(self, now: datetime) -> None:
        self.last_seen_at = now
