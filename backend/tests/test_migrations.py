import logging
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.config import settings


def test_alembic_round_trip_creates_missing_sqlite_parent(tmp_path, monkeypatch, caplog):
    database_path = tmp_path / "missing" / "deck_versions.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite+aiosqlite:///{database_path}")
    alembic_config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    application_logger = logging.getLogger("app.tests.migration_order")
    application_logger.disabled = False
    monkeypatch.setattr(application_logger, "handlers", [*application_logger.handlers, caplog.handler])

    command.upgrade(alembic_config, "head")
    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"decks", "deck_versions"} <= tables

    command.downgrade(alembic_config, "base")
    with sqlite3.connect(database_path) as connection:
        remaining_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert "decks" not in remaining_tables
    assert "deck_versions" not in remaining_tables

    with caplog.at_level(logging.WARNING, logger=application_logger.name):
        application_logger.warning("application logger remains enabled")

    assert application_logger.disabled is False
    assert "application logger remains enabled" in caplog.messages
