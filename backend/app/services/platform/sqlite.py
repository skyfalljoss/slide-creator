from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine


def prepare_sqlite_database(url: str) -> None:
    """Create the parent for a file-backed aiosqlite database URL."""
    parsed = make_url(url)
    if parsed.drivername != "sqlite+aiosqlite":
        return
    if not parsed.database or parsed.database == ":memory:":
        return
    if str(parsed.query.get("uri", "")).lower() == "true":
        return

    Path(parsed.database).expanduser().parent.mkdir(parents=True, exist_ok=True)


def enable_sqlite_foreign_keys(engine: AsyncEngine) -> None:
    """Enable foreign-key enforcement on every SQLite application connection."""
    if engine.url.get_backend_name() != "sqlite":
        return

    def set_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    event.listen(engine.sync_engine, "connect", set_foreign_keys)
