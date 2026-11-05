"""認証まわりの設定を環境変数から 1 つのオブジェクトにまとめる。

``build_info.py`` と同じ流儀で、環境変数を読む場所をここ 1 つに閉じ込める
（アプリの各所から ``os.getenv`` を呼ばない）。
"""

from __future__ import annotations

import enum
import json
import os
from dataclasses import dataclass
from datetime import timedelta

from src.domain.value_objects.provisioning_policy import ProvisioningPolicy

DEFAULT_COOKIE_NAME = "wbs_access_token"
#: 以前出していたリフレッシュトークンとログアウトの札の Cookie（ADR-0069）。もう出さず、手元に残っていれば落とす（ADR-0071）
REFRESH_COOKIE_NAME = "wbs_refresh_token"
LOGOUT_COOKIE_NAME = "wbs_logout_token"
#: アクセストークンの寿命。⚠ **この値が「止めたら効くまで」の上限時間そのものになる**（ADR-0069）
DEFAULT_ACCESS_TOKEN_EXPIRES_SECONDS = 300.0
#: ログインの控えと、アクセストークンの Cookie を残す長さ（ADR-0071）。トークン自体は 5 分で切れる。
#: 切れた後も Cookie を残すのは、画面を出さずに続ける往復が「誰の・どのログインか」を読むため。
#: IdP のログイン状態の最も長いもの（30 日）に揃える。続けるたびに控えの期限も延びる
SIGN_IN_CARRY = timedelta(days=30)
#: 署名鍵の短さの下限（HS256 の鍵は SHA-256 の出力と同じ 32 バイト以上）
MIN_SIGNING_KEY_LENGTH = 32
DEFAULT_SCOPES = "openid email profile"
SINGLE_USER_ID = 1
# Set-Cookie の SameSite に書ける値。ここで弾かないと、誤記に気づくのが
# 「ログインの最後で Cookie を載せるとき」になり、500 だけが見える。
ALLOWED_SAMESITE = ("lax", "strict", "none")


class AuthMode(enum.StrEnum):
    SINGLE_USER = "single_user"
    OIDC = "oidc"


class AuthConfigurationError(RuntimeError):
    """設定が足りない・矛盾している。起動時に落として気づけるようにする。"""


@dataclass(frozen=True)
class AuthSettings:
    mode: AuthMode
    #: ⚠ **末尾の ``/`` を落とした綴り。** ディスカバリ文書が名乗るままの綴り
    #: （ID トークンの ``iss`` と完全一致で照合する値）とは別（``OidcDiscovery.issuer``）。
    issuer: str
    client_id: str
    client_secret: str | None
    redirect_uri: str
    scopes: str
    provider_name: str
    post_logout_redirect_uri: str | None
    http_timeout_seconds: float
    cookie_name: str
    cookie_secure: bool
    cookie_samesite: str
    policy: ProvisioningPolicy
    #: アクセストークンの寿命（ADR-0069）。切れたら画面が IdP へ画面を出さずに問い合わせる（ADR-0071）
    access_token_ttl: timedelta = timedelta(seconds=DEFAULT_ACCESS_TOKEN_EXPIRES_SECONDS)
    #: ログインの控えとアクセストークンの Cookie を残す長さ（ADR-0071）
    sign_in_carry: timedelta = SIGN_IN_CARRY
    #: このアプリのトークンの署名鍵。⚠ **プロセスをまたいで同じでなければならない**（ADR-0069）。
    session_signing_key: str = ""
    #: IdP へ**こちらから**問い合わせるときの名乗り（サービスアカウントの ``client_id``）。
    #: ⚠ ログイン用の ``client_id`` とは別の登録。**空なら定期照合は走らない。**
    machine_client_id: str = ""
    machine_private_key_file: str = ""
    machine_private_key_kid: str | None = None
    #: ほかのアプリのサーバーが機械として読み書きに来るときの、このアプリの宛名（assay の resource。ADR-0056）。
    #: ⚠ **空なら機械の口は 1 本も通さない。**
    machine_audience: str = ""
    #: 利用者の代わりに読み書きしてよいアプリの**機械の** ``client_id``（Tracker のサーバー。ADR-0056）。
    machine_reader_client_ids: frozenset[str] = frozenset()

    @property
    def sso_enabled(self) -> bool:
        return self.mode is AuthMode.OIDC

    @property
    def reconciliation_enabled(self) -> bool:
        """定期照合を走らせるか。**名乗りが無ければ走らせない**（何も聞けない）。"""
        return self.sso_enabled and bool(self.machine_client_id)

    @property
    def scope_list(self) -> list[str]:
        return self.scopes.split()


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise AuthConfigurationError(f"{key} must be a number, got {raw!r}") from exc


def _env_domains(key: str) -> tuple[str, ...]:
    raw = os.getenv(key, "")
    return tuple(d.strip().lower() for d in raw.split(",") if d.strip())


def _env_list(key: str) -> frozenset[str]:
    """カンマ区切り（または JSON の配列）。空の要素は捨てる。"""
    raw = os.getenv(key, "").strip()
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
        except ValueError as exc:
            raise AuthConfigurationError(f"{key} must be a JSON array or comma-separated") from exc
        items = [str(item) for item in parsed] if isinstance(parsed, list) else [str(parsed)]
    else:
        items = raw.split(",")
    return frozenset(item.strip() for item in items if item.strip())


