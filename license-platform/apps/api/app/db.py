from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Connection, Engine, Result

from app.config import settings


BASE_DIR = Path(__file__).resolve().parents[3]
POSTGRES_SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"
SQLITE_SCHEMA_PATH = BASE_DIR / "database" / "sqlite_schema.sql"

_ENGINE: Engine | None = None
_ENGINE_URL: str = ""


def is_sqlite_url(database_url: str) -> bool:
    return database_url.startswith("sqlite:///")


def is_postgres_url(database_url: str) -> bool:
    return database_url.startswith("postgresql://") or database_url.startswith("postgresql+psycopg://")


def database_driver() -> str:
    if is_sqlite_url(settings.database_url):
        return "sqlite"
    if is_postgres_url(settings.database_url):
        return "postgresql"
    raise ValueError(f"Unsupported database URL: {settings.database_url}")


def get_sqlite_path() -> Path:
    prefix = "sqlite:///"
    if not is_sqlite_url(settings.database_url):
        raise ValueError("Current database URL is not sqlite:///")
    return Path(settings.database_url[len(prefix) :]).expanduser()


def _configure_sqlite(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA busy_timeout = 5000")
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.execute("PRAGMA synchronous = NORMAL")
    cursor.close()


def get_engine() -> Engine:
    global _ENGINE, _ENGINE_URL
    if _ENGINE is not None and _ENGINE_URL == settings.database_url:
        return _ENGINE

    driver = database_driver()
    if driver == "sqlite":
        db_path = get_sqlite_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(
            settings.database_url,
            future=True,
            connect_args={"timeout": 5},
        )
        event.listen(engine, "connect", _configure_sqlite)
    else:
        engine = create_engine(
            settings.database_url,
            future=True,
            pool_pre_ping=True,
        )

    _ENGINE = engine
    _ENGINE_URL = settings.database_url
    return engine


def _split_sql_statements(script: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    in_double_quote = False

    for char in script:
        if char == "'" and not in_double_quote:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote:
            in_double_quote = not in_double_quote
        if char == ";" and not in_single_quote and not in_double_quote:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            continue
        current.append(char)

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def _load_schema_statements() -> list[str]:
    driver = database_driver()
    if driver == "sqlite":
        if not SQLITE_SCHEMA_PATH.exists():
            raise FileNotFoundError(f"Missing SQLite schema: {SQLITE_SCHEMA_PATH}")
        return _split_sql_statements(SQLITE_SCHEMA_PATH.read_text(encoding="utf-8"))
    if not POSTGRES_SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Missing PostgreSQL schema: {POSTGRES_SCHEMA_PATH}")
    return _split_sql_statements(POSTGRES_SCHEMA_PATH.read_text(encoding="utf-8"))


def _prepare_statement(sql: str, params: Any) -> tuple[Any, dict[str, Any]]:
    if params is None:
        return text(sql), {}
    if isinstance(params, dict):
        return text(sql), params
    if not isinstance(params, (list, tuple)):
        raise TypeError(f"Unsupported SQL params type: {type(params)!r}")

    bind_params: dict[str, Any] = {}
    pieces: list[str] = []
    index = 0
    for char in sql:
        if char == "?":
            name = f"p{index}"
            pieces.append(f":{name}")
            bind_params[name] = params[index]
            index += 1
        else:
            pieces.append(char)
    if index != len(params):
        raise ValueError("SQL placeholder count does not match provided params.")
    return text("".join(pieces)), bind_params


class DBRow:
    def __init__(self, mapping: dict[str, Any]):
        self._mapping = dict(mapping)

    def __getitem__(self, key: str) -> Any:
        return self._mapping[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self._mapping.get(key, default)

    def __iter__(self) -> Iterator[str]:
        return iter(self._mapping)

    def __len__(self) -> int:
        return len(self._mapping)

    def as_dict(self) -> dict[str, Any]:
        return dict(self._mapping)


class DBResult:
    def __init__(self, result: Result[Any]):
        self._result = result

    def fetchone(self) -> DBRow | None:
        row = self._result.mappings().first()
        if row is None:
            return None
        return DBRow(dict(row))

    def fetchall(self) -> list[DBRow]:
        return [DBRow(dict(row)) for row in self._result.mappings().all()]


class DBSession:
    def __init__(self, connection: Connection):
        self._connection = connection

    def execute(self, sql: str, params: Any = ()) -> DBResult:
        statement, bind_params = _prepare_statement(sql, params)
        return DBResult(self._connection.execute(statement, bind_params))

    def executescript(self, script: str):
        for statement in _split_sql_statements(script):
            self._connection.exec_driver_sql(statement)


class _ConnectContext:
    def __init__(self):
        self._context = get_engine().begin()
        self._connection: Connection | None = None

    def __enter__(self) -> DBSession:
        self._connection = self._context.__enter__()
        return DBSession(self._connection)

    def __exit__(self, exc_type, exc, tb):
        return self._context.__exit__(exc_type, exc, tb)


def connect() -> _ConnectContext:
    return _ConnectContext()


def init_db():
    with connect() as conn:
        for statement in _load_schema_statements():
            conn.execute(statement)
        _ensure_runtime_schema(conn)


def _sqlite_column_exists(conn: DBSession, table_name: str, column_name: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(str(row["name"]).strip().lower() == column_name.strip().lower() for row in rows)


def _postgres_column_exists(conn: DBSession, table_name: str, column_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = ?
          AND column_name = ?
        LIMIT 1
        """,
        (table_name, column_name),
    ).fetchone()
    return row is not None


def _ensure_runtime_schema(conn: DBSession):
    driver = database_driver()
    if driver == "sqlite":
        if not _sqlite_column_exists(conn, "license_keys", "validity_seconds"):
            conn.execute(
                "ALTER TABLE license_keys ADD COLUMN validity_seconds INTEGER NOT NULL DEFAULT 0"
            )
        return
    if not _postgres_column_exists(conn, "license_keys", "validity_seconds"):
        conn.execute(
            "ALTER TABLE license_keys ADD COLUMN validity_seconds INTEGER NOT NULL DEFAULT 0"
        )
