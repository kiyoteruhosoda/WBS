import pytest


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    from main import create_app

    app = create_app(db_path=str(tmp_path / "test.db"))
    with TestClient(app) as c:
        yield c
