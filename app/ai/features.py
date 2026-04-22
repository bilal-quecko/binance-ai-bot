"""Deterministic AI advisory feature extraction."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.analysis.market_sentiment import MarketSentimentSnapshot
from app.analysis.technical import TechnicalAnalysisSnapshot
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


def _window_return(candles: Sequence[Candle], *, lookback: int) -> Decimal | None:
    """Return the close-to-close return for one lookback window."""

    if len(candles) <= lookback:
        return None
    baseline = candles[-(lookback + 1)].close
    if baseline <= Decimal("0"):
        return None
    return (candles[-1].close - baseline) / baseline


def _momentum_persistence(returns: Sequence[Decimal]) -> Decimal | None:
    """Return the share of recent returns aligned with the dominant direction."""

    if len(returns) < 3:
        return None
    positives = sum(1 for value in returns if value > Decimal("0"))
    negatives = sum(1 for value in returns if value < Decimal("0"))
    dominant = max(positives, negatives)
    total_directional = positives + negatives
    if total_directional == 0:
        return Decimal("0")
    return Decimal(dominant) / Decimal(total_directional)


def _direction_flip_rate(returns: Sequence[Decimal]) -> Decimal | None:
    """Return the rate of sign flips across recent directional returns."""

    directional = [Decimal("1") if value > Decimal("0") else Decimal("-1") for value in returns if value != Decimal("0")]
    if len(directional) < 2:
        return None
    flips = sum(1 for previous, current in zip(directional, directional[1:]) if previous != current)
    return Decimal(flips) / Decimal(len(directional) - 1)


def _structure_quality(
    *,
    candle_range: Decimal,
    candle_body: Decimal,
    wick_body_ratio: Decimal | None,
    trend_strength_score: int | None,
    multi_timeframe_agreement: str | None,
) -> Decimal | None:
    """Return a coarse structure-quality score from 0 to 1."""

    if candle_range <= Decimal("0"):
        return None
    body_ratio = candle_body / candle_range
    wick_penalty = Decimal("0")
    if wick_body_ratio is not None:
        wick_penalty = min(Decimal("0.35"), wick_body_ratio / Decimal("10"))
    trend_component = Decimal("0")
    if trend_strength_score is not None:
        trend_component = min(Decimal("0.35"), Decimal(trend_strength_score) / Decimal("200"))
    mtf_component = Decimal("0.15") if multi_timeframe_agreement in {"bullish_alignment", "bearish_alignment"} else Decimal("0")
    return max(Decimal("0"), min(Decimal("1"), body_ratio + trend_component + mtf_component - wick_penalty))


def extract_ai_features(
    *,
    symbol: str,
    candles: Sequence[Candle],
    feature_snapshot: FeatureSnapshot,
    top_of_book: TopOfBook | None = None,
    technical_analysis: TechnicalAnalysisSnapshot | None = None,
    market_sentiment: MarketSentimentSnapshot | None = None,
    recent_false_positive_rate_5m: Decimal | None = None,
    recent_false_reversal_rate_5m: Decimal | None = None,
) -> AIFeatureVector:
    """Extract a deterministic advisory feature vector from recent market state."""

    if not candles:
        raise ValueError("candles cannot be empty")

    latest_candle = candles[-1]
    recent_returns = tuple(
        _candle_return(previous.close, current.close)
        for previous, current in zip(candles, candles[1:])
    )
    recent_returns_window = recent_returns[-60:]
    momentum = sum(recent_returns_window[-5:], Decimal("0")) if recent_returns_window else Decimal("0")

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
        return_5m=_window_return(candles, lookback=5),
        return_15m=_window_return(candles, lookback=15),
        return_1h=_window_return(candles, lookback=60),
        momentum_persistence=_momentum_persistence(recent_returns_window[-12:]),
        direction_flip_rate=_direction_flip_rate(recent_returns_window[-12:]),
        structure_quality=_structure_quality(
            candle_range=candle_range,
            candle_body=candle_body,
            wick_body_ratio=wick_body_ratio,
            trend_strength_score=technical_analysis.trend_strength_score if technical_analysis is not None else None,
            multi_timeframe_agreement=(
                technical_analysis.multi_timeframe_agreement if technical_analysis is not None else None
            ),
        ),
        technical_trend_direction=technical_analysis.trend_direction if technical_analysis is not None else None,
        technical_trend_strength=technical_analysis.trend_strength if technical_analysis is not None else None,
        technical_trend_strength_score=(
            technical_analysis.trend_strength_score if technical_analysis is not None else None
        ),
        volatility_regime=technical_analysis.volatility_regime if technical_analysis is not None else None,
        breakout_readiness=technical_analysis.breakout_readiness if technical_analysis is not None else None,
        breakout_bias=technical_analysis.breakout_bias if technical_analysis is not None else None,
        reversal_risk=technical_analysis.reversal_risk if technical_analysis is not None else None,
        multi_timeframe_agreement=(
            technical_analysis.multi_timeframe_agreement if technical_analysis is not None else None
        ),
        market_state=market_sentiment.market_state if market_sentiment is not None else None,
        market_sentiment_score=market_sentiment.sentiment_score if market_sentiment is not None else None,
        market_breadth_state=market_sentiment.market_breadth_state if market_sentiment is not None else None,
        selected_symbol_relative_strength=(
            market_sentiment.selected_symbol_relative_strength if market_sentiment is not None else None
        ),
        recent_false_positive_rate_5m=recent_false_positive_rate_5m,
        recent_false_reversal_rate_5m=recent_false_reversal_rate_5m,
    )
