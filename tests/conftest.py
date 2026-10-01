import shutil

import pytest


@pytest.fixture(scope="session")
def migrated_database_template(tmp_path_factory):
    """head まで上げて既定の利用者を入れた DB を 1 回だけ作る（試験ごとに写して使う）。"""
    from src.infrastructure.database.connection import init_db
    from src.infrastructure.database.session import get_engine

    path = tmp_path_factory.mktemp("template") / "template.db"
    init_db(f"sqlite:///{path}")
    get_engine().dispose()
    return path


@pytest.fixture
def database_path(tmp_path, migrated_database_template):
    path = tmp_path / "test.db"
    shutil.copyfile(migrated_database_template, path)
    return str(path)


@pytest.fixture
def client(database_path):
    from fastapi.testclient import TestClient

    from main import create_app

    app = create_app(db_path=database_path)
    with TestClient(app) as c:
        yield c
