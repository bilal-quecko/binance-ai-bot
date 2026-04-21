import sqlite3
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.ai.models import AIFeatureVector, AISignalSnapshot
from app.paper.models import FillResult
from app.risk.models import RiskDecision
from app.storage import StorageRepository


def _db_path(name: str) -> Path:
    base = Path("tests/.tmp_storage")
    base.mkdir(parents=True, exist_ok=True)
    return (base / f"{name}_{uuid4().hex}.sqlite").resolve()


def _ai_snapshot(
    *,
    symbol: str,
    timestamp: datetime,
    bias: str = "bullish",
    confidence: int = 72,
    entry_signal: bool = True,
    exit_signal: bool = False,
    suggested_action: str = "enter",
    explanation: str = "Momentum is improving and volatility is controlled.",
) -> AISignalSnapshot:
    return AISignalSnapshot(
        symbol=symbol,
        bias=bias,
        confidence=confidence,
        entry_signal=entry_signal,
        exit_signal=exit_signal,
        suggested_action=suggested_action,
        explanation=explanation,
        feature_vector=AIFeatureVector(
            symbol=symbol,
            timestamp=timestamp,
            candle_count=5,
            close_price=Decimal("101"),
            ema_fast=Decimal("101"),
            ema_slow=Decimal("100"),
            rsi=Decimal("60"),
            atr=Decimal("1"),
            volatility_pct=Decimal("0.01"),
            momentum=Decimal("0.02"),
            recent_returns=(Decimal("0.01"), Decimal("0.005")),
            wick_body_ratio=Decimal("1.1"),
            upper_wick_ratio=Decimal("0.2"),
            lower_wick_ratio=Decimal("0.1"),
            volume_change_pct=Decimal("0.5"),
            volume_spike_ratio=Decimal("1.4"),
            spread_ratio=Decimal("0.001"),
            order_book_imbalance=Decimal("0.2"),
            microstructure_healthy=True,
        ),
    )


def test_storage_repository_creates_required_tables() -> None:
    db_path = _db_path("create_tables")
    repository = StorageRepository(f"sqlite:///{db_path}")
    repository.close()

    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    finally:
        connection.close()

    table_names = {row[0] for row in rows}
    assert {
        "ai_signal_snapshots",
        "fills",
        "pnl_snapshots",
        "positions_snapshots",
        "runner_events",
        "trades",
    } <= table_names


def test_storage_repository_persists_and_reads_trade_history() -> None:
    db_path = _db_path("trade_history")
    repository = StorageRepository(f"sqlite:///{db_path}")
    event_time = datetime(2024, 3, 9, 16, 0, 0, tzinfo=UTC)

    repository.insert_trade(
        fill_result=FillResult(
            order_id="PAPER-000001",
            status="executed",
            symbol="BTCUSDT",
            side="BUY",
            requested_quantity=Decimal("1"),
            filled_quantity=Decimal("1"),
            fill_price=Decimal("100"),
            fee_paid=Decimal("0.1"),
            realized_pnl=Decimal("0"),
            quote_balance=Decimal("899.9"),
            reason_codes=("EXECUTED",),
            position=None,
        ),
        risk_decision=RiskDecision(
            decision="approve",
            approved_quantity=Decimal("1"),
            reason_codes=("APPROVED",),
        ),
        approved_quantity=Decimal("1"),
        event_time=event_time,
    )
    repository.close()

    reopened = StorageRepository(f"sqlite:///{db_path}")
    try:
        history = reopened.get_trade_history()
    finally:
        reopened.close()

    assert len(history) == 1
    assert history[0].order_id == "PAPER-000001"
    assert history[0].symbol == "BTCUSDT"
    assert history[0].risk_decision == "approve"
    assert history[0].event_time == event_time


def test_storage_repository_tracks_daily_pnl_from_snapshots() -> None:
    db_path = _db_path("daily_pnl")
    repository = StorageRepository(f"sqlite:///{db_path}")
    repository.insert_pnl_snapshot(
        snapshot_time=datetime(2024, 3, 9, 16, 0, 0, tzinfo=UTC),
        equity=Decimal("1000"),
        total_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        cash_balance=Decimal("1000"),
    )
    repository.insert_pnl_snapshot(
        snapshot_time=datetime(2024, 3, 9, 17, 0, 0, tzinfo=UTC),
        equity=Decimal("1015.5"),
        total_pnl=Decimal("15.5"),
        realized_pnl=Decimal("10"),
        cash_balance=Decimal("900"),
    )

    daily_pnl = repository.get_daily_pnl(date(2024, 3, 9))
    snapshots = repository.get_pnl_snapshots()
    repository.close()

    assert daily_pnl == Decimal("15.5")
    assert len(snapshots) == 2
    assert snapshots[-1].equity == Decimal("1015.5")


