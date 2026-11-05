"""このアプリが自分で出すトークン（ADR-0069・ADR-0071）。assay のトークンとは別物で、中身を知るのはこのアプリだけ。

出すのはアクセストークンだけ（ADR-0071。リフレッシュトークンとログアウトの札はもう出さない）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.domain.value_objects.continued_sign_in import ContinuedSignIn


@dataclass(frozen=True)
class AccessTokenContents:
    user: AuthenticatedUserDTO
    session_id: str


class SessionTokens(ABC):
    @abstractmethod
    def access_token(self, user: AuthenticatedUserDTO, *, session_id: str, now: datetime) -> str:
        """⚠ **検証が DB を引かないので、利用者について要るものは全部載せる。**"""

    @abstractmethod
    def read_access(self, token: str, *, now: datetime) -> AccessTokenContents | None:
        """署名と期限を確かめて読む。読めなければ ``None``。"""

    @abstractmethod
    def continuation_of(self, token: str, *, now: datetime) -> ContinuedSignIn | None:
        """期限の切れたアクセストークンから、続けるログインを読む（ADR-0071）。

        ⚠ **これは認証ではない。** 署名・発行者・宛先・種類は確かめ、期限は控えを残す長さまで見逃す。
        読んだ値は、IdP から同じ人が戻ってきたとき（続ける往復）とログアウトにだけ使う。
        """
