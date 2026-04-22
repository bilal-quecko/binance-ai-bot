"""Multi-timeframe aggregation and agreement helpers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from app.features.indicators import ema
from app.market_data.candles import Candle


TimeframeAgreement = Literal[
    "bullish_alignment",
    "bearish_alignment",
    "mixed",
    "insufficient_data",
]
TrendDirection = Literal["bullish", "bearish", "sideways"]
TrendStrength = Literal["weak", "moderate", "strong"]


@dataclass(slots=True)
class AggregatedTimeframeSummary:
    """Trend summary for one derived timeframe."""

    timeframe: str
    trend_direction: TrendDirection
    trend_strength: TrendStrength


def build_multi_timeframe_summaries(
    candles: Sequence[Candle],
) -> list[AggregatedTimeframeSummary]:
    """Build timeframe summaries from 1m candles when enough history exists."""

    summaries: list[AggregatedTimeframeSummary] = []
    for timeframe_minutes in (1, 5, 15):
        aggregated = aggregate_candles(candles, timeframe_minutes=timeframe_minutes)
        if len(aggregated) < 6:
            continue
        closes = [candle.close for candle in aggregated]
        fast_ema = ema(closes, period=3)
        slow_ema = ema(closes, period=5)
        if fast_ema is None or slow_ema is None:
            continue
        latest_close = closes[-1]
        gap_ratio = abs(fast_ema - slow_ema) / latest_close if latest_close > Decimal("0") else Decimal("0")
        summaries.append(
            AggregatedTimeframeSummary(
                timeframe=_label_for_minutes(timeframe_minutes),
                trend_direction=_classify_trend_direction(fast_ema, slow_ema),
                trend_strength=_classify_trend_strength(gap_ratio),
            )
        )
    return summaries


def summarize_multi_timeframe_agreement(
    summaries: Sequence[AggregatedTimeframeSummary],
) -> TimeframeAgreement:
    """Summarize whether the available timeframe trends agree."""

    directional = [
        summary.trend_direction
        for summary in summaries
        if summary.trend_direction in {"bullish", "bearish"}
    ]
    if len(directional) < 2:
        return "insufficient_data"
    if all(direction == "bullish" for direction in directional):
        return "bullish_alignment"
    if all(direction == "bearish" for direction in directional):
        return "bearish_alignment"
    return "mixed"


def aggregate_candles(
    candles: Sequence[Candle],
    *,
    timeframe_minutes: int,
) -> list[Candle]:
    """Aggregate lower-timeframe candles into a higher timeframe."""

    if timeframe_minutes <= 1:
        return list(candles)
    if not candles:
        return []

    buckets: list[list[Candle]] = []
    current_bucket: list[Candle] = []
    current_bucket_open: datetime | None = None

    for candle in candles:
        bucket_open = _bucket_open_time(candle.open_time, timeframe_minutes)
        if current_bucket_open is None or bucket_open != current_bucket_open:
            if current_bucket:
                buckets.append(current_bucket)
            current_bucket = [candle]
            current_bucket_open = bucket_open
            continue
        current_bucket.append(candle)

    if current_bucket:
        buckets.append(current_bucket)

    aggregated: list[Candle] = []
    for bucket in buckets:
        first = bucket[0]
        last = bucket[-1]
        aggregated.append(
            Candle(
                symbol=first.symbol,
                timeframe=_label_for_minutes(timeframe_minutes),
                open=first.open,
                high=max(candle.high for candle in bucket),
                low=min(candle.low for candle in bucket),
                close=last.close,
                volume=sum((candle.volume for candle in bucket), start=Decimal("0")),
                quote_volume=sum((candle.quote_volume for candle in bucket), start=Decimal("0")),
                open_time=_bucket_open_time(first.open_time, timeframe_minutes),
                close_time=last.close_time,
                event_time=last.event_time,
                trade_count=sum(candle.trade_count for candle in bucket),
                is_closed=all(candle.is_closed for candle in bucket),
            )
        )
    return aggregated


def _bucket_open_time(value: datetime, timeframe_minutes: int) -> datetime:
    """Floor a candle open time to the requested minute bucket."""

    minute = (value.minute // timeframe_minutes) * timeframe_minutes
    return value.astimezone(UTC).replace(minute=minute, second=0, microsecond=0)


def _label_for_minutes(timeframe_minutes: int) -> str:
    """Return the Binance-style timeframe label for minute buckets."""

    return f"{timeframe_minutes}m"


def _classify_trend_direction(fast_ema: Decimal, slow_ema: Decimal) -> TrendDirection:
    """Classify trend direction from EMA ordering."""

    if fast_ema > slow_ema:
        return "bullish"
    if fast_ema < slow_ema:
        return "bearish"
    return "sideways"


def _classify_trend_strength(gap_ratio: Decimal) -> TrendStrength:
    """Classify trend strength from normalized EMA separation."""

    if gap_ratio >= Decimal("0.01"):
        return "strong"
    if gap_ratio >= Decimal("0.004"):
        return "moderate"
    return "weak"
