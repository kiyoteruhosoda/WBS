"""IdP のディスカバリ文書（``/.well-known/openid-configuration``）の取得。"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from src.domain.exceptions import AuthenticationError
from src.infrastructure.auth.idp_http import IDP_HEADERS

# 署名アルゴリズムの許可リスト。`none` と対称鍵（HS*）は入れない。
# JWKS の公開鍵で検証する前提なので、対称鍵を許すと「公開鍵を鍵として HS256 を
# 検証する」古典的な取り違えの入口になる。
SUPPORTED_SIGNING_ALGORITHMS = ("RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "PS256", "PS384", "PS512")

DISCOVERY_CACHE_SECONDS = 3600.0


@dataclass(frozen=True)
class OidcDiscovery:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    userinfo_endpoint: str | None
    end_session_endpoint: str | None
    id_token_signing_alg_values_supported: tuple[str, ...]
    token_endpoint_auth_methods_supported: tuple[str, ...]

    @property
    def allowed_algorithms(self) -> list[str]:
        advertised = [
            alg for alg in self.id_token_signing_alg_values_supported
            if alg in SUPPORTED_SIGNING_ALGORITHMS
        ]
        # IdP が何も告げない（または対応外しか告げない）場合でも RS256 は必須仕様
        return advertised or ["RS256"]


class OidcDiscoveryClient:
    """ディスカバリ文書を取り、しばらく使い回す。

    毎ログインで取りに行くと IdP の可用性がそのままログインの可用性になるので、
    既定 1 時間だけ手元に置く。
    """

    def __init__(self, issuer: str, *, timeout_seconds: float = 10.0,
                 cache_seconds: float = DISCOVERY_CACHE_SECONDS) -> None:
        self._issuer = issuer.rstrip("/")
        self._timeout = timeout_seconds
        self._cache_seconds = cache_seconds
        self._cached: OidcDiscovery | None = None
        self._fetched_at: float | None = None

    @property
    def well_known_url(self) -> str:
        return f"{self._issuer}/.well-known/openid-configuration"

    def get(self) -> OidcDiscovery:
        # 経過時間の計測なので壁時計ではなく単調増加時計を使う
        # （NTP の補正やサマータイムでキャッシュが飛んだり居座ったりしないように）。
        now = time.monotonic()
        cache_is_fresh = (
            self._cached is not None
            and self._fetched_at is not None
            and now - self._fetched_at < self._cache_seconds
        )
        if cache_is_fresh:
            return self._cached
        document = self._fetch()
        self._cached = document
        self._fetched_at = now
        return document

    def _fetch(self) -> OidcDiscovery:
        try:
            response = httpx.get(self.well_known_url, timeout=self._timeout, headers=IDP_HEADERS)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise AuthenticationError(f"Could not reach the identity provider: {exc}") from exc
        except ValueError as exc:
            raise AuthenticationError("Identity provider returned a malformed discovery document") from exc

        # 突き合わせは末尾の `/` を無視するが、保持するのは IdP が名乗ったそのままの
        # 文字列。ID トークンの `iss` は正規化されずに届くので、ここで削ると
        # 末尾に `/` を含む発行者（Auth0 など）で必ず検証に落ちる。
        advertised_issuer = str(payload.get("issuer", ""))
        if advertised_issuer.rstrip("/") != self._issuer:
            # ここが食い違うと、後段の ID トークン検証で使う iss がどちらか分からなくなる
            raise AuthenticationError(
                f"Issuer mismatch: configured {self._issuer!r}, discovery says {advertised_issuer!r}"
            )
        try:
            return OidcDiscovery(
                issuer=advertised_issuer,
                authorization_endpoint=payload["authorization_endpoint"],
                token_endpoint=payload["token_endpoint"],
                jwks_uri=payload["jwks_uri"],
                userinfo_endpoint=payload.get("userinfo_endpoint"),
                end_session_endpoint=payload.get("end_session_endpoint"),
                id_token_signing_alg_values_supported=tuple(
                    payload.get("id_token_signing_alg_values_supported", ())
                ),
                token_endpoint_auth_methods_supported=tuple(
                    payload.get("token_endpoint_auth_methods_supported", ())
                ),
            )
        except KeyError as exc:
            raise AuthenticationError(
                f"Discovery document is missing a required field: {exc.args[0]}"
            ) from exc
