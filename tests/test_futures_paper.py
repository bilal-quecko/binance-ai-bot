from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.futures_paper import FuturesPaperService
from app.futures_paper.broker import FuturesPaperBroker
from app.futures_paper.models import FuturesOrderRequest, FuturesSignalInput
from app.futures_paper.risk import FuturesPaperRiskEngine
from app.futures_paper.signal_engine import FuturesSignalEngine
from app.storage import StorageRepository


def _db_path() -> Path:
    return (Path("tmp") / f"futures_paper_{uuid4().hex}.sqlite").resolve()


def test_futures_signal_engine_long_short_wait_and_avoid() -> None:
    engine = FuturesSignalEngine()

    long_signal = engine.evaluate(
        FuturesSignalInput(
            symbol="BTCUSDT",
            technical_bias="bullish",
            regime="bullish",
            market_sentiment="bullish",
            pattern_bias="bullish",
            expected_edge_pct=Decimal("0.20"),
            estimated_cost_pct=Decimal("0.05"),
        )
    )
    short_signal = engine.evaluate(
        FuturesSignalInput(
            symbol="BTCUSDT",
            technical_bias="bearish",
            regime="bearish",
            market_sentiment="bearish",
            pattern_bias="bearish",
            expected_edge_pct=Decimal("0.20"),
            estimated_cost_pct=Decimal("0.05"),
        )
    )
    avoid_signal = engine.evaluate(FuturesSignalInput(symbol="BTCUSDT", volatility_safe=False))

    assert long_signal.side == "LONG"
    assert long_signal.reason_codes == ("FUTURES_LONG_ALIGNMENT",)
    assert short_signal.side == "SHORT"
    assert short_signal.reason_codes == ("FUTURES_SHORT_ALIGNMENT",)
    assert avoid_signal.side == "AVOID"
    assert avoid_signal.reason_codes == ("VOLATILITY_UNSAFE",)


def test_futures_broker_opens_and_closes_long_with_fees() -> None:
    broker = FuturesPaperBroker()
    risk = FuturesPaperRiskEngine()
    order = FuturesOrderRequest(
        symbol="BTCUSDT",
        side="LONG",
        quantity=Decimal("0.01"),
        market_price=Decimal("50000"),
        leverage=2,
    )
    decision = risk.evaluate(order, current_position=None, open_position_count=0)

    opened = broker.execute(order, approved=decision.approved, reason_codes=decision.reason_codes)
    closed = broker.execute(
        FuturesOrderRequest(
            symbol="BTCUSDT",
            side="CLOSE",
            quantity=Decimal("0.01"),
            market_price=Decimal("51000"),
            leverage=2,
        ),
        approved=True,
        reason_codes=("FUTURES_CLOSE_APPROVED",),
    )

    assert opened.status == "executed"
    assert broker.get_position("BTCUSDT") is None
    assert closed.status == "executed"
    assert closed.realized_pnl > Decimal("0")


def test_futures_service_persists_fill_and_position() -> None:
    repository = StorageRepository(f"sqlite:///{_db_path()}")
    try:
        service = FuturesPaperService(repository=repository)

        result = service.manual_open(
            symbol="BTCUSDT",
            side="SHORT",
            quantity=Decimal("0.01"),
            market_price=Decimal("50000"),
            leverage=2,
        )

        assert result.status == "executed"
        assert repository.get_futures_paper_position("BTCUSDT") is not None
        assert repository.get_futures_paper_fills(symbol="BTCUSDT", limit=10)
    finally:
        repository.close()
