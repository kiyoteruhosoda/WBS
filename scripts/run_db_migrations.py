from __future__ import annotations

import sys
from pathlib import Path

# スクリプト直接実行(`python scripts/run_db_migrations.py`)でも `src` パッケージを
# 解決できるよう、リポジトリルートを import パスへ加える。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.infrastructure.database.connection import init_db  # noqa: E402

# 接続先は DATABASE_URL 環境変数（未設定時は sqlite:///./app.db）。
# init_db() は冪等で、スキーマ作成と初期ユーザー投入を行う。
init_db()
