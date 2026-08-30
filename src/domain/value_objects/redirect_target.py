"""ログイン後に戻す画面のパス。"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_REDIRECT_PATH = "/"


@dataclass(frozen=True)
class RedirectTarget:
    """自サイト内の相対パスであることを保証した戻り先。

    ``?next=`` は利用者が自由に付けられるので、そのまま ``Location`` に載せると
    IdP のログイン直後に外部サイトへ飛ばせてしまう（オープンリダイレクト）。
    受け取った値はここを必ず通し、外部を指し得る形は既定のパスへ落とす。
    """

    path: str

    @classmethod
    def parse(cls, raw: str | None) -> RedirectTarget:
        if not raw:
            return cls(DEFAULT_REDIRECT_PATH)
        candidate = raw.strip()
        if not candidate.startswith("/"):
            # 絶対 URL・スキーム相対・素の相対パスはすべて外部を指し得る
            return cls(DEFAULT_REDIRECT_PATH)
        if candidate.startswith("//") or candidate.startswith("/\\"):
            # `//evil.example` はスキーム相対 URL として外部ホストに解決される
            return cls(DEFAULT_REDIRECT_PATH)
        if "\\" in candidate or "\n" in candidate or "\r" in candidate:
            # バックスラッシュを `/` として読むブラウザがある。改行はヘッダ分割の材料。
            return cls(DEFAULT_REDIRECT_PATH)
        return cls(candidate)

    def __str__(self) -> str:
        return self.path
