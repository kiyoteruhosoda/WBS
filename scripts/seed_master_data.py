from __future__ import annotations

import os
import sys
from pathlib import Path

# Add the repository root to the import path so the `src` package resolves even when
# the script is run directly (`python scripts/seed_master_data.py`).
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
        # Overwrite the default user seeded by init_db() with ADMIN_EMAIL
        # (an email address the user has already changed is left alone).
        user.email = admin_email
        session.commit()
