"""Types used by the API schemas.

`UtcDatetime` is an annotated type that always returns stored values as ISO strings ending in ``Z``.
Returning a bare ``datetime`` gives no offset, so the browser's ``new Date()`` reads it
as local time and the display is off by 9 hours (HANDOVER §14).

When adding a time to a response, use this type instead of ``datetime``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import PlainSerializer

from src.shared.clock import isoformat_utc

UtcDatetime = Annotated[
    datetime,
    PlainSerializer(isoformat_utc, return_type=str, when_used="json"),
]

__all__ = ["UtcDatetime"]
