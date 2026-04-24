"""SQLite repository helpers for paper-mode persistence."""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Iterator
from uuid import uuid4

from app.ai.models import AISignalSnapshot
from app.market_data.candles import Candle
from app.paper.models import FillResult, Position
from app.risk.models import RiskDecision
from app.storage.db import create_db_connection
from app.storage.models import (
    AISignalFeatureSummaryRecord,
    AISignalSnapshotRecord,
    DailyPnlRecord,
    DrawdownPoint,
    DrawdownSummary,
    EquityHistoryPoint,
    FillRecord,
    MarketCandleSnapshotRecord,
    PaperBrokerStateRecord,
    PaperSessionRunRecord,
    PnlHistoryPoint,
    PnlSnapshotRecord,
    PositionSnapshotRecord,
    ProfileTuningSetRecord,
    RuntimeSessionRecord,
    RunnerEventRecord,
    TradeRecord,
)


LOGGER = logging.getLogger(__name__)


def _decimal(value: Any) -> Decimal:
    """Convert a stored numeric value into Decimal."""

    return Decimal(str(value))


def _safe_datetime(value: Any) -> datetime | None:
    """Convert an ISO string into datetime, returning ``None`` when invalid."""

    if value in {None, ""}:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _parse_reason_codes(value: str) -> tuple[str, ...]:
    """Parse persisted reason codes from JSON."""

    raw = json.loads(value)
    return tuple(str(item) for item in raw)


def _parse_ai_feature_summary(value: str) -> AISignalFeatureSummaryRecord:
    """Parse a compact persisted AI feature summary."""

    try:
        raw = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return _empty_ai_feature_summary()
    return AISignalFeatureSummaryRecord(
        candle_count=int(raw.get("candle_count", 0)),
        close_price=_decimal(raw.get("close_price", "0")),
        volatility_pct=_decimal(raw["volatility_pct"]) if raw.get("volatility_pct") is not None else None,
        momentum=_decimal(raw["momentum"]) if raw.get("momentum") is not None else None,
        volume_change_pct=(
            _decimal(raw["volume_change_pct"]) if raw.get("volume_change_pct") is not None else None
        ),
        volume_spike_ratio=(
            _decimal(raw["volume_spike_ratio"]) if raw.get("volume_spike_ratio") is not None else None
        ),
        spread_ratio=_decimal(raw["spread_ratio"]) if raw.get("spread_ratio") is not None else None,
        microstructure_healthy=bool(raw.get("microstructure_healthy", False)),
        regime=str(raw["regime"]) if raw.get("regime") is not None else None,
        noise_level=str(raw["noise_level"]) if raw.get("noise_level") is not None else None,
        abstain=bool(raw.get("abstain", False)),
        low_confidence=bool(raw.get("low_confidence", False)),
        confirmation_needed=bool(raw.get("confirmation_needed", False)),
        preferred_horizon=str(raw["preferred_horizon"]) if raw.get("preferred_horizon") is not None else None,
        momentum_persistence=(
            _decimal(raw["momentum_persistence"]) if raw.get("momentum_persistence") is not None else None
        ),
        direction_flip_rate=(
            _decimal(raw["direction_flip_rate"]) if raw.get("direction_flip_rate") is not None else None
        ),
        structure_quality=(
            _decimal(raw["structure_quality"]) if raw.get("structure_quality") is not None else None
        ),
        recent_false_positive_rate_5m=(
            _decimal(raw["recent_false_positive_rate_5m"])
            if raw.get("recent_false_positive_rate_5m") is not None
            else None
        ),
        horizons=raw.get("horizons") if isinstance(raw.get("horizons"), dict) else None,
        weakening_factors=tuple(str(item) for item in raw.get("weakening_factors", [])),
    )


def _empty_ai_feature_summary() -> AISignalFeatureSummaryRecord:
    """Return a neutral compact AI feature summary."""

    return AISignalFeatureSummaryRecord(
        candle_count=0,
        close_price=Decimal("0"),
        volatility_pct=None,
        momentum=None,
        volume_change_pct=None,
        volume_spike_ratio=None,
        spread_ratio=None,
        microstructure_healthy=False,
        regime=None,
        noise_level=None,
        abstain=False,
        low_confidence=False,
        confirmation_needed=False,
        preferred_horizon=None,
        momentum_persistence=None,
        direction_flip_rate=None,
        structure_quality=None,
        recent_false_positive_rate_5m=None,
        horizons=None,
        weakening_factors=(),
    )


def _serialize_ai_feature_summary(snapshot: AISignalSnapshot) -> str:
    """Serialize the persisted AI feature summary."""

    feature_vector = snapshot.feature_vector
    payload = {
        "candle_count": feature_vector.candle_count,
        "close_price": str(feature_vector.close_price),
        "volatility_pct": (
            str(feature_vector.volatility_pct) if feature_vector.volatility_pct is not None else None
        ),
        "momentum": str(feature_vector.momentum) if feature_vector.momentum is not None else None,
        "volume_change_pct": (
            str(feature_vector.volume_change_pct) if feature_vector.volume_change_pct is not None else None
        ),
        "volume_spike_ratio": (
            str(feature_vector.volume_spike_ratio) if feature_vector.volume_spike_ratio is not None else None
        ),
        "spread_ratio": str(feature_vector.spread_ratio) if feature_vector.spread_ratio is not None else None,
        "microstructure_healthy": feature_vector.microstructure_healthy,
        "regime": snapshot.regime,
        "noise_level": snapshot.noise_level,
        "abstain": snapshot.abstain,
        "low_confidence": snapshot.low_confidence,
        "confirmation_needed": snapshot.confirmation_needed,
        "preferred_horizon": snapshot.preferred_horizon,
        "momentum_persistence": (
            str(feature_vector.momentum_persistence) if feature_vector.momentum_persistence is not None else None
        ),
        "direction_flip_rate": (
            str(feature_vector.direction_flip_rate) if feature_vector.direction_flip_rate is not None else None
        ),
        "structure_quality": (
            str(feature_vector.structure_quality) if feature_vector.structure_quality is not None else None
        ),
        "recent_false_positive_rate_5m": (
            str(feature_vector.recent_false_positive_rate_5m)
            if feature_vector.recent_false_positive_rate_5m is not None
            else None
        ),
        "weakening_factors": list(snapshot.weakening_factors),
        "horizons": {
            item.horizon: {
                "bias": item.bias,
                "confidence": item.confidence,
                "suggested_action": item.suggested_action,
                "abstain": item.abstain,
                "confirmation_needed": item.confirmation_needed,
                "explanation": item.explanation,
            }
            for item in snapshot.horizon_signals
        },
    }
    return json.dumps(payload, sort_keys=True)