def test_storage_repository_builds_history_and_drawdown_series() -> None:
    db_path = _db_path("history_series")
    repository = StorageRepository(f"sqlite:///{db_path}")
    snapshots = (
        (datetime(2024, 3, 9, 9, 0, 0, tzinfo=UTC), Decimal("1000"), Decimal("0"), Decimal("0")),
        (datetime(2024, 3, 9, 12, 0, 0, tzinfo=UTC), Decimal("1100"), Decimal("100"), Decimal("50")),
        (datetime(2024, 3, 9, 18, 0, 0, tzinfo=UTC), Decimal("990"), Decimal("-10"), Decimal("-10")),
        (datetime(2024, 3, 10, 10, 0, 0, tzinfo=UTC), Decimal("1200"), Decimal("200"), Decimal("100")),
        (datetime(2024, 3, 10, 15, 0, 0, tzinfo=UTC), Decimal("1140"), Decimal("140"), Decimal("150")),
    )
    for snapshot_time, equity, total_pnl, realized_pnl in snapshots:
        repository.insert_pnl_snapshot(
            snapshot_time=snapshot_time,
            equity=equity,
            total_pnl=total_pnl,
            realized_pnl=realized_pnl,
            cash_balance=equity,
        )

    equity_history = repository.get_equity_history()
    pnl_history = repository.get_pnl_history(start_date=date(2024, 3, 10))
    daily_history = repository.get_daily_pnl_history()
    drawdown = repository.get_drawdown_summary()
    repository.close()

    assert [point.equity for point in equity_history] == [
        Decimal("1000"),
        Decimal("1100"),
        Decimal("990"),
        Decimal("1200"),
        Decimal("1140"),
    ]
    assert [point.total_pnl for point in pnl_history] == [Decimal("200"), Decimal("140")]
    assert [(point.day, point.total_pnl, point.realized_pnl) for point in daily_history] == [
        (date(2024, 3, 9), Decimal("-10"), Decimal("-10")),
        (date(2024, 3, 10), Decimal("140"), Decimal("150")),
    ]
    assert drawdown.max_drawdown == Decimal("110")
    assert drawdown.max_drawdown_pct == Decimal("0.1")
    assert drawdown.current_drawdown == Decimal("60")
    assert drawdown.current_drawdown_pct == Decimal("0.05")


def test_storage_repository_persists_ai_signal_snapshots_and_suppresses_duplicates() -> None:
    db_path = _db_path("ai_signal_snapshots")
    repository = StorageRepository(f"sqlite:///{db_path}")
    first_timestamp = datetime(2024, 3, 9, 16, 0, 0, tzinfo=UTC)
    duplicate_timestamp = datetime(2024, 3, 9, 16, 1, 0, tzinfo=UTC)
    changed_timestamp = datetime(2024, 3, 9, 16, 2, 0, tzinfo=UTC)

    first_inserted = repository.insert_ai_signal_snapshot(
        _ai_snapshot(symbol="BTCUSDT", timestamp=first_timestamp)
    )
    duplicate_inserted = repository.insert_ai_signal_snapshot(
        _ai_snapshot(symbol="BTCUSDT", timestamp=duplicate_timestamp)
    )
    changed_inserted = repository.insert_ai_signal_snapshot(
        _ai_snapshot(
            symbol="BTCUSDT",
            timestamp=changed_timestamp,
            bias="sideways",
            confidence=55,
            entry_signal=False,
            suggested_action="wait",
            explanation="Momentum faded and confirmation is missing.",
        )
    )

    latest_snapshot = repository.get_latest_ai_signal("BTCUSDT")
    history = repository.get_ai_signal_history(symbol="BTCUSDT", limit=10, offset=0)
    total = repository.count_ai_signal_history(symbol="BTCUSDT")
    repository.close()

    assert first_inserted is True
    assert duplicate_inserted is False
    assert changed_inserted is True
    assert latest_snapshot is not None
    assert latest_snapshot.bias == "sideways"
    assert latest_snapshot.timestamp == changed_timestamp
    assert total == 2
    assert [item.bias for item in history] == ["sideways", "bullish"]


def test_storage_repository_filters_ai_signal_history_by_symbol() -> None:
    db_path = _db_path("ai_signal_symbol_history")
    repository = StorageRepository(f"sqlite:///{db_path}")
    repository.insert_ai_signal_snapshot(
        _ai_snapshot(symbol="BTCUSDT", timestamp=datetime(2024, 3, 9, 16, 0, 0, tzinfo=UTC))
    )
    repository.insert_ai_signal_snapshot(
        _ai_snapshot(
            symbol="ETHUSDT",
            timestamp=datetime(2024, 3, 9, 16, 1, 0, tzinfo=UTC),
            bias="bearish",
            confidence=68,
            entry_signal=False,
            exit_signal=True,
            suggested_action="exit",
            explanation="Fast EMA rolled under slow EMA.",
        )
    )

    btc_history = repository.get_ai_signal_history(symbol="BTCUSDT", limit=10, offset=0)
    eth_history = repository.get_ai_signal_history(symbol="ETHUSDT", limit=10, offset=0)
    repository.close()

    assert len(btc_history) == 1
    assert btc_history[0].symbol == "BTCUSDT"
    assert btc_history[0].bias == "bullish"
    assert len(eth_history) == 1
    assert eth_history[0].symbol == "ETHUSDT"
    assert eth_history[0].suggested_action == "exit"
