"""SQLite storage helpers."""

from __future__ import annotations

import logging
from pathlib import Path
import sqlite3
import tempfile
from hashlib import sha1

LOGGER = logging.getLogger(__name__)
_SQLITE_PATH_FALLBACK_CACHE: dict[Path, Path] = {}

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
        event_time TEXT NOT NULL,
        execution_source TEXT NOT NULL DEFAULT 'auto',
        trading_profile TEXT NOT NULL DEFAULT 'balanced',
        session_id TEXT,
        tuning_version_id TEXT
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
        event_time TEXT NOT NULL,
        execution_source TEXT NOT NULL DEFAULT 'auto',
        trading_profile TEXT NOT NULL DEFAULT 'balanced',
        session_id TEXT,
        tuning_version_id TEXT
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
    """
    CREATE TABLE IF NOT EXISTS signal_validation_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        snapshot_time TEXT NOT NULL,
        price TEXT NOT NULL,
        final_action TEXT NOT NULL,
        fusion_final_signal TEXT NOT NULL DEFAULT 'wait',
        confidence INTEGER NOT NULL,
        expected_edge_pct TEXT,
        estimated_cost_pct TEXT,
        risk_grade TEXT NOT NULL,
        preferred_horizon TEXT NOT NULL,
        technical_score TEXT,
        technical_context_json TEXT NOT NULL,
        sentiment_score TEXT,
        sentiment_context_json TEXT NOT NULL,
        pattern_score TEXT,
        pattern_context_json TEXT NOT NULL,
        ai_context_json TEXT NOT NULL,
        top_reasons_json TEXT NOT NULL,
        warnings_json TEXT NOT NULL,
        invalidation_hint TEXT,
        trade_opened INTEGER NOT NULL DEFAULT 0,
        signal_ignored_or_blocked INTEGER NOT NULL DEFAULT 0,
        blocker_reasons_json TEXT NOT NULL,
        regime_label TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS historical_candles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        interval TEXT NOT NULL,
        open_time TEXT NOT NULL,
        close_time TEXT NOT NULL,
        open_price TEXT NOT NULL,
        high_price TEXT NOT NULL,
        low_price TEXT NOT NULL,
        close_price TEXT NOT NULL,
        volume TEXT NOT NULL,
        quote_volume TEXT NOT NULL DEFAULT '0',
        trade_count INTEGER NOT NULL DEFAULT 0,
        source TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(symbol, interval, open_time)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS runtime_session_state (
        singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
        state TEXT NOT NULL,
        mode TEXT NOT NULL,
        trading_profile TEXT NOT NULL DEFAULT 'balanced',
        symbol TEXT,
        session_id TEXT,
        started_at TEXT,
        last_event_time TEXT,
        last_error TEXT,
        tuning_version_id TEXT,
        baseline_tuning_version_id TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS paper_broker_state (
        singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
        balances_json TEXT NOT NULL,
        realized_pnl TEXT NOT NULL,
        snapshot_time TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS paper_broker_positions (
        symbol TEXT PRIMARY KEY,
        quantity TEXT NOT NULL,
        avg_entry_price TEXT NOT NULL,
        realized_pnl TEXT NOT NULL,
        quote_asset TEXT NOT NULL,
        snapshot_time TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS profile_tuning_sets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        version_id TEXT NOT NULL UNIQUE,
        symbol TEXT,
        profile TEXT NOT NULL,
        status TEXT NOT NULL,
        config_json TEXT NOT NULL,
        baseline_config_json TEXT NOT NULL,
        created_at TEXT NOT NULL,
        applied_at TEXT,
        baseline_version_id TEXT,
        reason TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS paper_session_runs (
        session_id TEXT PRIMARY KEY,
        symbol TEXT NOT NULL,
        trading_profile TEXT NOT NULL,
        tuning_version_id TEXT,
        baseline_tuning_version_id TEXT,
        started_at TEXT NOT NULL,
        ended_at TEXT
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
    "signal_validation_snapshots": {
        "id": "INTEGER",
        "symbol": "TEXT NOT NULL DEFAULT ''",
        "snapshot_time": "TEXT NOT NULL DEFAULT ''",
        "price": "TEXT NOT NULL DEFAULT '0'",
        "final_action": "TEXT NOT NULL DEFAULT 'wait'",
        "fusion_final_signal": "TEXT NOT NULL DEFAULT 'wait'",
        "confidence": "INTEGER NOT NULL DEFAULT 0",
        "expected_edge_pct": "TEXT",
        "estimated_cost_pct": "TEXT",
        "risk_grade": "TEXT NOT NULL DEFAULT 'high'",
        "preferred_horizon": "TEXT NOT NULL DEFAULT '15m'",
        "technical_score": "TEXT",
        "technical_context_json": "TEXT NOT NULL DEFAULT '{}'",
        "sentiment_score": "TEXT",
        "sentiment_context_json": "TEXT NOT NULL DEFAULT '{}'",
        "pattern_score": "TEXT",
        "pattern_context_json": "TEXT NOT NULL DEFAULT '{}'",
        "ai_context_json": "TEXT NOT NULL DEFAULT '{}'",
        "top_reasons_json": "TEXT NOT NULL DEFAULT '[]'",
        "warnings_json": "TEXT NOT NULL DEFAULT '[]'",
        "invalidation_hint": "TEXT",
        "trade_opened": "INTEGER NOT NULL DEFAULT 0",
        "signal_ignored_or_blocked": "INTEGER NOT NULL DEFAULT 0",
        "blocker_reasons_json": "TEXT NOT NULL DEFAULT '[]'",
        "regime_label": "TEXT",
    },
    "historical_candles": {
        "id": "INTEGER",
        "symbol": "TEXT NOT NULL DEFAULT ''",
        "interval": "TEXT NOT NULL DEFAULT '1m'",
        "open_time": "TEXT NOT NULL DEFAULT ''",
        "close_time": "TEXT NOT NULL DEFAULT ''",
        "open_price": "TEXT NOT NULL DEFAULT '0'",
        "high_price": "TEXT NOT NULL DEFAULT '0'",
        "low_price": "TEXT NOT NULL DEFAULT '0'",
        "close_price": "TEXT NOT NULL DEFAULT '0'",
        "volume": "TEXT NOT NULL DEFAULT '0'",
        "quote_volume": "TEXT NOT NULL DEFAULT '0'",
        "trade_count": "INTEGER NOT NULL DEFAULT 0",
        "source": "TEXT NOT NULL DEFAULT 'historical_rest'",
        "created_at": "TEXT NOT NULL DEFAULT ''",
    },
    "runtime_session_state": {
        "trading_profile": "TEXT NOT NULL DEFAULT 'balanced'",
        "tuning_version_id": "TEXT",
        "baseline_tuning_version_id": "TEXT",
    },
    "trades": {
        "execution_source": "TEXT NOT NULL DEFAULT 'auto'",
        "trading_profile": "TEXT NOT NULL DEFAULT 'balanced'",
        "session_id": "TEXT",
        "tuning_version_id": "TEXT",
    },
    "fills": {
        "execution_source": "TEXT NOT NULL DEFAULT 'auto'",
        "trading_profile": "TEXT NOT NULL DEFAULT 'balanced'",
        "session_id": "TEXT",
        "tuning_version_id": "TEXT",
    },
}


def resolve_sqlite_path(database_url: str) -> Path:
    """Resolve a sqlite database URL to a local filesystem path."""

    if not database_url.startswith("sqlite:///"):
        raise ValueError("Only sqlite:/// database URLs are supported for paper-mode storage.")
    requested_path = Path(database_url.removeprefix("sqlite:///")).resolve()
    requested_path.parent.mkdir(parents=True, exist_ok=True)
    return _resolve_usable_sqlite_path(requested_path)


def create_db_connection(database_url: str) -> sqlite3.Connection:
    """Create a SQLite connection and initialize the paper-mode schema."""

    db_path = resolve_sqlite_path(database_url)
    connection = sqlite3.connect(db_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    _configure_sqlite_connection(connection)
    connection.execute("PRAGMA busy_timeout=5000")
    initialize_schema(connection)
    return connection


def _resolve_usable_sqlite_path(requested_path: Path) -> Path:
    """Return a SQLite path that supports local paper-mode journaling."""

    cached_path = _SQLITE_PATH_FALLBACK_CACHE.get(requested_path)
    if cached_path is not None:
        cached_path.parent.mkdir(parents=True, exist_ok=True)
        return cached_path

    if _sqlite_path_supports_wal(requested_path):
        _SQLITE_PATH_FALLBACK_CACHE[requested_path] = requested_path
        return requested_path

    fallback_root = Path(tempfile.gettempdir()) / "binance-ai-bot" / "sqlite"
    fallback_root.mkdir(parents=True, exist_ok=True)
    fallback_name = f"{requested_path.stem}_{sha1(str(requested_path).encode('utf-8')).hexdigest()[:12]}{requested_path.suffix}"
    fallback_path = fallback_root / fallback_name
    LOGGER.warning(
        "SQLite path %s does not support WAL in this environment; using temp storage %s instead.",
        requested_path,
        fallback_path,
    )
    _SQLITE_PATH_FALLBACK_CACHE[requested_path] = fallback_path
    return fallback_path


def _sqlite_path_supports_wal(requested_path: Path) -> bool:
    """Return whether a SQLite database path can enable WAL and create schema files."""

    probe_path = requested_path.parent / f".{requested_path.stem}_probe{requested_path.suffix}"
    _cleanup_sqlite_probe_artifacts(probe_path)

    connection = sqlite3.connect(probe_path, check_same_thread=False)
    try:
        connection.row_factory = sqlite3.Row
        row = connection.execute("PRAGMA journal_mode=WAL").fetchone()
        journal_mode = str(row[0]).lower() if row is not None else ""
        if journal_mode != "wal":
            return False
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("CREATE TABLE sqlite_probe (id INTEGER PRIMARY KEY)")
        connection.commit()
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        connection.close()
        _cleanup_sqlite_probe_artifacts(probe_path)


def _cleanup_sqlite_probe_artifacts(probe_path: Path) -> None:
    """Best-effort cleanup for SQLite probe files."""

    for candidate in (
        probe_path,
        probe_path.with_name(f"{probe_path.name}-wal"),
        probe_path.with_name(f"{probe_path.name}-shm"),
        probe_path.with_suffix(f"{probe_path.suffix}-journal"),
    ):
        if not candidate.exists():
            continue
        try:
            candidate.unlink()
        except PermissionError:
            LOGGER.debug("Skipping locked SQLite probe cleanup for %s.", candidate)


def _configure_sqlite_connection(connection: sqlite3.Connection) -> None:
    """Configure SQLite pragmas with WAL preference and safe fallback."""

    try:
        row = connection.execute("PRAGMA journal_mode=WAL").fetchone()
        journal_mode = str(row[0]).lower() if row is not None else ""
        if journal_mode != "wal":
            raise sqlite3.OperationalError(f"journal_mode={journal_mode or 'unknown'}")
    except sqlite3.OperationalError as exc:
        LOGGER.warning("WAL journal mode is unavailable in this environment; continuing with SQLite default journal mode: %s", exc)
    connection.execute("PRAGMA synchronous=NORMAL")


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
