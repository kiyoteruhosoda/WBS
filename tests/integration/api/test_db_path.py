from src.infrastructure.database.connection import resolve_db_path


def test_resolve_db_path_prefers_sqlite_path(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "sqlite:////app/data/app.db")
    monkeypatch.setenv("SQLITE_PATH", "/tmp/wbs.db")

    assert resolve_db_path() == "/tmp/wbs.db"


def test_resolve_db_path_reads_absolute_sqlite_url(monkeypatch) -> None:
    monkeypatch.delenv("SQLITE_PATH", raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite:////app/data/app.db")

    assert resolve_db_path() == "/app/data/app.db"
