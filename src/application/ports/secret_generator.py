"""推測できない文字列の供給元。テストでは決め打ちに差し替える。"""

from __future__ import annotations

import secrets
from abc import ABC, abstractmethod


class SecretGenerator(ABC):
    @abstractmethod
    def generate(self) -> str: ...


class UrlSafeSecretGenerator(SecretGenerator):
    """``secrets`` による既定の実装（32 バイト = 256 ビット）。"""

    def __init__(self, num_bytes: int = 32) -> None:
        self._num_bytes = num_bytes

    def generate(self) -> str:
        return secrets.token_urlsafe(self._num_bytes)