def _ai_signal_materially_changed(
    latest_snapshot: AISignalSnapshotRecord,
    next_snapshot: AISignalSnapshotRecord,
) -> bool:
    """Return whether an AI advisory snapshot materially changed."""

    return (
        latest_snapshot.bias != next_snapshot.bias
        or latest_snapshot.confidence != next_snapshot.confidence
        or latest_snapshot.entry_signal != next_snapshot.entry_signal
        or latest_snapshot.exit_signal != next_snapshot.exit_signal
        or latest_snapshot.suggested_action != next_snapshot.suggested_action
        or latest_snapshot.explanation != next_snapshot.explanation
        or latest_snapshot.feature_summary != next_snapshot.feature_summary
    )


def _start_of_day(value: date) -> datetime:
    """Return the UTC start datetime for a date."""

    return datetime.combine(value, time.min, tzinfo=UTC)


def _next_day(value: date) -> datetime:
    """Return the UTC start datetime for the following date."""

    return _start_of_day(value) + timedelta(days=1)


def _drawdown_pct(drawdown: Decimal, peak_equity: Decimal) -> Decimal:
    """Return drawdown as a fraction of the running peak."""

    if peak_equity <= Decimal("0"):
        return Decimal("0")
    return drawdown / peak_equity


def _is_optional_schema_error(error: sqlite3.Error) -> bool:
    """Return whether a SQLite error points to missing optional AI/evaluation schema."""

    message = str(error).lower()
    return (
        "no such table" in message
        or "no such column" in message
        or "has no column named" in message
    )


