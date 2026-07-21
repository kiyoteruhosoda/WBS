from __future__ import annotations

from dataclasses import dataclass


@dataclass
class UpdateUserSettingsDTO:
    display_name: str | None = None
    timezone: str | None = None
    language: str | None = None
