from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.execution.execution_engine import ExecutionEngine
from app.features.feature_store import FeatureEngine
from app.features.models import FeatureConfig
from app.market_data.candles import Candle
from app.market_data.models import MarketSnapshot
from app.market_data.orderbook import TopOfBook
from app.paper.broker import PaperBroker
from app.risk.limits import RiskEngine
from app.runner import RunnerConfig, StrategyRunner
from app.strategies.models import TrendFollowingConfig
from app.strategies.trend_following import TrendFollowingStrategy


BASE_TIME = datetime(2024, 3, 9, 16, 0, 0, tzinfo=UTC)


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


def test_strategy_runner_executes_one_loop_cycle() -> None:
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
        ],
        iterations=3,
    )

    final_result = results[-1]

    assert len(results) == 3
    assert final_result.signal.side == "BUY"
    assert final_result.risk_decision is not None
    assert final_result.risk_decision.decision == "approve"
    assert final_result.execution_result is not None
    assert final_result.execution_result.status == "executed"
    assert final_result.current_position is not None
    assert final_result.current_position.quantity == Decimal("1")
    assert final_result.current_pnl == Decimal("-0.10200")
