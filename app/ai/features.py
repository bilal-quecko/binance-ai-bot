"""Deterministic AI advisory feature extraction."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.ai.models import AIFeatureVector
from app.features.models import FeatureSnapshot
from app.market_data.candles import Candle
from app.market_data.orderbook import TopOfBook


def _safe_ratio(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    """Return numerator/denominator when the denominator is positive."""

    if denominator == Decimal("0"):
        return None
    return numerator / denominator


def _average(values: Sequence[Decimal]) -> Decimal | None:
    """Return the arithmetic mean for non-empty Decimal sequences."""

    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _candle_return(previous_close: Decimal, current_close: Decimal) -> Decimal:
    """Return the simple percent return between two closes."""

    if previous_close == Decimal("0"):
        return Decimal("0")
    return (current_close - previous_close) / previous_close


def extract_ai_features(
    *,
    symbol: str,
    candles: Sequence[Candle],
    feature_snapshot: FeatureSnapshot,
    top_of_book: TopOfBook | None = None,
) -> AIFeatureVector:
    """Extract a deterministic advisory feature vector from recent market state."""

    if not candles:
        raise ValueError("candles cannot be empty")

    latest_candle = candles[-1]
    recent_returns = tuple(
        _candle_return(previous.close, current.close)
        for previous, current in zip(candles, candles[1:])
    )
    recent_returns_window = recent_returns[-5:]
    momentum = sum(recent_returns_window, Decimal("0")) if recent_returns_window else Decimal("0")

    candle_body = abs(latest_candle.close - latest_candle.open)
    candle_range = latest_candle.high - latest_candle.low
    upper_wick = latest_candle.high - max(latest_candle.open, latest_candle.close)
    lower_wick = min(latest_candle.open, latest_candle.close) - latest_candle.low

    wick_body_ratio = _safe_ratio(upper_wick + lower_wick, candle_body)
    upper_wick_ratio = _safe_ratio(upper_wick, candle_range) if candle_range > Decimal("0") else None
    lower_wick_ratio = _safe_ratio(lower_wick, candle_range) if candle_range > Decimal("0") else None

    volatility_pct = None
    if feature_snapshot.atr is not None:
        volatility_pct = _safe_ratio(feature_snapshot.atr, latest_candle.close)

    average_volume = _average([candle.volume for candle in candles[:-1]])
    volume_change_pct = None
    volume_spike_ratio = None
    if average_volume is not None and average_volume > Decimal("0"):
        volume_change_pct = (latest_candle.volume - average_volume) / average_volume
        volume_spike_ratio = latest_candle.volume / average_volume

    spread_ratio = None
    microstructure_healthy = False
    if top_of_book is not None and feature_snapshot.mid_price not in {None, Decimal("0")}:
        spread_ratio = _safe_ratio(
            top_of_book.ask_price - top_of_book.bid_price,
            feature_snapshot.mid_price,
        )
        microstructure_healthy = (
            spread_ratio is not None
            and spread_ratio <= Decimal("0.0025")
            and (
                feature_snapshot.order_book_imbalance is None
                or abs(feature_snapshot.order_book_imbalance) <= Decimal("0.75")
            )
        )

    return AIFeatureVector(
        symbol=symbol.upper(),
        timestamp=feature_snapshot.timestamp,
        candle_count=len(candles),
        close_price=latest_candle.close,
        ema_fast=feature_snapshot.ema_fast,
        ema_slow=feature_snapshot.ema_slow,
        rsi=feature_snapshot.rsi,
        atr=feature_snapshot.atr,
        volatility_pct=volatility_pct,
        momentum=momentum,
        recent_returns=recent_returns_window,
        wick_body_ratio=wick_body_ratio,
        upper_wick_ratio=upper_wick_ratio,
        lower_wick_ratio=lower_wick_ratio,
        volume_change_pct=volume_change_pct,
        volume_spike_ratio=volume_spike_ratio,
        spread_ratio=spread_ratio,
        order_book_imbalance=feature_snapshot.order_book_imbalance,
        microstructure_healthy=microstructure_healthy,
    )
