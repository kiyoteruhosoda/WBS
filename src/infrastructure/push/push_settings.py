"""端末への通知（Web Push）の設定を環境変数から読む（task #193 / ADR-0031）。

⚠ **秘密鍵は値ではなく場所で持つ**（``WEB_PUSH_VAPID_PRIVATE_KEY_FILE``）。環境変数・設定画面に
鍵の中身を入れない。どちらかが空なら端末への通知は送らない（既定。購読も受け取らない）。
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PushSettings:
    #: VAPID の秘密鍵（P-256 の PEM）の置き場
    vapid_private_key_file: str = ""
    #: VAPID の ``sub``（連絡先。``mailto:`` か ``https:``）。通知サービスが困ったときの連絡先
    subject: str = ""

    @property
    def configured(self) -> bool:
        return bool(self.vapid_private_key_file and self.subject)


def load_push_settings() -> PushSettings:
    return PushSettings(
        vapid_private_key_file=os.getenv("WEB_PUSH_VAPID_PRIVATE_KEY_FILE", "").strip(),
        subject=os.getenv("WEB_PUSH_SUBJECT", "").strip(),
    )


__all__ = ["PushSettings", "load_push_settings"]
