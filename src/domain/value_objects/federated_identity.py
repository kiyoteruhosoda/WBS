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

    ⚠ **``issuer`` は末尾の ``/`` を落とした綴りで持つ。** 同じ IdP を指す綴りが
    2 つあると、ログインで書いた行を停止の通知や定期照合が引けなくなる。
    ディスカバリ文書側（``OidcDiscovery.issuer``）は IdP が名乗ったままを保つ
    ——ID トークンの ``iss`` は**完全一致**で照合するため。
    """

    issuer: str
    subject: str

    def __post_init__(self) -> None:
        if not self.issuer.strip():
            raise ValidationError("issuer must not be empty")
        if not self.subject.strip():
            raise ValidationError("subject must not be empty")
        # 発行者の綴りをここで 1 つに揃える。ディスカバリ文書は IdP が名乗ったまま
        # （末尾の `/` を含みうる）を保つ必要があるが、**手元に残す宛名**は揃って
        # いなければならない。揃っていないと、停止の通知や定期照合が引く行を
        # 1 つも見つけられず、**例外もログも出ないまま何も止まらない**。
        object.__setattr__(self, "issuer", self.issuer.strip().rstrip("/"))
        object.__setattr__(self, "subject", self.subject.strip())
