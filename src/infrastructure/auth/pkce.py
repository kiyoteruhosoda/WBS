"""PKCE（RFC 7636）の code_challenge 生成。"""

from __future__ import annotations

import base64
import hashlib

CODE_CHALLENGE_METHOD = "S256"


def code_challenge_from_verifier(code_verifier: str) -> str:
    """``S256`` 方式の code_challenge。

    認可コードは IdP から利用者のブラウザ経由で戻ってくるため、リダイレクト履歴や
    ログから漏れ得る。challenge を先に預けておけば、verifier を持たない相手は
    コードを手に入れてもトークンに換えられない。
    """
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
