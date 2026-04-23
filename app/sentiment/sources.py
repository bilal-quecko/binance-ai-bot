"""Deterministic symbol-sentiment proxy sources."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.sentiment.models import SentimentComponent, SymbolSentimentContext


@dataclass(slots=True)
class SymbolSentimentSourceResult:
    """One source result with optional weakening notes."""

    component: SentimentComponent | None
    weakening_note: str | None = None


class SymbolSentimentSource(Protocol):
    """Protocol for reusable symbol-sentiment inputs."""

    def collect(self, context: SymbolSentimentContext) -> SymbolSentimentSourceResult:
        """Collect one sentiment component for a symbol."""


class PriceAccelerationSource:
    """Proxy price-action sentiment from return acceleration and quote-volume support."""

    def collect(self, context: SymbolSentimentContext) -> SymbolSentimentSourceResult:
        candles = context.candles
        if len(candles) < 8:
            return SymbolSentimentSourceResult(
                component=None,
                weakening_note="Price-acceleration sentiment needs at least 8 closed candles.",
            )

        closes = [candle.close for candle in candles]
        quote_volumes = [candle.quote_volume for candle in candles]
        short_return = _return_ratio(closes[-4], closes[-1])
        prior_return = _return_ratio(closes[-8], closes[-4])
        acceleration = short_return - prior_return
        recent_quote_volume = _average(quote_volumes[-4:])
        prior_quote_volume = _average(quote_volumes[-8:-4])
        volume_support = _ratio_change(recent_quote_volume, prior_quote_volume)
        score = _clamp((acceleration * Decimal("7.5")) + (volume_support * Decimal("0.8")))
        return SymbolSentimentSourceResult(
            component=SentimentComponent(
                name="price_acceleration",
                score=score,
                weight=Decimal("0.28"),
                explanation=(
                    "Price acceleration proxy is "
                    f"{_direction_label(score)} because recent returns moved {short_return:.4f} "
                    f"versus {prior_return:.4f} previously, with quote-volume support at {volume_support:.4f}."
                ),
            )
        )


class VolatilityShockSource:
    """Proxy narrative pressure from short-horizon return shock and instability."""

    def collect(self, context: SymbolSentimentContext) -> SymbolSentimentSourceResult:
        candles = context.candles
        if len(candles) < 8:
            return SymbolSentimentSourceResult(
                component=None,
                weakening_note="Volatility-shock sentiment needs at least 8 closed candles.",
            )

        returns = _close_returns(candles)
        recent_returns = returns[-6:]
        volatility = _average_abs(recent_returns)
        latest_return = recent_returns[-1]
        if volatility <= Decimal("0"):
            return SymbolSentimentSourceResult(
                component=SentimentComponent(
                    name="volatility_shock",
                    score=Decimal("0"),
                    weight=Decimal("0.18"),
                    explanation="Volatility-shock proxy is neutral because recent return volatility is flat.",
                )
            )

        shock_ratio = latest_return / volatility
        score = _clamp(shock_ratio / Decimal("3"))
        return SymbolSentimentSourceResult(
            component=SentimentComponent(
                name="volatility_shock",
                score=score,
                weight=Decimal("0.18"),
                explanation=(
                    "Volatility-shock proxy is "
                    f"{_direction_label(score)} because the latest return shock ratio is {shock_ratio:.2f}x recent average."
                ),
            )
        )


class SearchTrendProxySource:
    """Placeholder search/social momentum proxy from volume spikes and directional persistence."""

    def collect(self, context: SymbolSentimentContext) -> SymbolSentimentSourceResult:
        candles = context.candles
        if len(candles) < 10:
            return SymbolSentimentSourceResult(
                component=None,
                weakening_note="Search/social trend proxy needs at least 10 closed candles.",
            )

        quote_volumes = [candle.quote_volume for candle in candles]
        returns = _close_returns(candles)
        spike_ratio = _safe_ratio(_average(quote_volumes[-3:]), _average(quote_volumes[-10:-3]))
        positive_moves = sum(1 for item in returns[-5:] if item > Decimal("0"))
        negative_moves = sum(1 for item in returns[-5:] if item < Decimal("0"))
        persistence = Decimal(positive_moves - negative_moves) / Decimal("5")
        score = _clamp((spike_ratio - Decimal("1")) * persistence * Decimal("1.4"))
        return SymbolSentimentSourceResult(
            component=SentimentComponent(
                name="search_social_proxy",
                score=score,
                weight=Decimal("0.17"),
                explanation=(
                    "Search/social momentum proxy is "
                    f"{_direction_label(score)} with volume spike ratio {spike_ratio:.2f} and recent directional persistence {persistence:.2f}."
                ),
            )
        )


class SymbolDominanceProxySource:
    """Relative-strength proxy versus BTC when benchmark history is available."""

    def collect(self, context: SymbolSentimentContext) -> SymbolSentimentSourceResult:
        if not context.benchmark_closes or len(context.candles) < 6:
            return SymbolSentimentSourceResult(
                component=None,
                weakening_note="BTC benchmark history is unavailable for relative-strength sentiment.",
            )

        symbol_closes = [candle.close for candle in context.candles]
        benchmark_closes = list(context.benchmark_closes)
        lookback = min(len(symbol_closes), len(benchmark_closes), 6)
        symbol_return = _return_ratio(symbol_closes[-lookback], symbol_closes[-1])
        benchmark_return = _return_ratio(benchmark_closes[-lookback], benchmark_closes[-1])
        relative_strength = symbol_return - benchmark_return
        score = _clamp(relative_strength * Decimal("8"))
        return SymbolSentimentSourceResult(
            component=SentimentComponent(
                name="symbol_dominance_proxy",
                score=score,
                weight=Decimal("0.17"),
                explanation=(
                    "Relative-strength proxy is "
                    f"{_direction_label(score)} because {context.symbol} returned {symbol_return:.4f} "
                    f"versus {context.benchmark_symbol or 'benchmark'} at {benchmark_return:.4f}."
                ),
            )
        )


class ExchangeActivityProxySource:
    """Exchange-attention proxy from trade count and quote-volume acceleration."""

    def collect(self, context: SymbolSentimentContext) -> SymbolSentimentSourceResult:
        candles = context.candles
        if len(candles) < 8:
            return SymbolSentimentSourceResult(
                component=None,
                weakening_note="Exchange-activity proxy needs at least 8 closed candles.",
            )

        trades = [Decimal(candle.trade_count) for candle in candles]
        quote_volumes = [candle.quote_volume for candle in candles]
        recent_trades = _average(trades[-4:])
        prior_trades = _average(trades[-8:-4])
        recent_quote_volume = _average(quote_volumes[-4:])
        prior_quote_volume = _average(quote_volumes[-8:-4])
        trades_change = _ratio_change(recent_trades, prior_trades)
        volume_change = _ratio_change(recent_quote_volume, prior_quote_volume)
        direction = _return_ratio(candles[-4].close, candles[-1].close)
        score = _clamp((trades_change + volume_change + direction) * Decimal("0.8"))
        return SymbolSentimentSourceResult(
            component=SentimentComponent(
                name="exchange_activity_proxy",
                score=score,
                weight=Decimal("0.20"),
                explanation=(
                    "Exchange-activity proxy is "
                    f"{_direction_label(score)} with trade-count change {trades_change:.4f}, "
                    f"quote-volume change {volume_change:.4f}, and recent direction {direction:.4f}."
                ),
            )
        )


def default_symbol_sentiment_sources() -> tuple[SymbolSentimentSource, ...]:
    """Return the default deterministic proxy source set."""

    return (
        PriceAccelerationSource(),
        VolatilityShockSource(),
        SearchTrendProxySource(),
        SymbolDominanceProxySource(),
        ExchangeActivityProxySource(),
    )


def _average(values: Sequence[Decimal]) -> Decimal:
    """Return the average of a Decimal sequence."""

    if not values:
        return Decimal("0")
    return sum(values, Decimal("0")) / Decimal(len(values))


def _average_abs(values: Sequence[Decimal]) -> Decimal:
    """Return the average absolute value of a Decimal sequence."""

    if not values:
        return Decimal("0")
    return sum((abs(value) for value in values), Decimal("0")) / Decimal(len(values))


def _return_ratio(start: Decimal, end: Decimal) -> Decimal:
    """Return a simple percentage change ratio."""

    if start == Decimal("0"):
        return Decimal("0")
    return (end - start) / start


def _ratio_change(current: Decimal, previous: Decimal) -> Decimal:
    """Return the relative change between two averages."""

    if previous == Decimal("0"):
        return Decimal("0")
    return (current - previous) / previous


def _safe_ratio(current: Decimal, previous: Decimal) -> Decimal:
    """Return a safe ratio between two values."""

    if previous == Decimal("0"):
        return Decimal("1")
    return current / previous


def _close_returns(candles: Sequence[object]) -> list[Decimal]:
    """Return close-to-close percentage moves."""

    closes = [getattr(candle, "close") for candle in candles]
    return [
        _return_ratio(closes[index - 1], closes[index])
        for index in range(1, len(closes))
    ]


def _clamp(value: Decimal) -> Decimal:
    """Clamp a score into `[-1, 1]`."""

    return max(Decimal("-1"), min(Decimal("1"), value))


def _direction_label(score: Decimal) -> str:
    """Map a normalized component score to a readable direction label."""

    if score >= Decimal("0.18"):
        return "bullish"
    if score <= Decimal("-0.18"):
        return "bearish"
    return "neutral"
