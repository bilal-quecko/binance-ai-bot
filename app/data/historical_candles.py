"""Historical candle helpers and typed backfill utilities."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from app.market_data.candles import Candle

SupportedInterval = Literal["1m", "5m", "15m", "1h"]
HistorySource = Literal["historical_rest", "live_runtime", "aggregated"]

INTERVAL_MS: dict[SupportedInterval, int] = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
}


def interval_to_timedelta(interval: SupportedInterval) -> timedelta:
    return timedelta(milliseconds=INTERVAL_MS[interval])


def now_utc() -> datetime:
    return datetime.now(tz=UTC)


def lookback_window(*, days: int, end_time: datetime | None = None) -> tuple[datetime, datetime]:
    end = end_time or now_utc()
    return end - timedelta(days=days), end


def parse_rest_kline(symbol: str, interval: SupportedInterval, row: list[Any]) -> Candle:
    open_time = datetime.fromtimestamp(int(row[0]) / 1000, tz=UTC)
    close_time = datetime.fromtimestamp(int(row[6]) / 1000, tz=UTC)
    return Candle(
        symbol=symbol.upper(),
        timeframe=interval,
        open=Decimal(str(row[1])),
        high=Decimal(str(row[2])),
        low=Decimal(str(row[3])),
        close=Decimal(str(row[4])),
        volume=Decimal(str(row[5])),
        quote_volume=Decimal(str(row[7])),
        open_time=open_time,
        close_time=close_time,
        event_time=close_time,
        trade_count=int(row[8]),
        is_closed=True,
    )
