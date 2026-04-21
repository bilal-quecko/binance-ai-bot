"""SQLite storage helpers."""

from __future__ import annotations

from pathlib import Path
import sqlite3


AI_SIGNAL_FEATURE_SUMMARY_DEFAULT = (
    '{"candle_count": 0, "close_price": "0", "microstructure_healthy": false, '
    '"momentum": null, "spread_ratio": null, "volatility_pct": null, '
    '"volume_change_pct": null, "volume_spike_ratio": null}'
)


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
    """
    CREATE TABLE IF NOT EXISTS market_candle_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        open_time TEXT NOT NULL,
        close_time TEXT NOT NULL,
        close_price TEXT NOT NULL,
        event_time TEXT NOT NULL,
        UNIQUE(symbol, timeframe, open_time)
    )
    """,
)

OPTIONAL_TABLE_COLUMNS: dict[str, dict[str, str]] = {
    "ai_signal_snapshots": {
        "id": "INTEGER",
        "symbol": "TEXT NOT NULL DEFAULT ''",
        "snapshot_time": "TEXT NOT NULL DEFAULT ''",
        "bias": "TEXT NOT NULL DEFAULT 'sideways'",
        "confidence": "INTEGER NOT NULL DEFAULT 0",
        "entry_signal": "INTEGER NOT NULL DEFAULT 0",
        "exit_signal": "INTEGER NOT NULL DEFAULT 0",
        "suggested_action": "TEXT NOT NULL DEFAULT 'wait'",
        "explanation": "TEXT NOT NULL DEFAULT ''",
        "feature_summary_json": f"TEXT NOT NULL DEFAULT '{AI_SIGNAL_FEATURE_SUMMARY_DEFAULT}'",
    },
    "market_candle_snapshots": {
        "id": "INTEGER",
        "symbol": "TEXT NOT NULL DEFAULT ''",
        "timeframe": "TEXT NOT NULL DEFAULT '1m'",
        "open_time": "TEXT NOT NULL DEFAULT ''",
        "close_time": "TEXT NOT NULL DEFAULT ''",
        "close_price": "TEXT NOT NULL DEFAULT '0'",
        "event_time": "TEXT NOT NULL DEFAULT ''",
    },
}


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
        _ensure_optional_table_columns(connection)


def _ensure_optional_table_columns(connection: sqlite3.Connection) -> None:
    """Add missing optional AI/evaluation columns for older local SQLite files."""

    for table_name, column_definitions in OPTIONAL_TABLE_COLUMNS.items():
        existing_columns = _get_existing_columns(connection, table_name)
        for column_name, column_definition in column_definitions.items():
            if column_name in existing_columns:
                continue
            connection.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
            )


def _get_existing_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    """Return the current column names for a SQLite table."""

    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}
