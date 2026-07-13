import os

from src.infrastructure.database.connection import init_db

init_db(os.getenv("SQLITE_PATH", "/app/data/app.db"))
