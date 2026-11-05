"""ログインごとの控え（ADR-0069 決定 3・ADR-0071）。

行が無ければそのログインは終わっている。停止の通知・定期照合・ログアウトは行を消し、
設定の保存でアクセストークンを出し直すときに行があるかを見る。

⚠ **リフレッシュトークンはもう出さない**（ADR-0071）。SSO で入ったログインはアクセストークン（5 分）だけを持ち、
切れたら画面が見えない枠で IdP へ問い合わせて続ける。続けるたびにこの行の期限を延ばす。
表の名前（``refresh_sessions``）は ADR-0069 のときのまま残す。
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime


def new_identifier() -> str:
    """控えの番号（列は 32 文字）。"""
    return secrets.token_hex(16)


@dataclass
class RefreshSession:
    id: str
    user_id: int
    expires_at: datetime
    created_at: datetime
    #: このログインを始めた（最後に続けた）IdP 側のログイン（ID トークンの ``sid``）。
    #: ⚠ ``sid`` を出さない IdP では ``None`` になり、停止の通知は**利用者単位**でしか
    #: 効かせられない（その人のログインがまとめて終わる）。
    idp_session_id: str | None = None

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at
