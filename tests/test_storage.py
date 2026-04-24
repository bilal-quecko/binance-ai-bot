from concurrent.futures import ThreadPoolExecutor
import sqlite3
import threading
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.ai.models import AIFeatureVector, AISignalSnapshot
from app.paper.models import Position
from app.paper.models import FillResult
from app.risk.models import RiskDecision
from app.storage import StorageRepository
from app.storage.db import resolve_sqlite_path


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
    database_url = f"sqlite:///{db_path}"
    repository = StorageRepository(database_url)
    repository.close()

    connection = sqlite3.connect(str(resolve_sqlite_path(database_url)))
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
        "market_candle_snapshots",
        "paper_broker_positions",
        "paper_broker_state",
        "pnl_snapshots",
        "positions_snapshots",
        "runner_events",
        "runtime_session_state",
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


def test_storage_repository_adds_missing_optional_ai_columns_for_old_sqlite_files() -> None:
    db_path = _db_path("legacy_optional_schema")
    repository = StorageRepository(f"sqlite:///{db_path}")
    try:
        repository._connection.execute("DROP TABLE ai_signal_snapshots")
        repository._connection.execute("DROP TABLE market_candle_snapshots")
        repository._connection.execute(
            """
            CREATE TABLE ai_signal_snapshots (
                symbol TEXT NOT NULL,
                snapshot_time TEXT NOT NULL,
                bias TEXT NOT NULL,
                confidence INTEGER NOT NULL,
                entry_signal INTEGER NOT NULL,
                exit_signal INTEGER NOT NULL,
                suggested_action TEXT NOT NULL,
                explanation TEXT NOT NULL
            )
            """
        )
        repository._connection.execute(
            """
            CREATE TABLE market_candle_snapshots (
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                open_time TEXT NOT NULL,
                close_price TEXT NOT NULL
            )
            """
        )
        repository._connection.commit()
    finally:
        repository.close()

    repository = StorageRepository(f"sqlite:///{db_path}")
    try:
        repository.insert_ai_signal_snapshot(
            _ai_snapshot(symbol="BTCUSDT", timestamp=datetime(2024, 3, 9, 16, 0, 0, tzinfo=UTC))
        )
        history = repository.get_ai_signal_history(symbol="BTCUSDT", limit=10, offset=0)
        candle_history = repository.get_market_candle_history(symbol="BTCUSDT")
    finally:
        repository.close()

    assert len(history) == 1
    assert history[0].feature_summary.candle_count == 5
    assert candle_history == []


def test_storage_repository_persists_runtime_session_and_broker_recovery_state() -> None:
    db_path = _db_path("runtime_broker_recovery")
    repository = StorageRepository(f"sqlite:///{db_path}")
    started_at = datetime(2024, 3, 9, 16, 0, 0, tzinfo=UTC)
    last_event_time = datetime(2024, 3, 9, 16, 5, 0, tzinfo=UTC)
    snapshot_time = datetime(2024, 3, 9, 16, 6, 0, tzinfo=UTC)
    repository.upsert_runtime_session_state(
        state="running",
        mode="auto_paper",
        symbol="BTCUSDT",
        session_id="session-001",
        started_at=started_at,
        last_event_time=last_event_time,
        last_error=None,
    )
    repository.upsert_paper_broker_state(
        balances={"USDT": Decimal("9900.5")},
        positions={
            "BTCUSDT": Position(
                symbol="BTCUSDT",
                quantity=Decimal("0.25"),
                avg_entry_price=Decimal("40000"),
                realized_pnl=Decimal("15"),
                quote_asset="USDT",
            )
        },
        realized_pnl=Decimal("15"),
        snapshot_time=snapshot_time,
    )
    repository.close()

    reopened = StorageRepository(f"sqlite:///{db_path}")
    try:
        session_state = reopened.get_runtime_session_state()
        broker_state = reopened.get_paper_broker_state()
    finally:
        reopened.close()

    assert session_state is not None
    assert session_state.state == "running"
    assert session_state.mode == "auto_paper"
    assert session_state.symbol == "BTCUSDT"
    assert session_state.session_id == "session-001"
    assert session_state.started_at == started_at
    assert session_state.last_event_time == last_event_time

    assert broker_state is not None
    assert broker_state.balances == {"USDT": Decimal("9900.5")}
    assert broker_state.realized_pnl == Decimal("15")
    assert broker_state.snapshot_time == snapshot_time
    assert len(broker_state.positions) == 1
    assert broker_state.positions[0].symbol == "BTCUSDT"
    assert broker_state.positions[0].quantity == Decimal("0.25")


