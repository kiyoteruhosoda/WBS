from __future__ import annotations

import os
import sys
from pathlib import Path

# スクリプト直接実行(`python scripts/seed_master_data.py`)でも `src` パッケージを
# 解決できるよう、リポジトリルートを import パスへ加える。
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.infrastructure.database.connection import init_db  # noqa: E402
from src.infrastructure.database.models import UserModel  # noqa: E402
from src.infrastructure.database.session import get_db_session  # noqa: E402

DEFAULT_EMAIL = "local@example.com"

init_db()
admin_email = os.getenv("ADMIN_EMAIL", DEFAULT_EMAIL)
with get_db_session() as session:
    user = session.get(UserModel, 1)
    if user is None:
        session.add(UserModel(id=1, email=admin_email, display_name="ローカルユーザー"))
        session.commit()
    elif user.email == DEFAULT_EMAIL and admin_email != DEFAULT_EMAIL:
        # init_db() が投入した既定ユーザーを ADMIN_EMAIL で上書きする
        # （利用者が変更済みのメールアドレスには触れない）。
        user.email = admin_email
        session.commit()
