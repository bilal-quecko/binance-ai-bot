from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.ai.service import AISignalService
from app.features.models import FeatureSnapshot
from app.market_data.candles import Candle
from app.market_data.orderbook import TopOfBook


BASE_TIME = datetime(2024, 3, 9, 16, 0, 0, tzinfo=UTC)


def build_candle(index: int, close_price: str, *, open_price: str | None = None, high: str | None = None, low: str | None = None, volume: str = "10") -> Candle:
    close = Decimal(close_price)
    open_ = Decimal(open_price) if open_price is not None else close - Decimal("0.5")
    high_value = Decimal(high) if high is not None else max(open_, close) + Decimal("1")
    low_value = Decimal(low) if low is not None else min(open_, close) - Decimal("1")
    open_time = BASE_TIME + timedelta(minutes=index)
    close_time = open_time + timedelta(minutes=1) - timedelta(milliseconds=1)
    return Candle(
        symbol="BTCUSDT",
        timeframe="1m",
        open=open_,
        high=high_value,
        low=low_value,
        close=close,
        volume=Decimal(volume),
        quote_volume=close * Decimal(volume),
        open_time=open_time,
        close_time=close_time,
        event_time=close_time,
        trade_count=100 + index,
        is_closed=True,
    )


def build_top_of_book(price: str) -> TopOfBook:
    mid = Decimal(price)
    return TopOfBook(
        symbol="BTCUSDT",
        bid_price=mid - Decimal("0.05"),
        bid_quantity=Decimal("2"),
        ask_price=mid + Decimal("0.05"),
        ask_quantity=Decimal("3"),
        event_time=BASE_TIME + timedelta(minutes=5),
    )


def build_feature_snapshot(**overrides: object) -> FeatureSnapshot:
    payload: dict[str, object] = {
        "symbol": "BTCUSDT",
        "timestamp": BASE_TIME + timedelta(minutes=5),
        "ema_fast": Decimal("105"),
        "ema_slow": Decimal("100"),
        "rsi": Decimal("60"),
        "atr": Decimal("1.2"),
        "mid_price": Decimal("106"),
        "bid_ask_spread": Decimal("0.10"),
        "order_book_imbalance": Decimal("0.20"),
        "regime": "bullish",
    }
    payload.update(overrides)
    return FeatureSnapshot(**payload)


def test_ai_signal_service_scores_bullish_entry_setup() -> None:
    service = AISignalService()
    candles = [
        build_candle(0, "100", volume="8"),
        build_candle(1, "101", volume="8.5"),
        build_candle(2, "103", volume="9"),
        build_candle(3, "104", volume="9.5"),
        build_candle(4, "106", volume="14"),
    ]
    signal = service.build_signal(
        symbol="BTCUSDT",
        candles=candles,
        feature_snapshot=build_feature_snapshot(),
        top_of_book=build_top_of_book("106"),
    )

    assert signal.bias == "bullish"
    assert signal.entry_signal is True
    assert signal.exit_signal is False
    assert signal.suggested_action in {"enter", "hold"}


def test_ai_signal_service_scores_bearish_exit_setup() -> None:
    service = AISignalService()
    candles = [
        build_candle(0, "106", volume="10"),
        build_candle(1, "104", volume="10.5"),
        build_candle(2, "102", volume="11"),
        build_candle(3, "100", volume="12"),
        build_candle(4, "97", volume="15"),
    ]
    signal = service.build_signal(
        symbol="BTCUSDT",
        candles=candles,
        feature_snapshot=build_feature_snapshot(
            ema_fast=Decimal("97"),
            ema_slow=Decimal("101"),
            rsi=Decimal("35"),
            atr=Decimal("1.8"),
            mid_price=Decimal("97"),
            order_book_imbalance=Decimal("-0.30"),
            regime="bearish",
        ),
        top_of_book=build_top_of_book("97"),
    )

    assert signal.bias == "bearish"
    assert signal.entry_signal is False
    assert signal.exit_signal is True
    assert signal.suggested_action == "exit"


def test_ai_signal_service_scores_sideways_wait_state() -> None:
    service = AISignalService()
    candles = [
        build_candle(0, "100", open_price="100.1", high="100.5", low="99.8", volume="10"),
        build_candle(1, "100.1", open_price="100", high="100.4", low="99.9", volume="10"),
        build_candle(2, "99.9", open_price="100", high="100.2", low="99.7", volume="9.8"),
        build_candle(3, "100", open_price="99.95", high="100.3", low="99.8", volume="10.1"),
        build_candle(4, "100.05", open_price="100", high="100.2", low="99.9", volume="10"),
    ]
    signal = service.build_signal(
        symbol="BTCUSDT",
        candles=candles,
        feature_snapshot=build_feature_snapshot(
            ema_fast=Decimal("100.02"),
            ema_slow=Decimal("100.01"),
            rsi=Decimal("50"),
            atr=Decimal("0.20"),
            mid_price=Decimal("100.05"),
            order_book_imbalance=Decimal("0.02"),
            regime="neutral",
        ),
        top_of_book=build_top_of_book("100.05"),
    )

    assert signal.bias == "sideways"
    assert signal.entry_signal is False
    assert signal.exit_signal is False
    assert signal.suggested_action == "wait"


def test_ai_signal_confidence_stays_within_bounds() -> None:
    service = AISignalService()
    candles = [
        build_candle(0, "100", volume="5"),
        build_candle(1, "110", volume="50"),
        build_candle(2, "120", volume="70"),
        build_candle(3, "130", volume="80"),
        build_candle(4, "140", volume="90"),
    ]
    signal = service.build_signal(
        symbol="BTCUSDT",
        candles=candles,
        feature_snapshot=build_feature_snapshot(
            ema_fast=Decimal("140"),
            ema_slow=Decimal("100"),
            rsi=Decimal("80"),
            atr=Decimal("9"),
            mid_price=Decimal("140"),
            bid_ask_spread=Decimal("0.80"),
            order_book_imbalance=Decimal("0.80"),
            regime="bullish",
        ),
        top_of_book=build_top_of_book("140"),
    )

    assert 0 <= signal.confidence <= 100
    assert isinstance(signal.explanation, str)