def test_storage_repository_ignores_corrupt_broker_recovery_state() -> None:
    db_path = _db_path("runtime_broker_corrupt")
    repository = StorageRepository(f"sqlite:///{db_path}")
    try:
        repository._connection.execute(  # noqa: SLF001 - targeted corrupt-state regression coverage
            """
            INSERT INTO paper_broker_state (singleton_id, balances_json, realized_pnl, snapshot_time)
            VALUES (1, ?, ?, ?)
            """,
            ("not-json", "10", "2024-03-09T16:00:00+00:00"),
        )
        repository._connection.commit()
    finally:
        repository.close()

    reopened = StorageRepository(f"sqlite:///{db_path}")
    try:
        broker_state = reopened.get_paper_broker_state()
    finally:
        reopened.close()

    assert broker_state is None


def test_storage_repository_uses_wal_and_handles_concurrent_runtime_writes() -> None:
    db_path = _db_path("concurrent_runtime_writes")
    repository = StorageRepository(f"sqlite:///{db_path}")
    barrier = threading.Barrier(5)
    errors: list[Exception] = []

    def write_cycle(index: int) -> None:
        try:
            barrier.wait()
            event_time = datetime(2024, 3, 9, 16, index, tzinfo=UTC)
            repository.upsert_runtime_session_state(
                state="running",
                mode="auto_paper",
                symbol="BTCUSDT",
                session_id=f"session-{index}",
                started_at=event_time,
                last_event_time=event_time,
                last_error=None,
            )
            repository.upsert_paper_broker_state(
                balances={"USDT": Decimal("10000") - Decimal(index)},
                positions={},
                realized_pnl=Decimal(index),
                snapshot_time=event_time,
            )
            repository.insert_event(
                event_type="runtime_write",
                symbol="BTCUSDT",
                message=f"write-{index}",
                payload={"index": index},
                event_time=event_time,
            )
        except Exception as exc:  # pragma: no cover - failure path asserted below
            errors.append(exc)

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(write_cycle, index) for index in range(5)]
        for future in futures:
            future.result()

    assert errors == []

    runtime_state = repository.get_runtime_session_state()
    event_count = repository.count_runner_events(symbol="BTCUSDT")
    repository.close()

    assert runtime_state is not None
    assert runtime_state.symbol == "BTCUSDT"
    assert event_count == 5


def test_storage_repository_persists_profile_tuning_and_session_runs() -> None:
    db_path = _db_path("profile_tuning_sessions")
    repository = StorageRepository(f"sqlite:///{db_path}")
    started_at = datetime(2024, 3, 9, 16, 0, tzinfo=UTC)
    try:
        tuning = repository.create_profile_tuning_set(
            symbol="BTCUSDT",
            profile="balanced",
            config_json='{"min_atr_ratio": "0.0003"}',
            baseline_config_json='{"min_atr_ratio": "0.0004"}',
            baseline_version_id=None,
            reason="Loosen the ATR floor slightly.",
        )
        repository.mark_profile_tuning_applied(tuning.version_id, applied_at=started_at)
        repository.start_paper_session_run(
            session_id="session-tuned",
            symbol="BTCUSDT",
            trading_profile="balanced",
            tuning_version_id=tuning.version_id,
            baseline_tuning_version_id=None,
            started_at=started_at,
        )
        repository.finish_paper_session_run(
            session_id="session-tuned",
            ended_at=started_at + timedelta(minutes=15),
        )
    finally:
        repository.close()

    reopened = StorageRepository(f"sqlite:///{db_path}")
    try:
        loaded_tuning = reopened.get_profile_tuning_set_by_version(tuning.version_id)
        session_runs = reopened.get_paper_session_runs(
            symbol="BTCUSDT",
            trading_profile="balanced",
            tuning_version_id=tuning.version_id,
        )
    finally:
        reopened.close()

    assert loaded_tuning is not None
    assert loaded_tuning.status == "applied"
    assert loaded_tuning.baseline_config_json == '{"min_atr_ratio": "0.0004"}'
    assert len(session_runs) == 1
    assert session_runs[0].session_id == "session-tuned"
    assert session_runs[0].ended_at == started_at + timedelta(minutes=15)
