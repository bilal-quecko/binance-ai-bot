from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.execution.execution_engine import ExecutionEngine
from app.features.feature_store import FeatureEngine
from app.features.models import FeatureConfig
from app.market_data.candles import Candle
from app.market_data.models import MarketSnapshot
from app.market_data.orderbook import TopOfBook
from app.paper.broker import PaperBroker
from app.risk.limits import RiskEngine
from app.runner import RunnerConfig, StrategyRunner
from app.storage import StorageRepository
from app.strategies.models import TrendFollowingConfig
from app.strategies.trend_following import TrendFollowingStrategy


BASE_TIME = datetime(2024, 3, 9, 16, 0, 0, tzinfo=UTC)


def _db_path() -> Path:
    base = Path("tests/.tmp_storage")
    base.mkdir(parents=True, exist_ok=True)
    return (base / f"runner_{uuid4().hex}.sqlite").resolve()


def build_snapshot(index: int, close_price: str) -> MarketSnapshot:
    close = Decimal(close_price)
    open_time = BASE_TIME + timedelta(minutes=index)
    close_time = open_time + timedelta(minutes=1) - timedelta(milliseconds=1)
    candle = Candle(
        symbol="BTCUSDT",
        timeframe="1m",
        open=close - Decimal("0.5"),
        high=close + Decimal("1"),
        low=close - Decimal("1"),
        close=close,
        volume=Decimal("10"),
        quote_volume=close * Decimal("10"),
        open_time=open_time,
        close_time=close_time,
        event_time=close_time,
        trade_count=100 + index,
        is_closed=True,
    )
    top_of_book = TopOfBook(
        symbol="BTCUSDT",
        bid_price=close - Decimal("0.05"),
        bid_quantity=Decimal("2"),
        ask_price=close + Decimal("0.05"),
        ask_quantity=Decimal("1.5"),
        event_time=close_time,
    )
    return MarketSnapshot(
        symbol="BTCUSDT",
        candle=candle,
        top_of_book=top_of_book,
        last_price=close,
        bid_price=top_of_book.bid_price,
        ask_price=top_of_book.ask_price,
        event_time=close_time,
        received_at=close_time,
    )


def test_strategy_runner_completes_buy_hold_sell_cycle() -> None:
    broker = PaperBroker(initial_balances={"USDT": Decimal("1000")})
    db_path = _db_path()
    repository = StorageRepository(f"sqlite:///{db_path}")
    runner = StrategyRunner(
        feature_engine=FeatureEngine(
            FeatureConfig(
                ema_fast_period=2,
                ema_slow_period=3,
                rsi_period=2,
                atr_period=2,
            )
        ),
        strategy=TrendFollowingStrategy(TrendFollowingConfig()),
        risk_engine=RiskEngine(),
        execution_engine=ExecutionEngine(broker),
        broker=broker,
        storage_repository=repository,
        config=RunnerConfig(
            order_quantity=Decimal("1"),
            risk_per_trade=Decimal("0.01"),
            max_daily_loss=Decimal("0.10"),
            max_open_positions=3,
        ),
    )

    results = runner.run(
        [
            build_snapshot(0, "100"),
            build_snapshot(1, "101"),
            build_snapshot(2, "102"),
            build_snapshot(3, "103"),
            build_snapshot(4, "95"),
        ],
        iterations=5,
    )

    buy_result = results[2]
    hold_result = results[3]
    sell_result = results[4]

    assert len(results) == 5
    assert buy_result.signal.side == "BUY"
    assert buy_result.execution_result is not None
    assert buy_result.execution_result.status == "executed"
    assert hold_result.signal.side == "HOLD"
    assert hold_result.current_position is not None
    assert sell_result.signal.side == "SELL"
    assert sell_result.risk_decision is not None
    assert sell_result.risk_decision.decision == "approve"
    assert sell_result.execution_result is not None
    assert sell_result.execution_result.status == "executed"
    assert sell_result.current_position is None
    assert sell_result.current_pnl == Decimal("-7.19700")
    assert broker.realized_pnl == Decimal("-7.19700")

    repository.close()
    reopened = StorageRepository(f"sqlite:///{db_path}")
    try:
        trade_history = reopened.get_trade_history()
        daily_pnl = reopened.get_daily_pnl(BASE_TIME.date())
        runner_events = reopened.get_runner_events()
    finally:
        reopened.close()

    assert len(trade_history) == 2
    assert trade_history[0].side == "BUY"
    assert trade_history[1].side == "SELL"
    assert daily_pnl == Decimal("-7.19700")
    assert any(event.event_type == "signal_generated" for event in runner_events)


def test_strategy_runner_ignores_duplicate_and_out_of_order_candles_in_cache() -> None:
    broker = PaperBroker(initial_balances={"USDT": Decimal("1000")})
    runner = StrategyRunner(
        feature_engine=FeatureEngine(
            FeatureConfig(
                ema_fast_period=2,
                ema_slow_period=3,
                rsi_period=2,
                atr_period=2,
            )
        ),
        strategy=TrendFollowingStrategy(TrendFollowingConfig()),
        risk_engine=RiskEngine(),
        execution_engine=ExecutionEngine(broker),
        broker=broker,
    )

    first = build_snapshot(0, "100")
    duplicate_newer = build_snapshot(0, "101")
    stale_older = build_snapshot(0, "99")
    second = build_snapshot(1, "102")
    older_after_second = build_snapshot(0, "98")
    assert duplicate_newer.candle is not None
    duplicate_newer.candle.event_time = duplicate_newer.candle.event_time + timedelta(seconds=1)
    assert stale_older.candle is not None
    stale_older.candle.event_time = stale_older.candle.event_time - timedelta(seconds=1)

    runner.ingest_snapshot(first)
    runner.ingest_snapshot(duplicate_newer)
    runner.ingest_snapshot(stale_older)
    runner.ingest_snapshot(second)
    runner.ingest_snapshot(older_after_second)

    feature_snapshot = runner.get_feature_snapshot("BTCUSDT")
    latest_market_snapshot = runner.get_latest_market_snapshot("BTCUSDT")

    assert feature_snapshot is None
    assert latest_market_snapshot is not None
    assert latest_market_snapshot.candle is not None
    assert latest_market_snapshot.candle.close == Decimal("102")
    assert runner._candles_by_symbol["BTCUSDT"][0].close == Decimal("101")  # noqa: SLF001 - targeted cache assertion
    assert runner._candles_by_symbol["BTCUSDT"][1].close == Decimal("102")  # noqa: SLF001 - targeted cache assertion
    assert len(runner._candles_by_symbol["BTCUSDT"]) == 2  # noqa: SLF001 - targeted cache assertion
