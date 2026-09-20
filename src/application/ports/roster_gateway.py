"""IdP に「いま誰がこのアプリを使ってよいか」を聞く口（ポート）。実装はインフラ層。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.value_objects.roster import Roster


class RosterGateway(ABC):
    @abstractmethod
    def fetch(self, *, issuer: str, subjects: tuple[str, ...]) -> Roster:
        """名指しで聞く。

        ⚠ **候補の一覧では足りない。** 「向こうに居ない（消えた）」は、こちらが
        名前を挙げて聞いて初めて分かる。

        ⚠ **引けなかったら例外で止めること。** 空の名簿として返すと、呼び出し側は
        「全員辞めた」と読む（``IdentityProviderUnavailableError`` /
        ``MachineNotBoundToApplicationError``）。
        """


__all__ = ["RosterGateway"]
