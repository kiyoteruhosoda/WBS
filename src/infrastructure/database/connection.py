import sqlite3


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: str) -> None:
    # スキーマは Alembic マイグレーションで管理する（設計書 DDL 管理方針）。
    # ここでは接続の初期化のみ行い、テーブル定義は持たない。
    with get_connection(db_path) as conn:
        conn.commit()
