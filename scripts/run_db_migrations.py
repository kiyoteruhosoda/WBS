from src.infrastructure.database.connection import init_db, resolve_db_path

init_db(resolve_db_path("/app/data/app.db"))
