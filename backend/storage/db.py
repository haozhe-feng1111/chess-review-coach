"""SQLite persistence: engine, session factory and schema creation.

SQLAlchemy is used as a thin mapping over SQLite — no migrations framework for the MVP,
the schema is created on startup if missing.
"""

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from storage.models import Base

logger = logging.getLogger(__name__)


def create_db_engine(database_url: str, echo: bool = False) -> Engine:
    """Create the SQLAlchemy engine, making sure the SQLite file's directory exists."""
    if database_url.startswith("sqlite:///"):
        path = database_url.replace("sqlite:///", "", 1)
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, echo=echo, future=True, connect_args=connect_args)

    if database_url.startswith("sqlite"):
        # WAL keeps the UI responsive while an analysis job writes progress rows.
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record):  # pragma: no cover
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def ensure_columns(engine: Engine) -> List[str]:
    """Add columns that exist in the models but not yet in an older SQLite file.

    The MVP deliberately ships no migration framework, but an existing local database
    must not hard-crash just because a new field was added to a model: without this,
    ``SELECT mate_before`` fails with "no such column" and the whole review screen
    breaks for anyone who analyzed games with an earlier version.

    Only additive changes are handled here (new nullable/defaulted columns and new
    tables via ``create_all``). Anything that needs a data rewrite is out of scope —
    the answer there is to re-analyze, and this function only reports what it did.
    """
    from sqlalchemy import inspect, text

    added: List[str] = []
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            present = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in present:
                    continue
                ddl = "ALTER TABLE {} ADD COLUMN {} {}".format(
                    table.name, column.name, column.type.compile(engine.dialect)
                )
                default = _literal_default(column)
                if default is not None:
                    ddl += " DEFAULT {}".format(default)
                connection.execute(text(ddl))
                added.append("{}.{}".format(table.name, column.name))
                logger.info("Added missing column %s.%s", table.name, column.name)

    return added


def _literal_default(column) -> Optional[str]:
    """SQL literal for a column default, or None when there is nothing safe to use."""
    if column.default is None or not getattr(column.default, "is_scalar", False):
        return None
    value = column.default.arg
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return "'{}'".format(escaped)
    return None


class Database:
    """Owns the engine and hands out sessions."""

    def __init__(self, database_url: str, echo: bool = False) -> None:
        self.engine = create_db_engine(database_url, echo=echo)
        self._session_factory = sessionmaker(bind=self.engine, expire_on_commit=False, future=True)

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)
        ensure_columns(self.engine)

    def drop_all(self) -> None:
        Base.metadata.drop_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        self.engine.dispose()


_db: Optional[Database] = None


def get_database(database_url: Optional[str] = None) -> Database:
    """Process-wide database handle (the MVP is a single-process local app)."""
    global _db
    if _db is None or database_url is not None:
        from config import settings

        url = database_url or settings.resolved_database_url
        _db = Database(url)
        _db.create_all()
        logger.info("Database ready at %s", url)
    return _db
