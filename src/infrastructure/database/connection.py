import os
import sqlite3

_MEMORY_CONNECTIONS: dict[str, sqlite3.Connection] = {}


def get_connection(db_path: str) -> sqlite3.Connection:
    if db_path == ":memory:":
        db_path = "file:wbs_memory?mode=memory&cache=shared"
        if db_path not in _MEMORY_CONNECTIONS:
            _MEMORY_CONNECTIONS[db_path] = sqlite3.connect(
                db_path, check_same_thread=False, uri=True
            )
        conn = sqlite3.connect(db_path, check_same_thread=False, uri=True)
    else:
        conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def resolve_db_path(default: str = "app.db") -> str:
    explicit_path = os.getenv("SQLITE_PATH")
    if explicit_path:
        return explicit_path
    database_url = os.getenv("DATABASE_URL")
    if database_url and database_url.startswith("sqlite:////"):
        return "/" + database_url.removeprefix("sqlite:////")
    if database_url and database_url.startswith("sqlite:///"):
        return database_url.removeprefix("sqlite:///")
    return default


def init_db(db_path: str) -> None:
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO users (id, email, display_name) VALUES (1, 'local@example.com', 'ローカルユーザー')"
        )
        conn.commit()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
  timezone TEXT NOT NULL DEFAULT 'Asia/Tokyo', is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL DEFAULT 1, name TEXT NOT NULL, color TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0, deleted_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id,name),
  CHECK(color IS NULL OR (length(color)=7 AND substr(color,1,1)='#')),
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS milestones (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL DEFAULT 1, name TEXT NOT NULL, due_date TEXT,
  description TEXT, deleted_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL DEFAULT 1, title TEXT NOT NULL, category_id INTEGER,
  priority INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5), urgency INTEGER NOT NULL DEFAULT 3 CHECK(urgency BETWEEN 1 AND 5),
  status TEXT NOT NULL DEFAULT 'TODO' CHECK(status IN ('TODO','DOING','WAITING','DONE','CANCELLED')),
  start_date TEXT, due_date TEXT, estimated_hours REAL, remaining_hours REAL, memo TEXT, parent_task_id INTEGER, milestone_id INTEGER,
  completed_at TEXT, deleted_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK(estimated_hours IS NULL OR estimated_hours >= 0), CHECK(remaining_hours IS NULL OR remaining_hours >= 0),
  CHECK(start_date IS NULL OR due_date IS NULL OR start_date <= due_date), CHECK(parent_task_id IS NULL OR parent_task_id <> id),
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE, FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE SET NULL,
  FOREIGN KEY(parent_task_id) REFERENCES tasks(id) ON DELETE SET NULL, FOREIGN KEY(milestone_id) REFERENCES milestones(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS work_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL DEFAULT 1, task_id INTEGER NOT NULL, work_date TEXT NOT NULL, hours REAL NOT NULL CHECK(hours > 0 AND hours <= 24),
  memo TEXT, deleted_at TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE, FOREIGN KEY(task_id) REFERENCES tasks(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS task_dependencies (
  predecessor_task_id INTEGER NOT NULL, successor_task_id INTEGER NOT NULL, dependency_type TEXT NOT NULL DEFAULT 'FS' CHECK(dependency_type IN ('FS','SS','FF','SF')), lag_days INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY(predecessor_task_id, successor_task_id), CHECK(predecessor_task_id <> successor_task_id),
  FOREIGN KEY(predecessor_task_id) REFERENCES tasks(id) ON DELETE CASCADE, FOREIGN KEY(successor_task_id) REFERENCES tasks(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS inbox_items (
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL DEFAULT 1, title TEXT NOT NULL, memo TEXT, converted_task_id INTEGER, converted_at TEXT, deleted_at TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE, FOREIGN KEY(converted_task_id) REFERENCES tasks(id) ON DELETE SET NULL
);
"""
