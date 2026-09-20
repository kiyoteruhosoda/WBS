"""``private_key_jwt`` のクライアント認証アサーション（RFC 7523 / OIDC Core §9）。

``client_secret`` と違い、**秘密鍵はホストから出ない**。配備の設定（環境変数）に
資格情報そのものを置かずに済むのが採用理由で、機械としての名乗り
（``client_credentials``）はこの方式だけを使う。

IdP 側の検証:

- ``client_assertion_type`` は ``urn:ietf:params:oauth:client-assertion-type:jwt-bearer`` のみ
- ``iss`` と ``sub`` はどちらも **client_id 自身**（RFC 7523 §3）
- ``aud`` はトークンエンドポイント（発行者そのものを受ける IdP もある）
- **``jti`` 必須**。再生防止のため IdP 側が記録する
- ``exp`` は短いこと。長くしても得るものは無く、再生の窓を伸ばすだけ
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

import jwt

ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"

#: アサーションの寿命。⚠ **長くしない**（IdP 側が ``jti`` を覚える期間も伸びる）。
LIFETIME_SECONDS = 60


@dataclass(frozen=True)
class ClientAssertionRequest:
    """アサーションを 1 通作るための入力。

    ``client_id`` / ``audience`` / ``kid`` はどれも ``str`` なので、位置引数で渡すと
    取り違えが型検査を抜ける。取り違えれば IdP 側で ``invalid_client`` になるが、
    **どれで落ちたかは返ってこない**ので、入口でまとめて運ぶ。
    """

    client_id: str
    audience: str
    private_key_pem: str
    kid: str | None
    now: datetime


def build_client_assertion(request: ClientAssertionRequest) -> str:
    """トークンエンドポイントへ提示する署名付きアサーションを組み立てる。"""
    headers = {"typ": "JWT"}
    if request.kid:
        # 鍵が複数登録されていると、kid が無ければ IdP はどれで検証するか決められない。
        headers["kid"] = request.kid
    return jwt.encode(
        {
            "iss": request.client_id,
            "sub": request.client_id,
            "aud": request.audience,
            # 毎回異なる値。IdP が記録して再生を防ぐ。
            "jti": secrets.token_urlsafe(32),
            "iat": request.now,
            "exp": request.now + timedelta(seconds=LIFETIME_SECONDS),
        },
        request.private_key_pem,
        algorithm="RS256",
        headers=headers,
    )


__all__ = ["ASSERTION_TYPE", "LIFETIME_SECONDS", "ClientAssertionRequest", "build_client_assertion"]
