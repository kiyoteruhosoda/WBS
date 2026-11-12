"""Source of unguessable strings. Replaced with fixed values in tests."""

from __future__ import annotations

import secrets
from abc import ABC, abstractmethod


class SecretGenerator(ABC):
    @abstractmethod
    def generate(self) -> str: ...


class UrlSafeSecretGenerator(SecretGenerator):
    """Default implementation using ``secrets`` (32 bytes = 256 bits)."""

    def __init__(self, num_bytes: int = 32) -> None:
        self._num_bytes = num_bytes

    def generate(self) -> str:
        return secrets.token_urlsafe(self._num_bytes)
