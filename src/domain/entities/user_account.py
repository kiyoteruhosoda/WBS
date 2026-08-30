"""アプリ内の利用者。IdP 上の本人と紐づく。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src.domain.exceptions import ValidationError
from src.domain.value_objects.federated_identity import FederatedIdentity

DEFAULT_TIMEZONE = "Asia/Tokyo"
DEFAULT_LANGUAGE = "ja"


@dataclass
class UserAccount:
    id: int | None
    email: str
    display_name: str
    timezone: str = DEFAULT_TIMEZONE
    language: str = DEFAULT_LANGUAGE
    is_active: bool = True
    identities: list[FederatedIdentity] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def has_identity(self, identity: FederatedIdentity) -> bool:
        return identity in self.identities

    def link_identity(self, identity: FederatedIdentity) -> None:
        """IdP 上の本人をこの利用者に結び付ける。

        同じ発行者の別 ``sub`` を足すのは拒む。IdP を跨いだ複数所属（社内 IdP と
        取引先 IdP など）は許すが、同じ発行者に本人が 2 つある状態は、どちらの
        セッションでも同じ画面が出てしまうため取り違えの元になる。
        """
        if self.has_identity(identity):
            return
        conflicting = next((i for i in self.identities if i.issuer == identity.issuer), None)
        if conflicting is not None:
            raise ValidationError(
                f"User is already linked to another subject on issuer {identity.issuer}"
            )
        self.identities.append(identity)

    def apply_profile(self, *, email: str | None, display_name: str | None) -> bool:
        """IdP 側のプロフィール変更を取り込む。変化があれば True。

        タイムゾーンと言語はアプリ内の設定画面で選ぶものなので上書きしない。
        """
        changed = False
        if email and email != self.email:
            self.email = email
            changed = True
        if display_name and display_name != self.display_name:
            self.display_name = display_name
            changed = True
        return changed

    def ensure_can_sign_in(self) -> None:
        if not self.is_active:
            raise ValidationError(f"User account is deactivated: {self.email}")
