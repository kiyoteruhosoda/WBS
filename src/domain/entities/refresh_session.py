"""ログインごとの控え（ADR-0069。fastapitemplate の ADR-0091・ADR-0092 と同じ仕組み）。

リフレッシュトークンの振り替えと、使い回しの見分けの決まりをここに置く。

- **今の 1 本**（``current_jti``）だけが新しいトークン対を受け取れる。ただし前の振り替えから
  :data:`REUSE_GRACE` が過ぎるまでは振り替えず、アクセストークンだけを受け取る
- **直前の 1 本**（``previous_jti``）は振り替えから :data:`REUSE_GRACE` のあいだだけ、
  アクセストークンだけを受け取れる。タブが同時に更新したときの負けた側で、Cookie は勝った側のものを残す
- **それ以外**は使い回し。そのログインだけを終わらせる（ほかの端末は巻き込まない）
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

#: 振り替えの間隔と、直前の 1 本を受け付ける長さ。ほかのタブの更新が同時に走る幅で足りる
REUSE_GRACE = timedelta(seconds=30)


class RefreshStanding(StrEnum):
    CURRENT = "current"
    JUST_ROTATED = "just_rotated"
    REUSED = "reused"


def new_identifier() -> str:
    """控えの番号とトークンの ``jti``（列は 32 文字）。"""
    return secrets.token_hex(16)


@dataclass
class RefreshSession:
    id: str
    user_id: int
    current_jti: str
    expires_at: datetime
    created_at: datetime
    previous_jti: str | None = None
    rotated_at: datetime | None = None
    #: このログインを始めた IdP 側のログイン（ID トークンの ``sid``）。
    #: ⚠ ``sid`` を出さない IdP では ``None`` になり、停止の通知は**利用者単位**でしか
    #: 効かせられない（その人のログインがまとめて終わる）。
    idp_session_id: str | None = None

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at

    def standing_of(self, jti: str, now: datetime) -> RefreshStanding:
        if jti == self.current_jti:
            return RefreshStanding.CURRENT
        if (
            jti == self.previous_jti
            and self.rotated_at is not None
            and now - self.rotated_at <= REUSE_GRACE
        ):
            return RefreshStanding.JUST_ROTATED
        return RefreshStanding.REUSED
