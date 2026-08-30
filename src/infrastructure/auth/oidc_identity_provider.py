"""OIDC 認可コードフロー（PKCE 付き）で IdP と話す実装。

``IdentityProvider`` ポートの唯一の実装。Keycloak / Microsoft Entra ID /
Google Workspace / Okta など、ディスカバリ文書を出す IdP であれば設定だけで繋がる。
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient

from src.application.ports.identity_provider import AuthorizationRequest, IdentityProvider
from src.domain.exceptions import AuthenticationError
from src.domain.value_objects.federated_identity import FederatedIdentity
from src.domain.value_objects.identity_claims import IdentityClaims
from src.infrastructure.auth.auth_settings import AuthSettings
from src.infrastructure.auth.idp_http import IDP_HEADERS
from src.infrastructure.auth.oidc_discovery import OidcDiscoveryClient
from src.infrastructure.auth.pkce import CODE_CHALLENGE_METHOD, code_challenge_from_verifier

JWKS_CACHE_SECONDS = 300

# JSON の真値として認める文字列。`email_verified` を素の ``bool()`` に通すと
# ``bool("false")`` が True になり、「検証済みメールしか通さない」規則が
# 文字列で真偽値を返す IdP でだけ素通しになる。
_TRUE_STRINGS = {"true", "1", "yes"}


def _as_bool(value: object, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in _TRUE_STRINGS
    return bool(value)


class OidcIdentityProvider(IdentityProvider):
    def __init__(
        self,
        settings: AuthSettings,
        discovery: OidcDiscoveryClient | None = None,
        jwks_client: PyJWKClient | None = None,
    ) -> None:
        self._settings = settings
        self._discovery = discovery or OidcDiscoveryClient(
            settings.issuer, timeout_seconds=settings.http_timeout_seconds
        )
        self._jwks_client = jwks_client

    @property
    def display_name(self) -> str:
        return self._settings.provider_name

    # ── 認可リクエスト ─────────────────────────────────────────────────
    def build_authorization_request(
        self, *, state: str, nonce: str, code_verifier: str
    ) -> AuthorizationRequest:
        discovery = self._discovery.get()
        params = {
            "response_type": "code",
            "client_id": self._settings.client_id,
            "redirect_uri": self._settings.redirect_uri,
            "scope": self._settings.scopes,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge_from_verifier(code_verifier),
            "code_challenge_method": CODE_CHALLENGE_METHOD,
        }
        separator = "&" if "?" in discovery.authorization_endpoint else "?"
        url = f"{discovery.authorization_endpoint}{separator}{urlencode(params)}"
        return AuthorizationRequest(
            authorization_url=url, state=state, nonce=nonce, code_verifier=code_verifier
        )

    # ── コード交換と ID トークン検証 ───────────────────────────────────
    def exchange_code(self, *, code: str, code_verifier: str, nonce: str) -> IdentityClaims:
        discovery = self._discovery.get()
        tokens = self._request_tokens(code, code_verifier)
        id_token = tokens.get("id_token")
        if not id_token:
            raise AuthenticationError("Token response did not contain an id_token")

        claims = self._verify_id_token(id_token, nonce=nonce)
        email = claims.get("email")
        email_verified = _as_bool(claims.get("email_verified"))
        display_name = claims.get("name")
        preferred_username = claims.get("preferred_username")

        if email is None and discovery.userinfo_endpoint and tokens.get("access_token"):
            # ID トークンに email を載せない IdP がある（要求スコープや設定次第）。
            # 所属の判定に使うので、載っていなければ userinfo から取り直す。
            userinfo = self._fetch_userinfo(discovery.userinfo_endpoint, tokens["access_token"])
            if userinfo.get("sub") != claims["sub"]:
                raise AuthenticationError("userinfo response does not match the ID token subject")
            email = userinfo.get("email")
            email_verified = _as_bool(userinfo.get("email_verified"), default=email_verified)
            display_name = display_name or userinfo.get("name")
            preferred_username = preferred_username or userinfo.get("preferred_username")

        return IdentityClaims(
            identity=FederatedIdentity(issuer=claims["iss"], subject=claims["sub"]),
            email=email,
            email_verified=email_verified,
            display_name=display_name,
            preferred_username=preferred_username,
        )

    def build_end_session_url(self, *, post_logout_redirect_uri: str | None) -> str | None:
        try:
            discovery = self._discovery.get()
        except AuthenticationError:
            # IdP に届かなくても、こちら側のセッションはもう消してある。
            # ログアウトを失敗として返す理由がない。
            return None
        if not discovery.end_session_endpoint:
            return None
        params = {"client_id": self._settings.client_id}
        if post_logout_redirect_uri:
            params["post_logout_redirect_uri"] = post_logout_redirect_uri
        separator = "&" if "?" in discovery.end_session_endpoint else "?"
        return f"{discovery.end_session_endpoint}{separator}{urlencode(params)}"

    # ── 内部 ───────────────────────────────────────────────────────────
    def _request_tokens(self, code: str, code_verifier: str) -> dict:
        discovery = self._discovery.get()
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._settings.redirect_uri,
            "client_id": self._settings.client_id,
            "code_verifier": code_verifier,
        }
        auth: tuple[str, str] | None = None
        if self._settings.client_secret:
            if "client_secret_post" in discovery.token_endpoint_auth_methods_supported:
                data["client_secret"] = self._settings.client_secret
            else:
                # 既定は client_secret_basic（IdP が何も告げない場合もこちら）
                auth = (self._settings.client_id, self._settings.client_secret)
        try:
            response = httpx.post(
                discovery.token_endpoint,
                data=data,
                auth=auth,
                headers={"Accept": "application/json", **IDP_HEADERS},
                timeout=self._settings.http_timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise AuthenticationError(f"Could not reach the token endpoint: {exc}") from exc
        if response.status_code >= 400:
            # IdP のエラー本文には client_secret は載らないが、詳細は利用者に返さずログへ
            raise AuthenticationError(
                f"Token endpoint rejected the authorization code (HTTP {response.status_code})"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise AuthenticationError("Token endpoint returned a malformed response") from exc

    def _verify_id_token(self, id_token: str, *, nonce: str) -> dict:
        discovery = self._discovery.get()
        try:
            signing_key = self._get_jwks_client(discovery.jwks_uri).get_signing_key_from_jwt(id_token)
            claims = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=discovery.allowed_algorithms,
                audience=self._settings.client_id,
                issuer=discovery.issuer,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError(f"ID token verification failed: {exc}") from exc

        if claims.get("nonce") != nonce:
            # nonce が合わないトークンは、別の（あるいは以前の）ログイン向けに
            # 発行されたもの。使い回しをここで止める。
            raise AuthenticationError("ID token nonce does not match this login request")
        azp = claims.get("azp")
        if azp is not None and azp != self._settings.client_id:
            raise AuthenticationError("ID token was issued for another client")
        return claims

    def _get_jwks_client(self, jwks_uri: str) -> PyJWKClient:
        if self._jwks_client is None:
            self._jwks_client = PyJWKClient(
                jwks_uri,
                cache_keys=True,
                lifespan=JWKS_CACHE_SECONDS,
                timeout=self._settings.http_timeout_seconds,
                # ⚠ ここだけ urllib 経由。既定の UA (`Python-urllib/3.x`) は WAF に
                #   弾かれることがあり、そうなると**トークン交換までは成功したまま**
                #   署名検証だけが落ちる。詳細は idp_http.py。
                headers=IDP_HEADERS,
            )
        return self._jwks_client

    def _fetch_userinfo(self, userinfo_endpoint: str, access_token: str) -> dict:
        try:
            response = httpx.get(
                userinfo_endpoint,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                    **IDP_HEADERS,
                },
                timeout=self._settings.http_timeout_seconds,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AuthenticationError(f"Could not read the userinfo endpoint: {exc}") from exc
