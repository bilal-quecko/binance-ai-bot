from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.analysis import TechnicalAnalysisService
from app.features.feature_store import FeatureEngine
from app.features.models import FeatureConfig
from app.market_data.candles import Candle


def _build_candles(closes: list[Decimal]) -> list[Candle]:
    candles: list[Candle] = []
    base_time = datetime(2024, 3, 9, 16, 0, tzinfo=UTC)
    previous_close = closes[0]
    for index, close in enumerate(closes):
        open_price = previous_close if index > 0 else close
        high = max(open_price, close) + Decimal("0.6")
        low = min(open_price, close) - Decimal("0.6")
        open_time = base_time + timedelta(minutes=index)
        close_time = open_time + timedelta(minutes=1) - timedelta(milliseconds=1)
        candles.append(
            Candle(
                symbol="BTCUSDT",
                timeframe="1m",
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=Decimal("10") + Decimal(index),
                quote_volume=(Decimal("10") + Decimal(index)) * close,
                open_time=open_time,
                close_time=close_time,
                event_time=close_time,
                trade_count=10 + index,
                is_closed=True,
            )
        )
        previous_close = close
    return candles


def _feature_snapshot(candles: list[Candle]):
    engine = FeatureEngine(FeatureConfig(ema_fast_period=3, ema_slow_period=5, rsi_period=3, atr_period=3))
    return engine.build_snapshot(candles)


def test_technical_analysis_detects_bullish_trend() -> None:
    candles = _build_candles(
        [
            Decimal("100"),
            Decimal("101"),
            Decimal("102"),
            Decimal("103"),
            Decimal("104"),
            Decimal("105"),
            Decimal("106"),
            Decimal("107"),
            Decimal("108"),
            Decimal("109"),
            Decimal("110"),
            Decimal("111"),
            Decimal("112"),
            Decimal("113"),
            Decimal("114"),
        ]
    )
    analysis = TechnicalAnalysisService().analyze(
        symbol="BTCUSDT",
        candles=candles,
        feature_snapshot=_feature_snapshot(candles),
    )

    assert analysis.data_state == "ready"
    assert analysis.trend_direction == "bullish"
    assert analysis.momentum_state in {"bullish", "overbought"}
    assert analysis.breakout_readiness in {"medium", "high", "low"}
    assert analysis.explanation is not None


def test_technical_analysis_detects_bearish_trend() -> None:
    candles = _build_candles(
        [
            Decimal("114"),
            Decimal("113"),
            Decimal("112"),
            Decimal("111"),
            Decimal("110"),
            Decimal("109"),
            Decimal("108"),
            Decimal("107"),
            Decimal("106"),
            Decimal("105"),
            Decimal("104"),
            Decimal("103"),
            Decimal("102"),
            Decimal("101"),
            Decimal("100"),
        ]
    )
    analysis = TechnicalAnalysisService().analyze(
        symbol="BTCUSDT",
        candles=candles,
        feature_snapshot=_feature_snapshot(candles),
    )

    assert analysis.data_state == "ready"
    assert analysis.trend_direction == "bearish"
    assert analysis.momentum_state in {"bearish", "oversold"}
    assert analysis.reversal_risk in {"low", "medium", "high"}


def test_technical_analysis_detects_sideways_regime() -> None:
    candles = _build_candles(
        [
            Decimal("100"),
            Decimal("101"),
            Decimal("100"),
            Decimal("101"),
            Decimal("100"),
            Decimal("101"),
            Decimal("100"),
            Decimal("101"),
            Decimal("100"),
            Decimal("101"),
            Decimal("100"),
            Decimal("101"),
        ]
    )
    analysis = TechnicalAnalysisService().analyze(
        symbol="BTCUSDT",
        candles=candles,
        feature_snapshot=_feature_snapshot(candles),
    )

    assert analysis.data_state == "ready"
    assert analysis.trend_direction == "sideways"
    assert analysis.trend_strength in {"weak", "moderate"}


def test_technical_analysis_extracts_support_and_resistance_levels() -> None:
    candles = _build_candles(
        [
            Decimal("100"),
            Decimal("103"),
            Decimal("99"),
            Decimal("104"),
            Decimal("100"),
            Decimal("105"),
            Decimal("101"),
            Decimal("104"),
            Decimal("102"),
            Decimal("103"),
            Decimal("102.5"),
            Decimal("103"),
        ]
    )
    analysis = TechnicalAnalysisService().analyze(
        symbol="BTCUSDT",
        candles=candles,
        feature_snapshot=_feature_snapshot(candles),
    )

    assert analysis.data_state == "ready"
    assert len(analysis.support_levels) >= 1
    assert len(analysis.resistance_levels) >= 1
    assert all(level < candles[-1].close for level in analysis.support_levels)
    assert all(level > candles[-1].close for level in analysis.resistance_levels)


def test_technical_analysis_returns_incomplete_state_when_history_is_missing() -> None:
    candles = _build_candles([Decimal("100"), Decimal("101"), Decimal("102"), Decimal("103")])
    analysis = TechnicalAnalysisService().analyze(
        symbol="BTCUSDT",
        candles=candles,
        feature_snapshot=None,
    )

    assert analysis.data_state == "incomplete"
    assert analysis.trend_direction is None
    assert analysis.support_levels == []
    assert analysis.resistance_levels == []
