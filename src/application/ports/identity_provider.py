"""外部 IdP との会話の口（ポート）。実装はインフラ層。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

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
