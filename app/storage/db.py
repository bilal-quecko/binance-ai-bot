"""SQLite storage helpers."""

from pathlib import Path
import sqlite3


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        requested_quantity TEXT NOT NULL,
        approved_quantity TEXT NOT NULL,
        filled_quantity TEXT NOT NULL,
        status TEXT NOT NULL,
        risk_decision TEXT NOT NULL,
        reason_codes TEXT NOT NULL,
        fill_price TEXT NOT NULL,
        realized_pnl TEXT NOT NULL,
        quote_balance TEXT NOT NULL,
        event_time TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fills (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id TEXT NOT NULL,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        filled_quantity TEXT NOT NULL,
        fill_price TEXT NOT NULL,
        fee_paid TEXT NOT NULL,
        realized_pnl TEXT NOT NULL,
        quote_balance TEXT NOT NULL,
        event_time TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS positions_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        quantity TEXT NOT NULL,
        avg_entry_price TEXT NOT NULL,
        realized_pnl TEXT NOT NULL,
        quote_asset TEXT NOT NULL,
        snapshot_time TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pnl_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_time TEXT NOT NULL,
        equity TEXT NOT NULL,
        total_pnl TEXT NOT NULL,
        realized_pnl TEXT NOT NULL,
        cash_balance TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runner_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_type TEXT NOT NULL,
        symbol TEXT NOT NULL,
        message TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        event_time TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_signal_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        snapshot_time TEXT NOT NULL,
        bias TEXT NOT NULL,
        confidence INTEGER NOT NULL,
        entry_signal INTEGER NOT NULL,
        exit_signal INTEGER NOT NULL,
        suggested_action TEXT NOT NULL,
        explanation TEXT NOT NULL,
        feature_summary_json TEXT NOT NULL
    )
    """,
)


def resolve_sqlite_path(database_url: str) -> Path:
    """Resolve a sqlite database URL to a local filesystem path."""

    if not database_url.startswith("sqlite:///"):
        raise ValueError("Only sqlite:/// database URLs are supported for paper-mode storage.")
    return Path(database_url.removeprefix("sqlite:///")).resolve()


def create_db_connection(database_url: str) -> sqlite3.Connection:
    """Create a SQLite connection and initialize the paper-mode schema."""

    db_path = resolve_sqlite_path(database_url)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=MEMORY")
    connection.execute("PRAGMA synchronous=OFF")
    initialize_schema(connection)
    return connection


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Create the required paper-mode storage tables."""

    with connection:
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
