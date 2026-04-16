from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.features.feature_store import FeatureEngine
from app.features.indicators import atr, ema, rsi
from app.features.models import FeatureConfig, FeatureSnapshot
from app.market_data.candles import Candle
from app.market_data.orderbook import TopOfBook


BASE_TIME = datetime(2024, 3, 9, 16, 0, 0, tzinfo=UTC)


def build_candle(*, index: int, open_: str, high: str, low: str, close: str, volume: str = "10") -> Candle:
    open_time = BASE_TIME + timedelta(minutes=index)
    close_time = open_time + timedelta(minutes=1) - timedelta(milliseconds=1)
    return Candle(
        symbol="BTCUSDT",
        timeframe="1m",
        open=Decimal(open_),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal(volume),
        quote_volume=Decimal("1000"),
        open_time=open_time,
        close_time=close_time,
        event_time=close_time,
        trade_count=100 + index,
        is_closed=True,
    )


def test_ema_returns_expected_value() -> None:
    values = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), Decimal("5")]

    assert ema(values, period=3) == Decimal("4")


def test_rsi_returns_expected_value() -> None:
    values = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("2"), Decimal("3")]

    assert rsi(values, period=3) == Decimal("77.77777777777777777777777778")


def test_atr_returns_expected_value() -> None:
    candles = [
        build_candle(index=0, open_="10", high="11", low="9", close="10"),
        build_candle(index=1, open_="10", high="13", low="10", close="12"),
        build_candle(index=2, open_="12", high="14", low="11", close="13"),
        build_candle(index=3, open_="13", high="15", low="12", close="14"),
    ]

    assert atr(candles, period=3) == Decimal("2.777777777777777777777777778")


def test_feature_engine_builds_deterministic_snapshot() -> None:
    candles = [
        build_candle(index=0, open_="100", high="101", low="99", close="100"),
        build_candle(index=1, open_="100", high="103", low="99", close="102"),
        build_candle(index=2, open_="102", high="103", low="100", close="101"),
        build_candle(index=3, open_="101", high="104", low="101", close="103"),
        build_candle(index=4, open_="103", high="105", low="102", close="104"),
    ]
    top_of_book = TopOfBook(
        symbol="BTCUSDT",
        bid_price=Decimal("103.90"),
        bid_quantity=Decimal("2.5"),
        ask_price=Decimal("104.10"),
        ask_quantity=Decimal("1.5"),
        event_time=BASE_TIME + timedelta(minutes=5),
    )
    engine = FeatureEngine(
        FeatureConfig(
            ema_fast_period=3,
            ema_slow_period=4,
            rsi_period=3,
            atr_period=3,
        )
    )

    snapshot = engine.build_snapshot(candles, top_of_book=top_of_book)

    assert isinstance(snapshot, FeatureSnapshot)
    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.timestamp == top_of_book.event_time
    assert snapshot.ema_fast == Decimal("103")
    assert snapshot.ema_slow == Decimal("102.5")
    assert snapshot.rsi == Decimal("84.61538461538461538461538462")
    assert snapshot.atr == Decimal("3")
    assert snapshot.mid_price == Decimal("104.00")
    assert snapshot.bid_ask_spread == Decimal("0.20")
    assert snapshot.order_book_imbalance == Decimal("0.25")
    assert snapshot.regime == "bullish"


def test_feature_engine_rejects_symbol_mismatch() -> None:
    candles = [
        build_candle(index=0, open_="100", high="101", low="99", close="100"),
        build_candle(index=1, open_="100", high="103", low="99", close="102"),
    ]
    top_of_book = TopOfBook(
        symbol="ETHUSDT",
        bid_price=Decimal("1"),
        bid_quantity=Decimal("1"),
        ask_price=Decimal("2"),
        ask_quantity=Decimal("1"),
        event_time=BASE_TIME,
    )
    engine = FeatureEngine()

    with pytest.raises(ValueError, match="top_of_book symbol"):
        engine.build_snapshot(candles, top_of_book=top_of_book)
