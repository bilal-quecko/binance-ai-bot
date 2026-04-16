"""Application entrypoint."""

from argparse import ArgumentParser
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import FastAPI

from app.config import get_settings
from app.execution.execution_engine import ExecutionEngine
from app.features.feature_store import FeatureEngine
from app.features.models import FeatureConfig
from app.market_data.candles import Candle
from app.market_data.models import MarketSnapshot
from app.market_data.orderbook import TopOfBook
from app.monitoring.health import HealthStatus
from app.monitoring.logging import configure_logging
from app.paper.broker import PaperBroker
from app.risk.limits import RiskEngine
from app.runner import RunnerConfig, StrategyRunner
from app.strategies.models import TrendFollowingConfig
from app.strategies.trend_following import TrendFollowingStrategy


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    yield


app = FastAPI(title="Binance AI Bot", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    """Basic health endpoint."""

    settings = get_settings()
    return HealthStatus(
        name=settings.app_name,
        status="ok",
        mode=settings.app_mode,
    ).to_dict()


def _sample_market_snapshots(iterations: int) -> list[MarketSnapshot]:
    """Build a deterministic paper-mode market feed for the CLI loop."""

    base_time = datetime(2024, 3, 9, 16, 0, 0, tzinfo=UTC)
    snapshots: list[MarketSnapshot] = []
    pivot = max(iterations // 2, 1)

    for index in range(iterations):
        if index <= pivot:
            close_price = Decimal("100") + Decimal(index)
        else:
            close_price = Decimal("100") + Decimal(pivot) - (Decimal(index - pivot) * Decimal("2"))
        open_time = base_time + timedelta(minutes=index)
        close_time = open_time + timedelta(minutes=1) - timedelta(milliseconds=1)
        candle = Candle(
            symbol="BTCUSDT",
            timeframe="1m",
            open=close_price - Decimal("0.5"),
            high=close_price + Decimal("1"),
            low=close_price - Decimal("1"),
            close=close_price,
            volume=Decimal("10"),
            quote_volume=close_price * Decimal("10"),
            open_time=open_time,
            close_time=close_time,
            event_time=close_time,
            trade_count=100 + index,
            is_closed=True,
        )
        top_of_book = TopOfBook(
            symbol="BTCUSDT",
            bid_price=close_price - Decimal("0.05"),
            bid_quantity=Decimal("2"),
            ask_price=close_price + Decimal("0.05"),
            ask_quantity=Decimal("1.5"),
            event_time=close_time,
        )
        snapshots.append(
            MarketSnapshot(
                symbol="BTCUSDT",
                candle=candle,
                top_of_book=top_of_book,
                last_price=close_price,
                bid_price=top_of_book.bid_price,
                ask_price=top_of_book.ask_price,
                event_time=close_time,
                received_at=close_time,
            )
        )

    return snapshots


def run_paper_loop(iterations: int = 20) -> None:
    """Run a deterministic paper-mode bot loop and print results."""

    settings = get_settings()
    if settings.app_mode != "paper":
        raise RuntimeError("The strategy runner CLI only supports paper mode.")

    configure_logging(settings.log_level)
    broker = PaperBroker(initial_balances={"USDT": Decimal("10000")})
    execution_engine = ExecutionEngine(broker)
    feature_engine = FeatureEngine(
        FeatureConfig(
            ema_fast_period=3,
            ema_slow_period=5,
            rsi_period=3,
            atr_period=3,
        )
    )
    strategy = TrendFollowingStrategy(TrendFollowingConfig())
    risk_engine = RiskEngine()
    runner = StrategyRunner(
        feature_engine=feature_engine,
        strategy=strategy,
        risk_engine=risk_engine,
        execution_engine=execution_engine,
        broker=broker,
        config=RunnerConfig(
            order_quantity=Decimal("1"),
            risk_per_trade=Decimal(str(settings.risk_per_trade)),
            max_daily_loss=Decimal(str(settings.max_daily_loss)),
            max_open_positions=settings.max_open_positions,
        ),
    )

    for result in runner.run(_sample_market_snapshots(iterations), iterations=iterations):
        execution_status = result.execution_result.status if result.execution_result else "skipped"
        print(
            f"{result.feature_snapshot.timestamp.isoformat()} "
            f"signal={result.signal.side} "
            f"risk={result.risk_decision.decision if result.risk_decision else 'skipped'} "
            f"execution={execution_status} "
            f"position={result.current_position} "
            f"pnl={result.current_pnl}"
        )


def main() -> None:
    """CLI entry point for the paper-mode runner loop."""

    parser = ArgumentParser(description="Run the paper trading bot loop.")
    parser.add_argument("--iterations", type=int, default=20, help="Number of loop iterations to run.")
    args = parser.parse_args()
    run_paper_loop(iterations=args.iterations)


if __name__ == "__main__":
    main()
