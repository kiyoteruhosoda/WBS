"""検証済み ID トークンから取り出した、本人を表すクレーム。"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.exceptions import ValidationError
from src.domain.value_objects.federated_identity import FederatedIdentity


@dataclass(frozen=True)
class IdentityClaims:
    """IdP から受け取った本人情報。

    署名・``iss``・``aud``・``exp``・``nonce`` の検証はインフラ層（IdP アダプタ）で
    済ませてからここへ入れる。この値オブジェクトが受け持つのは「アプリが本人を
    作る／突き合わせるのに足りているか」の検査だけ。
    """

    identity: FederatedIdentity
    email: str | None = None
    email_verified: bool = False
    display_name: str | None = None
    preferred_username: str | None = None

    def __post_init__(self) -> None:
        if self.email is not None and "@" not in self.email:
            raise ValidationError(f"Invalid email in ID token: {self.email}")

    @property
    def issuer(self) -> str:
        return self.identity.issuer

    @property
    def subject(self) -> str:
        return self.identity.subject

    @property
    def email_domain(self) -> str | None:
        """メールアドレスのドメイン部（小文字）。所属の絞り込みに使う。"""
        if self.email is None:
            return None
        return self.email.rsplit("@", 1)[1].lower()

    def resolved_display_name(self) -> str:
        """画面に出す名前。IdP が name を返さないことがあるので順に落とす。"""
        for candidate in (self.display_name, self.preferred_username, self.email, self.subject):
            if candidate and candidate.strip():
                return candidate.strip()
        return self.subject
