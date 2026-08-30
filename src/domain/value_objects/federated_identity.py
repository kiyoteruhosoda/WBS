"""外部 IdP 上の本人を指す値オブジェクト。"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.exceptions import ValidationError


@dataclass(frozen=True)
class FederatedIdentity:
    """IdP が発行した「発行者 + 主体」の対。

    OIDC ではユーザーの一意性は ``sub`` 単独ではなく ``(iss, sub)`` の組で決まる
    （``sub`` は発行者の中でだけ一意）。メールアドレスは IdP 側で変更・再割当てが
    あり得るので、突き合わせの鍵には使わない。
    """

    issuer: str
    subject: str

    def __post_init__(self) -> None:
        if not self.issuer.strip():
            raise ValidationError("issuer must not be empty")
        if not self.subject.strip():
            raise ValidationError("subject must not be empty")
