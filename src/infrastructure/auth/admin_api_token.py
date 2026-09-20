"""IdP の**管理 API** を叩くときに名乗るトークン。

``client_credentials`` ＋ ``private_key_jwt`` で取る。ログイン用の登録
（``OIDC_CLIENT_ID``。public ＋ PKCE で鍵を持たない）とは別の、**このアプリの
サービスアカウント**（``MACHINE_CLIENT_ID``）として名乗る。

- **宛名は ``{issuer}/admin``。** 管理 API のトークンはこの ``aud`` でなければ通らない。
  ⚠ **設定にしない** ——発行者から決まる値で、運用者が選ぶものではない。
- **方式は常に ``private_key_jwt``。** ログインが public クライアントでも、機械は鍵で名乗る。
- **トークンエンドポイントはディスカバリから引く**（ログイン・停止の受け口と同じ出所）。

⚠ **IdP 側でこのサービスアカウントをアプリの名乗りとして結び付ける必要がある。**
結び付けるまで管理 API は 403 を返し続ける（トークンそのものは取れる）。
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import httpx

from src.domain.exceptions import IdentityProviderUnavailableError
from src.infrastructure.auth.auth_settings import AuthConfigurationError, AuthSettings
from src.infrastructure.auth.client_assertion import (
    ASSERTION_TYPE,
    ClientAssertionRequest,
    build_client_assertion,
)
from src.infrastructure.auth.idp_http import IDP_HEADERS
from src.infrastructure.auth.oidc_discovery import OidcDiscoveryClient
from src.shared.clock import utcnow

logger = logging.getLogger(__name__)

#: 期限のどれだけ手前で取り直すか（秒）。⚠ **0 にしない**（送信中に期限が来ると 401 で落ちる）。
RENEW_MARGIN_SECONDS = 60.0

#: 期限が読めなかったときに仮定する寿命（秒）。⚠ 無期限と読むと二度と取り直さない。
FALLBACK_LIFETIME_SECONDS = 60.0


def admin_audience(issuer: str) -> str:
    """管理 API のトークンに刻む宛名。

    ⚠ **``issuer`` にはテナントが含まれる**（``https://identity.example/<tenant>``）ので、
    宛名はその後ろに ``/admin`` を足したものになる。
    """
    return f"{issuer.rstrip('/')}/admin"


class AdminToken(Protocol):
    """管理 API 向けの 1 本を出すもの。

    名簿を引く側が要るのはこの 2 つだけ。**クラスではなくこの形に依存させる**ので、
    試験は IdP を立てずに差し替えられる。
    """

    def token(self) -> str: ...

    def invalidate(self) -> None: ...


class AdminApiTokenSource:
    """管理 API 用のトークンを取得し、期限の手前まで使い回す。

    プロセスで 1 つ持つ。周回のたびに取り直すと、照合 1 回につき IdP への往復が 1 つ増える。
    """

    def __init__(
        self,
        settings: AuthSettings,
        discovery: OidcDiscoveryClient | None = None,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._discovery = discovery or OidcDiscoveryClient(
            settings.issuer, timeout_seconds=settings.http_timeout_seconds
        )
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._token = ""
        self._expires_at = 0.0

    def token(self) -> str:
        client_id = self._settings.machine_client_id
        if not client_id:
            raise AuthConfigurationError("MACHINE_CLIENT_ID is not configured")
        with self._lock:
            if self._token and self._monotonic() < self._expires_at:
                return self._token
        discovery = self._discovery.get()
        issued, lifetime = self._request(
            client_id=client_id,
            token_endpoint=discovery.token_endpoint,
            audience=admin_audience(discovery.issuer),
        )
        with self._lock:
            self._token = issued
            self._expires_at = self._monotonic() + max(lifetime - RENEW_MARGIN_SECONDS, 1.0)
            return self._token

    def invalidate(self) -> None:
        """控えているトークンを捨てる（401 を受けたときに呼ぶ）。"""
        with self._lock:
            self._token = ""
            self._expires_at = 0.0

    def _request(self, *, client_id: str, token_endpoint: str, audience: str) -> tuple[str, float]:
        assertion = build_client_assertion(
            ClientAssertionRequest(
                client_id=client_id,
                audience=token_endpoint,
                private_key_pem=self._private_key(),
                kid=self._settings.machine_private_key_kid,
                now=utcnow(),
            )
        )
        payload = self._post(
            token_endpoint, client_id=client_id, assertion=assertion, audience=audience
        )
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise IdentityProviderUnavailableError("the token response has no access_token")
        lifetime = payload.get("expires_in")
        if isinstance(lifetime, bool) or not isinstance(lifetime, int | float):
            return token, FALLBACK_LIFETIME_SECONDS
        return token, float(lifetime)

    def _private_key(self) -> str:
        path = self._settings.machine_private_key_file
        if not path:
            raise AuthConfigurationError("MACHINE_CLIENT_ID requires MACHINE_PRIVATE_KEY_FILE")
        try:
            return Path(path).read_text(encoding="utf-8")
        except OSError as error:
            # 0400 root だとコンテナの実行ユーザーは読めない（group を実行 gid に合わせる）。
            raise AuthConfigurationError(
                f"cannot read the machine private key: {type(error).__name__}"
            ) from error

    def _post(
        self, endpoint: str, *, client_id: str, assertion: str, audience: str
    ) -> dict[str, object]:
        form = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_assertion_type": ASSERTION_TYPE,
            "client_assertion": assertion,
            # ⚠ 管理 API では宛名が**必須**。省くと権限の載らないトークンになり、
            #   管理 API 側で弾かれる。
            "resource": audience,
        }
        try:
            response = httpx.post(
                endpoint,
                data=form,
                headers={"Accept": "application/json", **IDP_HEADERS},
                timeout=self._settings.http_timeout_seconds,
            )
        except httpx.HTTPError as error:
            raise IdentityProviderUnavailableError(
                f"the token endpoint is unreachable: {type(error).__name__}"
            ) from error
        if response.status_code != 200:
            # ⚠ 本文をそのままログに出さない（トークンが載りうる）。
            logger.warning(
                "機械の名乗りでトークンを取得できませんでした",
                extra={
                    "event": "auth.oidc.admin_token_failed",
                    "status_code": response.status_code,
                },
            )
            raise IdentityProviderUnavailableError(
                f"the token endpoint returned {response.status_code}"
            )
        try:
            body = response.json()
        except ValueError as error:
            raise IdentityProviderUnavailableError("the token response is not JSON") from error
        return body if isinstance(body, dict) else {}


__all__ = [
    "FALLBACK_LIFETIME_SECONDS",
    "RENEW_MARGIN_SECONDS",
    "AdminApiTokenSource",
    "AdminToken",
    "admin_audience",
]
