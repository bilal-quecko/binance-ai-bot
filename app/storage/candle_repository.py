"""Historical candle storage and merge helpers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

from app.analysis.multi_timeframe import aggregate_candles
from app.market_data.candles import Candle
from app.storage import StorageRepository
from app.storage.models import HistoricalCandleRecord

BackfillState = Literal["not_started", "loading", "ready", "partial", "failed"]
SupportedInterval = Literal["1m", "5m", "15m", "1h"]

INTERVAL_MINUTES: dict[str, int] = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
}


@dataclass(slots=True)
class CandleBackfillStatus:
    symbol: str
    requested_interval: SupportedInterval
    requested_lookback_days: int
    available_from: datetime | None
    available_to: datetime | None
    candle_count: int
    coverage_pct: Decimal
    status: BackfillState
    message: str
    last_backfilled_at: datetime | None
    effective_interval: SupportedInterval | None = None


@dataclass(slots=True)
class CandleSeries:
    symbol: str
    interval: SupportedInterval
    source_interval: SupportedInterval
    derived_from_lower_timeframe: bool
    candles: list[Candle]


class CandleRepository:
    """Higher-level stored-candle access on top of the shared storage repository."""

    def __init__(self, repository: StorageRepository) -> None:
        self._repository = repository

    def upsert(self, candles: Sequence[Candle], *, source: str) -> int:
        return self._repository.upsert_historical_candles(list(candles), source=source)

    def load(
        self,
        *,
        symbol: str,
        interval: SupportedInterval,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int | None = None,
    ) -> list[Candle]:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            return []

        if interval == "1m":
            records = self._repository.get_historical_candles(
                symbol=normalized_symbol,
                interval="1m",
                start_time=start_time,
                end_time=end_time,
                limit=limit,
            )
            return [_record_to_candle(record) for record in records]

        base_records = self._repository.get_historical_candles(
            symbol=normalized_symbol,
            interval="1m",
            start_time=start_time,
            end_time=end_time,
        )
        aggregated = aggregate_candles(
            [_record_to_candle(record) for record in base_records],
            timeframe_minutes=INTERVAL_MINUTES[interval],
        )
        if limit is not None:
            return aggregated[-limit:]
        return aggregated

    def latest(
        self,
        *,
        symbol: str,
        interval: SupportedInterval,
    ) -> Candle | None:
        candles = self.load(symbol=symbol, interval=interval, limit=1)
        return candles[-1] if candles else None

    def status(
        self,
        *,
        symbol: str,
        interval: SupportedInterval,
        lookback_days: int,
        loading: bool = False,
        failed_message: str | None = None,
        effective_interval: SupportedInterval | None = None,
    ) -> CandleBackfillStatus:
        candles = self.load(symbol=symbol, interval=interval)
        if not candles:
            if failed_message is not None:
                return CandleBackfillStatus(
                    symbol=symbol,
                    requested_interval=interval,
                    requested_lookback_days=lookback_days,
                    available_from=None,
                    available_to=None,
                    candle_count=0,
                    coverage_pct=Decimal("0"),
                    status="failed",
                    message=failed_message,
                    last_backfilled_at=None,
                    effective_interval=effective_interval,
                )
            return CandleBackfillStatus(
                symbol=symbol,
                requested_interval=interval,
                requested_lookback_days=lookback_days,
                available_from=None,
                available_to=None,
                candle_count=0,
                coverage_pct=Decimal("0"),
                status="loading" if loading else "not_started",
                message=(
                    f"Historical {interval} candles for {symbol} are loading."
                    if loading
                    else f"Historical {interval} candles for {symbol} have not been loaded yet."
                ),
                last_backfilled_at=None,
                effective_interval=effective_interval,
            )

        latest = candles[-1]
        earliest = candles[0]
        requested_span = timedelta(days=lookback_days)
        actual_span = max(latest.close_time - earliest.open_time, timedelta(0))
        coverage_pct = min(
            Decimal("100"),
            (Decimal(actual_span.total_seconds()) / Decimal(requested_span.total_seconds())) * Decimal("100")
            if requested_span.total_seconds() > 0
            else Decimal("0"),
        )
        interval_minutes = INTERVAL_MINUTES[interval]
        stale_cutoff = timedelta(minutes=5 if interval == "1m" else interval_minutes)
        age = datetime.now(tz=UTC) - latest.close_time
        if failed_message is not None:
            state: BackfillState = "failed"
            message = failed_message
        elif loading:
            state = "partial" if coverage_pct > Decimal("0") else "loading"
            message = f"Historical {interval} candles for {symbol} are still loading."
        elif coverage_pct >= Decimal("95") and age <= stale_cutoff:
            state = "ready"
            message = f"Historical {interval} candles are ready for {symbol}."
        else:
            state = "partial"
            message = f"Historical {interval} candles for {symbol} are only partially backfilled."

        return CandleBackfillStatus(
            symbol=symbol,
            requested_interval=interval,
            requested_lookback_days=lookback_days,
            available_from=earliest.open_time,
            available_to=latest.close_time,
            candle_count=len(candles),
            coverage_pct=coverage_pct.quantize(Decimal("0.01")),
            status=state,
            message=message,
            last_backfilled_at=latest.event_time,
            effective_interval=effective_interval,
        )


def merge_candles(
    *,
    stored_candles: Sequence[Candle],
    live_candles: Sequence[Candle],
    interval: SupportedInterval,
    limit: int | None = None,
) -> CandleSeries:
    merged: dict[datetime, Candle] = {}
    for candle in stored_candles:
        if candle.is_closed:
            merged[candle.open_time] = candle
    for candle in live_candles:
        if candle.is_closed:
            merged[candle.open_time] = candle
    ordered = [merged[key] for key in sorted(merged)]
    source_interval: SupportedInterval = "1m"
    derived = False
    if interval != "1m":
        ordered = aggregate_candles(ordered, timeframe_minutes=INTERVAL_MINUTES[interval])
        derived = True
    if limit is not None:
        ordered = ordered[-limit:]
    return CandleSeries(
        symbol=ordered[-1].symbol if ordered else "",
        interval=interval,
        source_interval=source_interval,
        derived_from_lower_timeframe=derived,
        candles=ordered,
    )


def _record_to_candle(record: HistoricalCandleRecord) -> Candle:
    return Candle(
        symbol=record.symbol,
        timeframe=record.interval,
        open=record.open_price,
        high=record.high_price,
        low=record.low_price,
        close=record.close_price,
        volume=record.volume,
        quote_volume=record.quote_volume,
        open_time=record.open_time,
        close_time=record.close_time,
        event_time=record.created_at,
        trade_count=record.trade_count,
        is_closed=True,
    )