class StorageRepository:
    """Paper-mode SQLite repository."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._connection = create_db_connection(database_url)
        self._optional_storage_degraded = False
        self._optional_storage_message: str | None = None

    def close(self) -> None:
        """Close the underlying SQLite connection."""

        self._connection.close()

    def _open_connection(self) -> sqlite3.Connection:
        """Open a fresh SQLite connection for an isolated operation."""

        return create_db_connection(self._database_url)

    @contextmanager
    def _connection_scope(self) -> Iterator[sqlite3.Connection]:
        """Yield a fresh SQLite connection for one repository operation."""

        connection = self._open_connection()
        try:
            yield connection
        finally:
            connection.close()

    @property
    def optional_storage_degraded(self) -> bool:
        """Return whether optional AI/evaluation storage access has degraded."""

        return self._optional_storage_degraded

    @property
    def optional_storage_message(self) -> str | None:
        """Return the latest optional storage degradation message, if any."""

        return self._optional_storage_message

    def _mark_optional_storage_degraded(self, message: str) -> None:
        """Record that optional AI/evaluation storage access degraded."""

        self._optional_storage_degraded = True
        self._optional_storage_message = message

    def record_persistence_warning(self, message: str) -> None:
        """Expose a friendly persistence warning to runtime and API callers."""

        self._mark_optional_storage_degraded(message)

    def clear_all(self) -> None:
        """Delete all persisted paper-session rows."""

        connection = self._open_connection()
        try:
            with connection:
                for table_name in (
                    "trades",
                    "fills",
                    "positions_snapshots",
                    "pnl_snapshots",
                    "runner_events",
                    "ai_signal_snapshots",
                    "market_candle_snapshots",
                    "runtime_session_state",
                    "paper_broker_state",
                    "paper_broker_positions",
                    "profile_tuning_sets",
                    "paper_session_runs",
                ):
                    try:
                        connection.execute(f"DELETE FROM {table_name}")
                    except sqlite3.OperationalError as exc:
                        if not _is_optional_schema_error(exc):
                            raise
                        self._mark_optional_storage_degraded(f"Optional storage table {table_name} is unavailable.")
                        LOGGER.warning("Skipping clear for missing table %s: %s", table_name, exc)
        finally:
            connection.close()

    def upsert_runtime_session_state(
        self,
        *,
        state: str,
        mode: str,
        symbol: str | None,
        session_id: str | None,
        started_at: datetime | None,
        last_event_time: datetime | None,
        last_error: str | None,
        trading_profile: str = "balanced",
        tuning_version_id: str | None = None,
        baseline_tuning_version_id: str | None = None,
    ) -> None:
        """Persist the backend-owned runtime session state."""

        connection = self._open_connection()
        try:
            with connection:
                connection.execute(
                """
                INSERT INTO runtime_session_state (
                    singleton_id, state, mode, trading_profile, symbol, session_id, started_at, last_event_time, last_error,
                    tuning_version_id, baseline_tuning_version_id
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(singleton_id) DO UPDATE SET
                    state = excluded.state,
                    mode = excluded.mode,
                    trading_profile = excluded.trading_profile,
                    symbol = excluded.symbol,
                    session_id = excluded.session_id,
                    started_at = excluded.started_at,
                    last_event_time = excluded.last_event_time,
                    last_error = excluded.last_error,
                    tuning_version_id = excluded.tuning_version_id,
                    baseline_tuning_version_id = excluded.baseline_tuning_version_id
                """,
                (
                    state,
                    mode,
                    trading_profile,
                    symbol,
                    session_id,
                    started_at.isoformat() if started_at is not None else None,
                    last_event_time.isoformat() if last_event_time is not None else None,
                    last_error,
                    tuning_version_id,
                    baseline_tuning_version_id,
                ),
            )
        finally:
            connection.close()

    def get_runtime_session_state(self) -> RuntimeSessionRecord | None:
        """Return the persisted backend-owned runtime session state."""

        with self._connection_scope() as connection:
            row = connection.execute(
                """
                SELECT state, mode, trading_profile, symbol, session_id, started_at, last_event_time, last_error,
                       tuning_version_id, baseline_tuning_version_id
                FROM runtime_session_state
                WHERE singleton_id = 1
                """
            ).fetchone()
        if row is None:
            return None
        return RuntimeSessionRecord(
            state=row["state"],
            mode=row["mode"],
            trading_profile=row["trading_profile"] or "balanced",
            symbol=row["symbol"],
            session_id=row["session_id"],
            started_at=_safe_datetime(row["started_at"]),
            last_event_time=_safe_datetime(row["last_event_time"]),
            last_error=row["last_error"],
            tuning_version_id=row["tuning_version_id"],
            baseline_tuning_version_id=row["baseline_tuning_version_id"],
        )

    def clear_runtime_session_state(self) -> None:
        """Clear any persisted runtime recovery state."""

        connection = self._open_connection()
        try:
            with connection:
                connection.execute("DELETE FROM runtime_session_state")
        finally:
            connection.close()

    def create_profile_tuning_set(
        self,
        *,
        symbol: str | None,
        profile: str,
        config_json: str,
        baseline_config_json: str,
        baseline_version_id: str | None,
        reason: str,
    ) -> ProfileTuningSetRecord:
        """Persist a paper-only tuning set for explicit later application."""

        version_id = f"tune_{uuid4().hex[:12]}"
        created_at = datetime.now(tz=UTC)
        connection = self._open_connection()
        try:
            with connection:
                connection.execute(
                    """
                    UPDATE profile_tuning_sets
                    SET status = 'superseded'
                    WHERE status = 'pending' AND profile = ? AND (
                        (symbol IS NULL AND ? IS NULL) OR symbol = ?
                    )
                    """,
                    (profile, symbol, symbol),
                )
                connection.execute(
                    """
                    INSERT INTO profile_tuning_sets (
                        version_id, symbol, profile, status, config_json, baseline_config_json,
                        created_at, applied_at, baseline_version_id, reason
                    ) VALUES (?, ?, ?, 'pending', ?, ?, ?, NULL, ?, ?)
                    """,
                    (
                        version_id,
                        symbol,
                        profile,
                        config_json,
                        baseline_config_json,
                        created_at.isoformat(),
                        baseline_version_id,
                        reason,
                    ),
                )
        finally:
            connection.close()
        return ProfileTuningSetRecord(
            version_id=version_id,
            symbol=symbol,
            profile=profile,
            status="pending",
            config_json=config_json,
            baseline_config_json=baseline_config_json,
            created_at=created_at,
            applied_at=None,
            baseline_version_id=baseline_version_id,
            reason=reason,
        )

    def get_latest_profile_tuning_set(
        self,
        *,
        symbol: str | None,
        profile: str,
        status: str | None = None,
    ) -> ProfileTuningSetRecord | None:
        """Return the latest persisted tuning set for one symbol/profile scope."""

        query = """
            SELECT version_id, symbol, profile, status, config_json, baseline_config_json,
                   created_at, applied_at, baseline_version_id, reason
            FROM profile_tuning_sets
            WHERE profile = ? AND ((symbol IS NULL AND ? IS NULL) OR symbol = ?)
        """
        params: list[Any] = [profile, symbol, symbol]
        if status is not None:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT 1"
        with self._connection_scope() as connection:
            row = connection.execute(query, tuple(params)).fetchone()
        if row is None:
            return None
        return ProfileTuningSetRecord(
            version_id=row["version_id"],
            symbol=row["symbol"],
            profile=row["profile"],
            status=row["status"],
            config_json=row["config_json"],
            baseline_config_json=row["baseline_config_json"],
            created_at=datetime.fromisoformat(row["created_at"]),
            applied_at=_safe_datetime(row["applied_at"]),
            baseline_version_id=row["baseline_version_id"],
            reason=row["reason"],
        )

    def get_profile_tuning_set_by_version(self, version_id: str) -> ProfileTuningSetRecord | None:
        """Return one persisted tuning set by version id."""

        with self._connection_scope() as connection:
            row = connection.execute(
                """
                SELECT version_id, symbol, profile, status, config_json, baseline_config_json,
                       created_at, applied_at, baseline_version_id, reason
                FROM profile_tuning_sets
                WHERE version_id = ?
                """,
                (version_id,),
            ).fetchone()
        if row is None:
            return None
        return ProfileTuningSetRecord(
            version_id=row["version_id"],
            symbol=row["symbol"],
            profile=row["profile"],
            status=row["status"],
            config_json=row["config_json"],
            baseline_config_json=row["baseline_config_json"],
            created_at=datetime.fromisoformat(row["created_at"]),
            applied_at=_safe_datetime(row["applied_at"]),
            baseline_version_id=row["baseline_version_id"],
            reason=row["reason"],
        )

    def mark_profile_tuning_applied(self, version_id: str, *, applied_at: datetime) -> None:
        """Mark a pending tuning set as applied."""

        connection = self._open_connection()
        try:
            with connection:
                connection.execute(
                    """
                    UPDATE profile_tuning_sets
                    SET status = 'applied', applied_at = ?
                    WHERE version_id = ?
                    """,
                    (applied_at.isoformat(), version_id),
                )
        finally:
            connection.close()

    def start_paper_session_run(
        self,
        *,
        session_id: str,
        symbol: str,
        trading_profile: str,
        tuning_version_id: str | None,
        baseline_tuning_version_id: str | None,
        started_at: datetime,
    ) -> None:
        """Persist one paper session run for later before/after comparison."""

        connection = self._open_connection()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO paper_session_runs (
                        session_id, symbol, trading_profile, tuning_version_id,
                        baseline_tuning_version_id, started_at, ended_at
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL)
                    ON CONFLICT(session_id) DO UPDATE SET
                        symbol = excluded.symbol,
                        trading_profile = excluded.trading_profile,
                        tuning_version_id = excluded.tuning_version_id,
                        baseline_tuning_version_id = excluded.baseline_tuning_version_id,
                        started_at = excluded.started_at
                    """,
                    (
                        session_id,
                        symbol,
                        trading_profile,
                        tuning_version_id,
                        baseline_tuning_version_id,
                        started_at.isoformat(),
                    ),
                )
        finally:
            connection.close()

    def finish_paper_session_run(self, *, session_id: str, ended_at: datetime) -> None:
        """Mark a persisted paper session as finished."""

        connection = self._open_connection()
        try:
            with connection:
                connection.execute(
                    "UPDATE paper_session_runs SET ended_at = ? WHERE session_id = ?",
                    (ended_at.isoformat(), session_id),
                )
        finally:
            connection.close()

    def get_paper_session_runs(
        self,
        *,
        symbol: str | None = None,
        trading_profile: str | None = None,
        tuning_version_id: str | None = None,
        baseline_tuning_version_id: str | None = None,
        session_id: str | None = None,
    ) -> list[PaperSessionRunRecord]:
        """Return persisted paper session runs with optional filters."""

        query = """
            SELECT session_id, symbol, trading_profile, tuning_version_id, baseline_tuning_version_id,
                   started_at, ended_at
            FROM paper_session_runs
            WHERE 1 = 1
        """
        params: list[Any] = []
        if symbol is not None:
            query += " AND symbol = ?"
            params.append(symbol)
        if trading_profile is not None:
            query += " AND trading_profile = ?"
            params.append(trading_profile)
        if tuning_version_id is not None:
            query += " AND tuning_version_id = ?"
            params.append(tuning_version_id)
        if baseline_tuning_version_id is not None:
            query += " AND baseline_tuning_version_id = ?"
            params.append(baseline_tuning_version_id)
        if session_id is not None:
            query += " AND session_id = ?"
            params.append(session_id)
        query += " ORDER BY started_at ASC"
        with self._connection_scope() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [
            PaperSessionRunRecord(
                session_id=row["session_id"],
                symbol=row["symbol"],
                trading_profile=row["trading_profile"],
                tuning_version_id=row["tuning_version_id"],
                baseline_tuning_version_id=row["baseline_tuning_version_id"],
                started_at=datetime.fromisoformat(row["started_at"]),
                ended_at=_safe_datetime(row["ended_at"]),
            )
            for row in rows
        ]

    def upsert_paper_broker_state(
        self,
        *,
        balances: dict[str, Decimal],
        positions: dict[str, Position],
        realized_pnl: Decimal,
        snapshot_time: datetime,
    ) -> None:
        """Persist paper broker balances and open positions for restart recovery."""

        balances_json = json.dumps(
            {asset.upper(): str(balance) for asset, balance in balances.items()},
            sort_keys=True,
        )
        connection = self._open_connection()
        try:
            with connection:
                connection.execute(
                """
                INSERT INTO paper_broker_state (
                    singleton_id, balances_json, realized_pnl, snapshot_time
                ) VALUES (1, ?, ?, ?)
                ON CONFLICT(singleton_id) DO UPDATE SET
                    balances_json = excluded.balances_json,
                    realized_pnl = excluded.realized_pnl,
                    snapshot_time = excluded.snapshot_time
                """,
                (
                    balances_json,
                    str(realized_pnl),
                    snapshot_time.isoformat(),
                ),
            )
                connection.execute("DELETE FROM paper_broker_positions")
                for symbol, position in positions.items():
                    connection.execute(
                    """
                    INSERT INTO paper_broker_positions (
                        symbol, quantity, avg_entry_price, realized_pnl, quote_asset, snapshot_time
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        symbol.upper(),
                        str(position.quantity),
                        str(position.avg_entry_price),
                        str(position.realized_pnl),
                        position.quote_asset,
                        snapshot_time.isoformat(),
                    ),
                )
        finally:
            connection.close()

    def get_paper_broker_state(self) -> PaperBrokerStateRecord | None:
        """Return persisted paper broker recovery state."""

        with self._connection_scope() as connection:
            row = connection.execute(
                """
                SELECT balances_json, realized_pnl, snapshot_time
                FROM paper_broker_state
                WHERE singleton_id = 1
                """
            ).fetchone()
            if row is None:
                return None
            try:
                raw_balances = json.loads(row["balances_json"])
                balances = {
                    str(asset).upper(): _decimal(value)
                    for asset, value in dict(raw_balances).items()
                }
            except (TypeError, ValueError, json.JSONDecodeError):
                LOGGER.warning("Ignoring corrupt persisted paper broker balances during recovery.")
                return None

            snapshot_time = _safe_datetime(row["snapshot_time"])
            if snapshot_time is None:
                LOGGER.warning("Ignoring corrupt persisted paper broker snapshot time during recovery.")
                return None

            position_rows = connection.execute(
                """
                SELECT symbol, quantity, avg_entry_price, realized_pnl, quote_asset, snapshot_time
                FROM paper_broker_positions
                ORDER BY symbol ASC
                """
            ).fetchall()
        positions: list[PositionSnapshotRecord] = []
        for position_row in position_rows:
            position_snapshot_time = _safe_datetime(position_row["snapshot_time"])
            if position_snapshot_time is None:
                LOGGER.warning(
                    "Skipping corrupt persisted paper broker position timestamp for %s.",
                    position_row["symbol"],
                )
                continue
            positions.append(
                PositionSnapshotRecord(
                    symbol=position_row["symbol"],
                    quantity=_decimal(position_row["quantity"]),
                    avg_entry_price=_decimal(position_row["avg_entry_price"]),
                    realized_pnl=_decimal(position_row["realized_pnl"]),
                    quote_asset=position_row["quote_asset"],
                    snapshot_time=position_snapshot_time,
                )
            )
        return PaperBrokerStateRecord(
            balances=balances,
            positions=positions,
            realized_pnl=_decimal(row["realized_pnl"]),
            snapshot_time=snapshot_time,
        )

    def clear_paper_broker_state(self) -> None:
        """Clear persisted paper broker recovery state."""

        connection = self._open_connection()
        try:
            with connection:
                connection.execute("DELETE FROM paper_broker_state")
                connection.execute("DELETE FROM paper_broker_positions")
        finally:
            connection.close()

    def insert_market_candle_snapshot(self, candle: Candle) -> None:
        """Persist a closed candle for later AI outcome validation."""

        if not candle.is_closed:
            return
        try:
            connection = self._open_connection()
            with connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO market_candle_snapshots (
                        symbol, timeframe, open_time, close_time, close_price, event_time
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        candle.symbol.upper(),
                        candle.timeframe,
                        candle.open_time.isoformat(),
                        candle.close_time.isoformat(),
                        str(candle.close),
                        candle.event_time.isoformat(),
                    ),
                )
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Closed-candle outcome storage is unavailable.")
            LOGGER.warning("Skipping market candle snapshot persistence due to schema issue: %s", exc)
        finally:
            if "connection" in locals():
                connection.close()

    def insert_ai_signal_snapshot(self, snapshot: AISignalSnapshot) -> bool:
        """Persist an AI advisory snapshot when it materially changed."""

        connection = self._open_connection()
        try:
            with connection:
                try:
                    row = connection.execute(
                        """
                        SELECT symbol, snapshot_time, bias, confidence, entry_signal, exit_signal,
                               suggested_action, explanation, feature_summary_json
                        FROM ai_signal_snapshots
                        WHERE symbol = ?
                        ORDER BY snapshot_time DESC
                        LIMIT 1
                        """,
                        (snapshot.symbol.upper(),),
                    ).fetchone()
                    latest_snapshot = (
                        AISignalSnapshotRecord(
                            symbol=row["symbol"],
                            timestamp=datetime.fromisoformat(row["snapshot_time"]),
                            bias=row["bias"],
                            confidence=int(row["confidence"]),
                            entry_signal=bool(row["entry_signal"]),
                            exit_signal=bool(row["exit_signal"]),
                            suggested_action=row["suggested_action"],
                            explanation=row["explanation"],
                            feature_summary=_parse_ai_feature_summary(row["feature_summary_json"]),
                        )
                        if row is not None
                        else None
                    )
                    next_feature_summary = _parse_ai_feature_summary(_serialize_ai_feature_summary(snapshot))
                    next_snapshot = AISignalSnapshotRecord(
                        symbol=snapshot.symbol.upper(),
                        timestamp=snapshot.feature_vector.timestamp,
                        bias=snapshot.bias,
                        confidence=snapshot.confidence,
                        entry_signal=snapshot.entry_signal,
                        exit_signal=snapshot.exit_signal,
                        suggested_action=snapshot.suggested_action,
                        explanation=snapshot.explanation,
                        feature_summary=next_feature_summary,
                    )
                    if latest_snapshot is not None and not _ai_signal_materially_changed(latest_snapshot, next_snapshot):
                        return False

                    connection.execute(
                        """
                        INSERT INTO ai_signal_snapshots (
                            symbol, snapshot_time, bias, confidence, entry_signal, exit_signal,
                            suggested_action, explanation, feature_summary_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            next_snapshot.symbol,
                            next_snapshot.timestamp.isoformat(),
                            next_snapshot.bias,
                            next_snapshot.confidence,
                            int(next_snapshot.entry_signal),
                            int(next_snapshot.exit_signal),
                            next_snapshot.suggested_action,
                            next_snapshot.explanation,
                            _serialize_ai_feature_summary(snapshot),
                        ),
                    )
                except sqlite3.OperationalError as exc:
                    if not _is_optional_schema_error(exc):
                        raise
                    self._mark_optional_storage_degraded("AI advisory snapshot storage is unavailable.")
                    LOGGER.warning("Skipping AI signal snapshot persistence due to schema issue: %s", exc)
                    return False
        finally:
            connection.close()
        return True

    def get_latest_ai_signal(self, symbol: str) -> AISignalSnapshotRecord | None:
        """Return the latest persisted AI advisory snapshot for a symbol."""

        try:
            with self._connection_scope() as connection:
                row = connection.execute(
                    """
                    SELECT symbol, snapshot_time, bias, confidence, entry_signal, exit_signal,
                           suggested_action, explanation, feature_summary_json
                    FROM ai_signal_snapshots
                    WHERE symbol = ?
                    ORDER BY snapshot_time DESC
                    LIMIT 1
                    """,
                    (symbol.upper(),),
                ).fetchone()
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("AI advisory snapshot storage is unavailable.")
            LOGGER.warning("Failed to read latest AI signal due to schema issue: %s", exc)
            return None
        if row is None:
            return None
        return AISignalSnapshotRecord(
            symbol=row["symbol"],
            timestamp=datetime.fromisoformat(row["snapshot_time"]),
            bias=row["bias"],
            confidence=int(row["confidence"]),
            entry_signal=bool(row["entry_signal"]),
            exit_signal=bool(row["exit_signal"]),
            suggested_action=row["suggested_action"],
            explanation=row["explanation"],
            feature_summary=_parse_ai_feature_summary(row["feature_summary_json"]),
        )

    def get_ai_signal_history(
        self,
        *,
        symbol: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[AISignalSnapshotRecord]:
        """Return persisted AI advisory history for one symbol."""

        query = """
            SELECT symbol, snapshot_time, bias, confidence, entry_signal, exit_signal,
                   suggested_action, explanation, feature_summary_json
            FROM ai_signal_snapshots
            WHERE symbol = ?
        """
        params: list[Any] = [symbol.upper()]
        query, params = self._apply_date_filters(
            query=query,
            params=params,
            start_date=start_date,
            end_date=end_date,
            timestamp_column="snapshot_time",
        )
        query += " ORDER BY snapshot_time DESC"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend((limit, offset))
        try:
            with self._connection_scope() as connection:
                rows = connection.execute(query, tuple(params)).fetchall()
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("AI advisory history storage is unavailable.")
            LOGGER.warning("Failed to read AI signal history due to schema issue: %s", exc)
            return []
        return [
            AISignalSnapshotRecord(
                symbol=row["symbol"],
                timestamp=datetime.fromisoformat(row["snapshot_time"]),
                bias=row["bias"],
                confidence=int(row["confidence"]),
                entry_signal=bool(row["entry_signal"]),
                exit_signal=bool(row["exit_signal"]),
                suggested_action=row["suggested_action"],
                explanation=row["explanation"],
                feature_summary=_parse_ai_feature_summary(row["feature_summary_json"]),
            )
            for row in rows
        ]

    def count_ai_signal_history(
        self,
        *,
        symbol: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> int:
        """Return the number of persisted AI advisory snapshots for one symbol."""

        query = """
            SELECT COUNT(*) AS row_count
            FROM ai_signal_snapshots
            WHERE symbol = ?
        """
        params: list[Any] = [symbol.upper()]
        query, params = self._apply_date_filters(
            query=query,
            params=params,
            start_date=start_date,
            end_date=end_date,
            timestamp_column="snapshot_time",
        )
        try:
            with self._connection_scope() as connection:
                row = connection.execute(query, tuple(params)).fetchone()
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("AI advisory history storage is unavailable.")
            LOGGER.warning("Failed to count AI signal history due to schema issue: %s", exc)
            return 0
        return int(row["row_count"]) if row is not None else 0

    def get_market_candle_history(
        self,
        *,
        symbol: str,
        timeframe: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[MarketCandleSnapshotRecord]:
        """Return persisted closed-candle history for one symbol."""

        query = """
            SELECT symbol, timeframe, open_time, close_time, close_price, event_time
            FROM market_candle_snapshots
            WHERE symbol = ?
        """
        params: list[Any] = [symbol.upper()]
        if timeframe is not None:
            query += " AND timeframe = ?"
            params.append(timeframe)
        query, params = self._apply_date_filters(
            query=query,
            params=params,
            start_date=start_date,
            end_date=end_date,
            timestamp_column="close_time",
        )
        query += " ORDER BY close_time ASC"
        try:
            with self._connection_scope() as connection:
                rows = connection.execute(query, tuple(params)).fetchall()
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Closed-candle outcome storage is unavailable.")
            LOGGER.warning("Failed to read market candle history due to schema issue: %s", exc)
            return []
        return [
            MarketCandleSnapshotRecord(
                symbol=row["symbol"],
                timeframe=row["timeframe"],
                open_time=datetime.fromisoformat(row["open_time"]),
                close_time=datetime.fromisoformat(row["close_time"]),
                close_price=_decimal(row["close_price"]),
                event_time=datetime.fromisoformat(row["event_time"]),
            )
            for row in rows
        ]

    def insert_trade(
        self,
        *,
        fill_result: FillResult,
        risk_decision: RiskDecision,
        approved_quantity: Decimal,
        event_time: datetime,
        execution_source: str = "auto",
        trading_profile: str = "balanced",
        session_id: str | None = None,
        tuning_version_id: str | None = None,
    ) -> None:
        """Persist a trade record."""

        connection = self._open_connection()
        try:
            with connection:
                connection.execute(
                """
                INSERT INTO trades (
                    order_id, symbol, side, requested_quantity, approved_quantity, filled_quantity,
                    status, risk_decision, reason_codes, fill_price, realized_pnl, quote_balance, event_time,
                    execution_source, trading_profile, session_id, tuning_version_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fill_result.order_id,
                    fill_result.symbol,
                    fill_result.side,
                    str(fill_result.requested_quantity),
                    str(approved_quantity),
                    str(fill_result.filled_quantity),
                    fill_result.status,
                    risk_decision.decision,
                    json.dumps(risk_decision.reason_codes),
                    str(fill_result.fill_price),
                    str(fill_result.realized_pnl),
                    str(fill_result.quote_balance),
                    event_time.isoformat(),
                    execution_source,
                    trading_profile,
                    session_id,
                    tuning_version_id,
                ),
            )
        finally:
            connection.close()

    def insert_fill(
        self,
        fill_result: FillResult,
        event_time: datetime,
        *,
        execution_source: str = "auto",
        trading_profile: str = "balanced",
        session_id: str | None = None,
        tuning_version_id: str | None = None,
    ) -> None:
        """Persist a fill row for executed orders."""

        connection = self._open_connection()
        try:
            with connection:
                connection.execute(
                """
                INSERT INTO fills (
                    order_id, symbol, side, filled_quantity, fill_price, fee_paid,
                    realized_pnl, quote_balance, event_time, execution_source, trading_profile, session_id, tuning_version_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fill_result.order_id,
                    fill_result.symbol,
                    fill_result.side,
                    str(fill_result.filled_quantity),
                    str(fill_result.fill_price),
                    str(fill_result.fee_paid),
                    str(fill_result.realized_pnl),
                    str(fill_result.quote_balance),
                    event_time.isoformat(),
                    execution_source,
                    trading_profile,
                    session_id,
                    tuning_version_id,
                ),
            )
        finally:
            connection.close()

    def insert_position_snapshot(self, position: Position | None, event_time: datetime, symbol: str) -> None:
        """Persist a position snapshot for the current cycle."""

        quantity = Decimal("0")
        avg_entry_price = Decimal("0")
        realized_pnl = Decimal("0")
        quote_asset = "USDT"
        if position is not None:
            quantity = position.quantity
            avg_entry_price = position.avg_entry_price
            realized_pnl = position.realized_pnl
            quote_asset = position.quote_asset

        connection = self._open_connection()
        try:
            with connection:
                connection.execute(
                """
                INSERT INTO positions_snapshots (
                    symbol, quantity, avg_entry_price, realized_pnl, quote_asset, snapshot_time
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    str(quantity),
                    str(avg_entry_price),
                    str(realized_pnl),
                    quote_asset,
                    event_time.isoformat(),
                ),
            )
        finally:
            connection.close()

    def insert_pnl_snapshot(
        self,
        *,
        snapshot_time: datetime,
        equity: Decimal,
        total_pnl: Decimal,
        realized_pnl: Decimal,
        cash_balance: Decimal,
    ) -> None:
        """Persist a PnL snapshot."""

        connection = self._open_connection()
        try:
            with connection:
                connection.execute(
                """
                INSERT INTO pnl_snapshots (
                    snapshot_time, equity, total_pnl, realized_pnl, cash_balance
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    snapshot_time.isoformat(),
                    str(equity),
                    str(total_pnl),
                    str(realized_pnl),
                    str(cash_balance),
                ),
            )
        finally:
            connection.close()

    def insert_event(
        self,
        *,
        event_type: str,
        symbol: str,
        message: str,
        payload: dict[str, Any],
        event_time: datetime,
    ) -> None:
        """Persist a runner event."""

        connection = self._open_connection()
        try:
            with connection:
                connection.execute(
                """
                INSERT INTO runner_events (
                    event_type, symbol, message, payload_json, event_time
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event_type,
                    symbol,
                    message,
                    json.dumps(payload, default=str, sort_keys=True),
                    event_time.isoformat(),
                ),
            )
        finally:
            connection.close()

    def _apply_history_filters(
        self,
        *,
        query: str,
        params: list[Any],
        symbol: str | None,
        start_date: date | None,
        end_date: date | None,
        timestamp_column: str,
    ) -> tuple[str, list[Any]]:
        """Apply common symbol and date filters to a history query."""

        if symbol is not None:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        return self._apply_date_filters(
            query=query,
            params=params,
            start_date=start_date,
            end_date=end_date,
            timestamp_column=timestamp_column,
        )

    def _apply_date_filters(
        self,
        *,
        query: str,
        params: list[Any],
        start_date: date | None,
        end_date: date | None,
        timestamp_column: str,
    ) -> tuple[str, list[Any]]:
        """Apply common date filters to a history query."""

        if start_date is not None:
            query += f" AND {timestamp_column} >= ?"
            params.append(_start_of_day(start_date).isoformat())
        if end_date is not None:
            query += f" AND {timestamp_column} < ?"
            params.append(_next_day(end_date).isoformat())
        return query, params

    def get_trade_history(
        self,
        *,
        symbol: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[TradeRecord]:
        """Return persisted trade history, optionally filtered by symbol."""

        query = """
            SELECT order_id, symbol, side, requested_quantity, approved_quantity, filled_quantity,
                   status, risk_decision, reason_codes, fill_price, realized_pnl, quote_balance, event_time,
                   execution_source, trading_profile, session_id, tuning_version_id
            FROM trades
            WHERE 1 = 1
        """
        params: list[Any] = []
        query, params = self._apply_history_filters(
            query=query,
            params=params,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timestamp_column="event_time",
        )
        query += " ORDER BY id ASC"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend((limit, offset))
        with self._connection_scope() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [
            TradeRecord(
                order_id=row["order_id"],
                symbol=row["symbol"],
                side=row["side"],
                requested_quantity=_decimal(row["requested_quantity"]),
                approved_quantity=_decimal(row["approved_quantity"]),
                filled_quantity=_decimal(row["filled_quantity"]),
                status=row["status"],
                risk_decision=row["risk_decision"],
                reason_codes=_parse_reason_codes(row["reason_codes"]),
                fill_price=_decimal(row["fill_price"]),
                realized_pnl=_decimal(row["realized_pnl"]),
                quote_balance=_decimal(row["quote_balance"]),
                event_time=datetime.fromisoformat(row["event_time"]),
                execution_source=row["execution_source"] or "auto",
                trading_profile=row["trading_profile"] or "balanced",
                session_id=row["session_id"],
                tuning_version_id=row["tuning_version_id"],
            )
            for row in rows
        ]

    def count_trades(
        self,
        *,
        symbol: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> int:
        """Return the total number of trades matching the requested filters."""

        query = """
            SELECT COUNT(*) AS row_count
            FROM trades
            WHERE 1 = 1
        """
        params: list[Any] = []
        query, params = self._apply_history_filters(
            query=query,
            params=params,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timestamp_column="event_time",
        )
        with self._connection_scope() as connection:
            row = connection.execute(query, tuple(params)).fetchone()
        return int(row["row_count"]) if row is not None else 0

    def get_daily_pnl(self, day: date | None = None) -> Decimal:
        """Return the latest persisted total PnL for a UTC day."""

        target_day = day or datetime.now(tz=UTC).date()
        with self._connection_scope() as connection:
            rows = connection.execute(
                """
                SELECT total_pnl
                FROM pnl_snapshots
                WHERE date(snapshot_time) = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (target_day.isoformat(),),
            ).fetchall()
        if not rows:
            return Decimal("0")
        return _decimal(rows[0]["total_pnl"])

    def get_pnl_snapshots(self) -> list[PnlSnapshotRecord]:
        """Return persisted PnL snapshots."""

        return self.get_pnl_history_snapshots()

    def get_pnl_history_snapshots(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[PnlSnapshotRecord]:
        """Return persisted PnL snapshots with optional date filtering."""

        query = """
            SELECT snapshot_time, equity, total_pnl, realized_pnl, cash_balance
            FROM pnl_snapshots
            WHERE 1 = 1
        """
        params: list[Any] = []
        query, params = self._apply_date_filters(
            query=query,
            params=params,
            start_date=start_date,
            end_date=end_date,
            timestamp_column="snapshot_time",
        )
        query += " ORDER BY id ASC"
        with self._connection_scope() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [
            PnlSnapshotRecord(
                snapshot_time=datetime.fromisoformat(row["snapshot_time"]),
                equity=_decimal(row["equity"]),
                total_pnl=_decimal(row["total_pnl"]),
                realized_pnl=_decimal(row["realized_pnl"]),
                cash_balance=_decimal(row["cash_balance"]),
            )
            for row in rows
        ]

    def get_equity_history(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[EquityHistoryPoint]:
        """Return persisted equity history points."""

        return [
            EquityHistoryPoint(
                snapshot_time=snapshot.snapshot_time,
                equity=snapshot.equity,
            )
            for snapshot in self.get_pnl_history_snapshots(
                start_date=start_date,
                end_date=end_date,
            )
        ]

    def get_pnl_history(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[PnlHistoryPoint]:
        """Return persisted total and realized PnL history points."""

        return [
            PnlHistoryPoint(
                snapshot_time=snapshot.snapshot_time,
                total_pnl=snapshot.total_pnl,
                realized_pnl=snapshot.realized_pnl,
            )
            for snapshot in self.get_pnl_history_snapshots(
                start_date=start_date,
                end_date=end_date,
            )
        ]

    def get_daily_pnl_history(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[DailyPnlRecord]:
        """Return the latest persisted PnL point for each UTC day."""

        latest_by_day: dict[date, PnlSnapshotRecord] = {}
        for snapshot in self.get_pnl_history_snapshots(
            start_date=start_date,
            end_date=end_date,
        ):
            latest_by_day[snapshot.snapshot_time.date()] = snapshot

        return [
            DailyPnlRecord(
                day=day,
                total_pnl=latest_by_day[day].total_pnl,
                realized_pnl=latest_by_day[day].realized_pnl,
            )
            for day in sorted(latest_by_day)
        ]

    def get_drawdown_summary(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> DrawdownSummary:
        """Return derived drawdown summary and time series from equity history."""

        points: list[DrawdownPoint] = []
        max_drawdown = Decimal("0")
        max_drawdown_pct = Decimal("0")
        running_peak = Decimal("0")

        for snapshot in self.get_pnl_history_snapshots(
            start_date=start_date,
            end_date=end_date,
        ):
            running_peak = max(running_peak, snapshot.equity)
            drawdown = max(running_peak - snapshot.equity, Decimal("0"))
            drawdown_pct = _drawdown_pct(drawdown, running_peak)
            max_drawdown = max(max_drawdown, drawdown)
            max_drawdown_pct = max(max_drawdown_pct, drawdown_pct)
            points.append(
                DrawdownPoint(
                    snapshot_time=snapshot.snapshot_time,
                    equity=snapshot.equity,
                    peak_equity=running_peak,
                    drawdown=drawdown,
                    drawdown_pct=drawdown_pct,
                )
            )

        if not points:
            return DrawdownSummary(
                current_drawdown=Decimal("0"),
                current_drawdown_pct=Decimal("0"),
                max_drawdown=Decimal("0"),
                max_drawdown_pct=Decimal("0"),
                points=[],
            )

        latest_point = points[-1]
        return DrawdownSummary(
            current_drawdown=latest_point.drawdown,
            current_drawdown_pct=latest_point.drawdown_pct,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            points=points,
        )

    def get_latest_pnl_snapshot(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> PnlSnapshotRecord | None:
        """Return the latest persisted PnL snapshot within an optional date range."""

        query = """
            SELECT snapshot_time, equity, total_pnl, realized_pnl, cash_balance
            FROM pnl_snapshots
            WHERE 1 = 1
        """
        params: list[Any] = []
        query, params = self._apply_date_filters(
            query=query,
            params=params,
            start_date=start_date,
            end_date=end_date,
            timestamp_column="snapshot_time",
        )
        query += " ORDER BY id DESC LIMIT 1"
        with self._connection_scope() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        if not rows:
            return None

        row = rows[0]
        return PnlSnapshotRecord(
            snapshot_time=datetime.fromisoformat(row["snapshot_time"]),
            equity=_decimal(row["equity"]),
            total_pnl=_decimal(row["total_pnl"]),
            realized_pnl=_decimal(row["realized_pnl"]),
            cash_balance=_decimal(row["cash_balance"]),
        )

    def get_current_positions(self) -> list[PositionSnapshotRecord]:
        """Return the latest non-zero position snapshot for each symbol."""

        with self._connection_scope() as connection:
            rows = connection.execute(
                """
                SELECT p.symbol, p.quantity, p.avg_entry_price, p.realized_pnl, p.quote_asset, p.snapshot_time
                FROM positions_snapshots AS p
                INNER JOIN (
                    SELECT symbol, MAX(id) AS max_id
                    FROM positions_snapshots
                    GROUP BY symbol
                ) AS latest
                    ON latest.max_id = p.id
                WHERE CAST(p.quantity AS REAL) != 0
                ORDER BY p.symbol ASC
                """
            ).fetchall()
        return [
            PositionSnapshotRecord(
                symbol=row["symbol"],
                quantity=_decimal(row["quantity"]),
                avg_entry_price=_decimal(row["avg_entry_price"]),
                realized_pnl=_decimal(row["realized_pnl"]),
                quote_asset=row["quote_asset"],
                snapshot_time=datetime.fromisoformat(row["snapshot_time"]),
            )
            for row in rows
        ]

    def get_fill_history(
        self,
        *,
        symbol: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[FillRecord]:
        """Return persisted fills."""

        with self._connection_scope() as connection:
            rows = connection.execute(
                *self._build_fill_query(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    limit=limit,
                    offset=offset,
                )
            ).fetchall()
        return [
            FillRecord(
                order_id=row["order_id"],
                symbol=row["symbol"],
                side=row["side"],
                filled_quantity=_decimal(row["filled_quantity"]),
                fill_price=_decimal(row["fill_price"]),
                fee_paid=_decimal(row["fee_paid"]),
                realized_pnl=_decimal(row["realized_pnl"]),
                quote_balance=_decimal(row["quote_balance"]),
                event_time=datetime.fromisoformat(row["event_time"]),
                execution_source=row["execution_source"] or "auto",
                trading_profile=row["trading_profile"] or "balanced",
                session_id=row["session_id"],
                tuning_version_id=row["tuning_version_id"],
            )
            for row in rows
        ]

    def _build_fill_query(
        self,
        *,
        symbol: str | None,
        start_date: date | None,
        end_date: date | None,
        limit: int | None,
        offset: int,
    ) -> tuple[str, tuple[Any, ...]]:
        """Build a filtered fills query."""

        query = """
            SELECT order_id, symbol, side, filled_quantity, fill_price, fee_paid,
                   realized_pnl, quote_balance, event_time, execution_source, trading_profile, session_id, tuning_version_id
            FROM fills
            WHERE 1 = 1
        """
        params: list[Any] = []
        query, params = self._apply_history_filters(
            query=query,
            params=params,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timestamp_column="event_time",
        )
        query += " ORDER BY id ASC"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend((limit, offset))
        return query, tuple(params)

    def count_fills(
        self,
        *,
        symbol: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> int:
        """Return the total number of fills matching the requested filters."""

        query = """
            SELECT COUNT(*) AS row_count
            FROM fills
            WHERE 1 = 1
        """
        params: list[Any] = []
        query, params = self._apply_history_filters(
            query=query,
            params=params,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timestamp_column="event_time",
        )
        with self._connection_scope() as connection:
            row = connection.execute(query, tuple(params)).fetchone()
        return int(row["row_count"]) if row is not None else 0

    def get_runner_events(
        self,
        *,
        symbol: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[RunnerEventRecord]:
        """Return persisted runner events."""

        query = """
            SELECT event_type, symbol, message, payload_json, event_time
            FROM runner_events
            WHERE 1 = 1
        """
        params: list[Any] = []
        query, params = self._apply_history_filters(
            query=query,
            params=params,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timestamp_column="event_time",
        )
        query += " ORDER BY id ASC"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend((limit, offset))
        with self._connection_scope() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [
            RunnerEventRecord(
                event_type=row["event_type"],
                symbol=row["symbol"],
                message=row["message"],
                payload_json=row["payload_json"],
                event_time=datetime.fromisoformat(row["event_time"]),
            )
            for row in rows
        ]

    def count_runner_events(
        self,
        *,
        symbol: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> int:
        """Return the total number of runner events matching the requested filters."""

        query = """
            SELECT COUNT(*) AS row_count
            FROM runner_events
            WHERE 1 = 1
        """
        params: list[Any] = []
        query, params = self._apply_history_filters(
            query=query,
            params=params,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timestamp_column="event_time",
        )
        with self._connection_scope() as connection:
            row = connection.execute(query, tuple(params)).fetchone()
        return int(row["row_count"]) if row is not None else 0
