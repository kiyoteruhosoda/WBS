import os

from src.infrastructure.database.connection import get_connection, init_db

path = os.getenv("SQLITE_PATH", "/app/data/app.db")
init_db(path)
with get_connection(path) as conn:
    conn.execute(
        "INSERT OR IGNORE INTO users (id,email,display_name) VALUES (1,?,?)",
        (os.getenv("ADMIN_EMAIL", "local@example.com"), "ローカルユーザー"),
    )
    conn.commit()
