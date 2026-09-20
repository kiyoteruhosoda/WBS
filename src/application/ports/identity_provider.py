"""外部 IdP との会話の口（ポート）。実装はインフラ層。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.domain.value_objects.identity_claims import IdentityClaims


@dataclass(frozen=True)
class AuthorizationRequest:
    """認可エンドポイントへ利用者のブラウザを飛ばすための材料。"""

    authorization_url: str
    state: str
    nonce: str
    code_verifier: str


class IdentityProvider(ABC):
    """OIDC の Relying Party 側から見た IdP。

    ユースケースはこのインターフェースしか知らない。ディスカバリ・JWKS 取得・
    ID トークンの署名検証といった手順はすべて実装側に隠す。
    """

    @property
    @abstractmethod
    def display_name(self) -> str:
        """ログイン画面のボタンに出す IdP の名前。"""

    @abstractmethod
    def build_authorization_request(self, *, state: str, nonce: str, code_verifier: str) -> AuthorizationRequest:
        """認可リクエスト URL を組み立てる。"""

    @abstractmethod
    def exchange_code(self, *, code: str, code_verifier: str, nonce: str) -> IdentityClaims:
        """認可コードを ID トークンに交換し、検証して本人のクレームを返す。

        署名・``iss``・``aud``・``exp``・``nonce`` の検証は実装側の責務。
        検証に通らなければ ``AuthenticationError`` を送出する。
        """

    @abstractmethod
    def build_end_session_url(self, *, post_logout_redirect_uri: str | None) -> str | None:
        """IdP 側もログアウトさせる URL。IdP が対応していなければ None。"""

    @abstractmethod
    def verify_logout_token(self, token: str) -> Mapping[str, Any]:
        """停止の通知（``logout_token``）を JWT として確かめ、クレームを返す。

        確かめるのは**署名・発行者・対象者・期限**まで。「ログアウトの通知として
        成立しているか」（``events`` / ``nonce`` / ``sub`` か ``sid`` / ``jti``）の
        判断はドメイン側（``LogoutNotice``）が行う。

        通らなければ ``InvalidLogoutTokenError`` を送出する。
        """

    @property
    @abstractmethod
    def federated_issuer(self) -> str:
        """**手元に残した宛名を引くための**発行者の綴り。

        ⚠ ディスカバリ文書が名乗るままの綴り（ID トークンの ``iss`` と完全一致で
        照合する値）とは別。末尾の ``/`` の有無が違うだけで、引く行が 1 つも
        見つからなくなる。
        """
