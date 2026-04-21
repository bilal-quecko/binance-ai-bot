"""SQLite repository helpers for paper-mode persistence."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from app.ai.models import AISignalSnapshot
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
    PnlHistoryPoint,
    PnlSnapshotRecord,
    PositionSnapshotRecord,
    RunnerEventRecord,
    TradeRecord,
)


def _decimal(value: Any) -> Decimal:
    """Convert a stored numeric value into Decimal."""

    return Decimal(str(value))


def _parse_reason_codes(value: str) -> tuple[str, ...]:
    """Parse persisted reason codes from JSON."""

    raw = json.loads(value)
    return tuple(str(item) for item in raw)


def _parse_ai_feature_summary(value: str) -> AISignalFeatureSummaryRecord:
    """Parse a compact persisted AI feature summary."""

    raw = json.loads(value)
    return AISignalFeatureSummaryRecord(
        candle_count=int(raw["candle_count"]),
        close_price=_decimal(raw["close_price"]),
        volatility_pct=_decimal(raw["volatility_pct"]) if raw["volatility_pct"] is not None else None,
        momentum=_decimal(raw["momentum"]) if raw["momentum"] is not None else None,
        volume_change_pct=(
            _decimal(raw["volume_change_pct"]) if raw["volume_change_pct"] is not None else None
        ),
        volume_spike_ratio=(
            _decimal(raw["volume_spike_ratio"]) if raw["volume_spike_ratio"] is not None else None
        ),
        spread_ratio=_decimal(raw["spread_ratio"]) if raw["spread_ratio"] is not None else None,
        microstructure_healthy=bool(raw["microstructure_healthy"]),
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


class StorageRepository:
    """Paper-mode SQLite repository."""

    def __init__(self, database_url: str) -> None:
        self._connection = create_db_connection(database_url)

    def close(self) -> None:
        """Close the underlying SQLite connection."""

        self._connection.close()

    def clear_all(self) -> None:
        """Delete all persisted paper-session rows."""

        with self._connection:
            self._connection.execute("DELETE FROM trades")
            self._connection.execute("DELETE FROM fills")
            self._connection.execute("DELETE FROM positions_snapshots")
            self._connection.execute("DELETE FROM pnl_snapshots")
            self._connection.execute("DELETE FROM runner_events")
            self._connection.execute("DELETE FROM ai_signal_snapshots")

    def insert_ai_signal_snapshot(self, snapshot: AISignalSnapshot) -> bool:
        """Persist an AI advisory snapshot when it materially changed."""

        latest_snapshot = self.get_latest_ai_signal(snapshot.symbol)
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

        with self._connection:
            self._connection.execute(
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
        return True

    def get_latest_ai_signal(self, symbol: str) -> AISignalSnapshotRecord | None:
        """Return the latest persisted AI advisory snapshot for a symbol."""

        row = self._connection.execute(
            """
            SELECT symbol, snapshot_time, bias, confidence, entry_signal, exit_signal,
                   suggested_action, explanation, feature_summary_json
            FROM ai_signal_snapshots
            WHERE symbol = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (symbol.upper(),),
        ).fetchone()
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
        query += " ORDER BY id DESC"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend((limit, offset))
        rows = self._connection.execute(query, tuple(params)).fetchall()
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
        row = self._connection.execute(query, tuple(params)).fetchone()
        return int(row["row_count"]) if row is not None else 0

    def insert_trade(
        self,
        *,
        fill_result: FillResult,
        risk_decision: RiskDecision,
        approved_quantity: Decimal,
        event_time: datetime,
    ) -> None:
        """Persist a trade record."""

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO trades (
                    order_id, symbol, side, requested_quantity, approved_quantity, filled_quantity,
                    status, risk_decision, reason_codes, fill_price, realized_pnl, quote_balance, event_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )

    def insert_fill(self, fill_result: FillResult, event_time: datetime) -> None:
        """Persist a fill row for executed orders."""

        with self._connection:
            self._connection.execute(
                """
                INSERT INTO fills (
                    order_id, symbol, side, filled_quantity, fill_price, fee_paid,
                    realized_pnl, quote_balance, event_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                ),
            )

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

        with self._connection:
            self._connection.execute(
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

        with self._connection:
            self._connection.execute(
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

        with self._connection:
            self._connection.execute(
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
                   status, risk_decision, reason_codes, fill_price, realized_pnl, quote_balance, event_time
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
        rows = self._connection.execute(query, tuple(params)).fetchall()
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
        row = self._connection.execute(query, tuple(params)).fetchone()
        return int(row["row_count"]) if row is not None else 0

    def get_daily_pnl(self, day: date | None = None) -> Decimal:
        """Return the latest persisted total PnL for a UTC day."""

        target_day = day or datetime.now(tz=UTC).date()
        rows = self._connection.execute(
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
        rows = self._connection.execute(query, tuple(params)).fetchall()
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

    def get_latest_pnl_snapshot(self) -> PnlSnapshotRecord | None:
        """Return the latest persisted PnL snapshot."""

        rows = self._connection.execute(
            """
            SELECT snapshot_time, equity, total_pnl, realized_pnl, cash_balance
            FROM pnl_snapshots
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchall()
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

        rows = self._connection.execute(
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

        rows = self._connection.execute(
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
                   realized_pnl, quote_balance, event_time
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
        row = self._connection.execute(query, tuple(params)).fetchone()
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
        rows = self._connection.execute(query, tuple(params)).fetchall()
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
        row = self._connection.execute(query, tuple(params)).fetchone()
        return int(row["row_count"]) if row is not None else 0
