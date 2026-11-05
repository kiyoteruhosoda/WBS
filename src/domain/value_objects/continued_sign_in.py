"""画面を出さずに続けるログイン（ADR-0071）。

手元に残った期限切れのアクセストークンから読む「誰の・どのログインか」。⚠ **これは認証ではない。**
IdP から**同じ人**が戻ってきたときにだけ、その控えを引き継ぐために使う。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContinuedSignIn:
    user_id: int
    #: 続けるログインの控え（``refresh_sessions.id``）
    session_id: str