def _env_samesite(key: str, *, cookie_secure: bool) -> str:
    value = os.getenv(key, "lax").strip().lower() or "lax"
    if value not in ALLOWED_SAMESITE:
        raise AuthConfigurationError(
            f"{key} must be one of: {', '.join(ALLOWED_SAMESITE)} (got {value!r})"
        )
    if value == "none" and not cookie_secure:
        # SameSite=None の Cookie は Secure が無いとブラウザに捨てられる。
        # 起動はするがログインだけが通らない、という一番分かりにくい壊れ方になる。
        raise AuthConfigurationError(f"{key}=none requires AUTH_COOKIE_SECURE=true")
    return value


def _load_signing_key() -> str:
    """署名鍵を読む。本番はファイルの場所（``SESSION_SIGNING_KEY_FILE``）で渡す。⚠ 値をログへ出さない。"""
    value = os.getenv("SESSION_SIGNING_KEY", "").strip()
    if value:
        return value
    path = os.getenv("SESSION_SIGNING_KEY_FILE", "").strip()
    if not path:
        return ""
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError as exc:
        raise AuthConfigurationError(f"SESSION_SIGNING_KEY_FILE could not be read: {path}") from exc


def _env_seconds(key: str, default: float) -> timedelta:
    seconds = _env_float(key, default)
    if seconds <= 0:
        raise AuthConfigurationError(f"{key} must be positive (got {seconds})")
    return timedelta(seconds=seconds)


def load_auth_settings() -> AuthSettings:
    raw_mode = os.getenv("AUTH_MODE", AuthMode.SINGLE_USER.value).strip().lower()
    try:
        mode = AuthMode(raw_mode)
    except ValueError as exc:
        allowed = ", ".join(m.value for m in AuthMode)
        raise AuthConfigurationError(f"AUTH_MODE must be one of: {allowed} (got {raw_mode!r})") from exc

    issuer = os.getenv("OIDC_ISSUER", "").strip().rstrip("/")
    client_id = os.getenv("OIDC_CLIENT_ID", "").strip()
    client_secret = os.getenv("OIDC_CLIENT_SECRET") or None
    redirect_uri = os.getenv("OIDC_REDIRECT_URI", "").strip()

    if mode is AuthMode.OIDC:
        missing = [
            name
            for name, value in (
                ("OIDC_ISSUER", issuer),
                ("OIDC_CLIENT_ID", client_id),
                ("OIDC_REDIRECT_URI", redirect_uri),
            )
            if not value
        ]
        if missing:
            raise AuthConfigurationError(
                "AUTH_MODE=oidc requires " + ", ".join(missing)
            )
        if not issuer.startswith("https://") and not issuer.startswith("http://localhost"):
            # ID トークンの取得経路が TLS でないと、途中で差し替えられても気づけない
            raise AuthConfigurationError(
                f"OIDC_ISSUER must use https (got {issuer!r}); http is only allowed for localhost"
            )

    signing_key = _load_signing_key()
    if mode is AuthMode.OIDC and len(signing_key) < MIN_SIGNING_KEY_LENGTH:
        # ⚠ 起動で落とす。乱数で埋めると、再起動のたびに全員のログインが切れる
        raise AuthConfigurationError(
            "AUTH_MODE=oidc requires SESSION_SIGNING_KEY_FILE "
            f"(a signing key of at least {MIN_SIGNING_KEY_LENGTH} characters)"
        )

    cookie_secure = _env_bool("AUTH_COOKIE_SECURE", True)
    return AuthSettings(
        mode=mode,
        issuer=issuer,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scopes=os.getenv("OIDC_SCOPES", DEFAULT_SCOPES).strip() or DEFAULT_SCOPES,
        provider_name=os.getenv("OIDC_PROVIDER_NAME", "SSO").strip() or "SSO",
        post_logout_redirect_uri=os.getenv("AUTH_POST_LOGOUT_REDIRECT_URI") or None,
        http_timeout_seconds=_env_float("OIDC_HTTP_TIMEOUT_SECONDS", 10.0),
        access_token_ttl=_env_seconds(
            "ACCESS_TOKEN_EXPIRES_SECONDS", DEFAULT_ACCESS_TOKEN_EXPIRES_SECONDS
        ),
        session_signing_key=signing_key,
        cookie_name=os.getenv("AUTH_COOKIE_NAME", DEFAULT_COOKIE_NAME).strip() or DEFAULT_COOKIE_NAME,
        cookie_secure=cookie_secure,
        cookie_samesite=_env_samesite("AUTH_COOKIE_SAMESITE", cookie_secure=cookie_secure),
        policy=ProvisioningPolicy(
            auto_provision=_env_bool("OIDC_AUTO_PROVISION", True),
            allowed_email_domains=_env_domains("OIDC_ALLOWED_EMAIL_DOMAINS"),
            require_verified_email=_env_bool("OIDC_REQUIRE_VERIFIED_EMAIL", True),
            # ⚠ **既定は寄せない。** メールアドレスは本人の証明ではない（下記）。
            link_by_email=_env_bool("OIDC_LINK_BY_EMAIL", False),
        ),
        machine_client_id=os.getenv("MACHINE_CLIENT_ID", "").strip(),
        machine_private_key_file=os.getenv("MACHINE_PRIVATE_KEY_FILE", "").strip(),
        machine_private_key_kid=os.getenv("MACHINE_PRIVATE_KEY_KID", "").strip() or None,
        machine_audience=os.getenv("MACHINE_AUDIENCE", "").strip(),
        machine_reader_client_ids=_env_list("MACHINE_READER_CLIENT_IDS"),
    )
