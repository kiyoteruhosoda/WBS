"""IdP で本人確認できた人を、このアプリに入れてよいかの規則。"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.exceptions import AccessDeniedError
from src.domain.value_objects.identity_claims import IdentityClaims


@dataclass(frozen=True)
class ProvisioningPolicy:
    """初回ログイン時に利用者を自動で作るか、誰を通すかの決めごと。

    IdP で認証が通ることと、このアプリを使ってよいことは別。テナント共用の IdP
    （Microsoft Entra ID の common エンドポイントなど）では、素通しにすると
    「認証は成功するので誰でも入れる」状態になる。
    """

    auto_provision: bool = True
    allowed_email_domains: tuple[str, ...] = ()
    require_verified_email: bool = True
    #: まだ結び付いていない人を、**同じメールアドレスの既存利用者**へ寄せてよいか。
    #:
    #: ⚠ **既定は寄せない。** ``email_verified`` が真でも、それは「IdP がそのアドレスへ
    #: 到達できることを確かめた」であって「この利用者が本人である」ではない。寄せる形を
    #: 開けておくと、IdP 側で誰かのアドレスを名乗れた時点で、このアプリの既存の口座
    #: （＝過去の作業記録）に入れてしまう。結び付けは ``(iss, sub)`` が既に在るときだけ。
    link_by_email: bool = False

    def ensure_allowed(self, claims: IdentityClaims) -> None:
        needs_email = bool(self.allowed_email_domains) or self.require_verified_email
        if needs_email and claims.email is None:
            raise AccessDeniedError(
                "IdP did not provide an email address; cannot apply the sign-in policy"
            )
        if self.require_verified_email and not claims.email_verified:
            raise AccessDeniedError(f"Email address is not verified by the IdP: {claims.email}")
        if self.allowed_email_domains and claims.email_domain not in self.allowed_email_domains:
            raise AccessDeniedError(f"Email domain is not allowed: {claims.email}")

    def ensure_can_link_by_email(self, claims: IdentityClaims) -> None:
        """メールアドレスで既存の利用者へ寄せてよいかを確かめる。

        ⚠ **2 つの関門を両方通ること。** 「寄せてよい」と決めてあっても、IdP が
        検証していないアドレスでは寄せない。
        """
        if not self.link_by_email:
            raise AccessDeniedError(
                "This account is not linked to an identity provider subject; "
                "linking by email address is disabled (OIDC_LINK_BY_EMAIL)"
            )
        if not self.require_verified_email:
            raise AccessDeniedError(
                "Linking an existing account by email requires verified email addresses; "
                "enable OIDC_REQUIRE_VERIFIED_EMAIL"
            )

    def ensure_can_provision(self, claims: IdentityClaims) -> None:
        """未登録の人を新規に作ってよいか。"""
        if not self.auto_provision:
            raise AccessDeniedError(
                "This account is not registered and automatic provisioning is disabled"
            )
        if claims.email is None:
            raise AccessDeniedError("IdP did not provide an email address; cannot create a user")
