"""Market-context data access for symbol-scoped analysis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from app.market_data.candles import Candle
from app.storage import StorageRepository
from app.storage.models import MarketCandleSnapshotRecord

if TYPE_CHECKING:
    from app.bot import PaperBotRuntime


@dataclass(slots=True)
class MarketContextPoint:
    """One closed-price point used for market-context analysis."""

    symbol: str
    timestamp: datetime
    close_price: Decimal


class MarketContextService:
    """Load deterministic market-context history from persisted and live candles."""

    CORE_SYMBOLS: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT")

    def __init__(
        self,
        *,
        repository: StorageRepository,
        runtime: PaperBotRuntime,
    ) -> None:
        self._repository = repository
        self._runtime = runtime

    def load_symbol_points(
        self,
        symbol: str,
        *,
        timeframe: str = "1m",
        limit: int = 2_000,
    ) -> list[MarketContextPoint]:
        """Return merged persisted and live closed-price points for one symbol."""

        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            return []

        merged: dict[datetime, MarketContextPoint] = {}
        for record in self._repository.get_market_candle_history(
            symbol=normalized_symbol,
            timeframe=timeframe,
        ):
            point = _from_record(record)
            merged[point.timestamp] = point
        for candle in self._runtime.candle_history(normalized_symbol):
            if not candle.is_closed:
                continue
            point = _from_candle(candle)
            merged[point.timestamp] = point
        ordered = [merged[timestamp] for timestamp in sorted(merged)]
        if limit > 0:
            return ordered[-limit:]
        return ordered

    def load_market_context(
        self,
        *,
        selected_symbol: str,
        timeframe: str = "1m",
        limit: int = 2_000,
    ) -> dict[str, list[MarketContextPoint]]:
        """Return market-context histories for the selected symbol and core proxies."""

        symbols = {selected_symbol.strip().upper(), *self.CORE_SYMBOLS}
        return {
            symbol: self.load_symbol_points(symbol, timeframe=timeframe, limit=limit)
            for symbol in sorted(symbols)
            if symbol
        }


def _from_record(record: MarketCandleSnapshotRecord) -> MarketContextPoint:
    """Convert a persisted candle record into a market-context point."""

    return MarketContextPoint(
        symbol=record.symbol,
        timestamp=record.close_time,
        close_price=record.close_price,
    )


def _from_candle(candle: Candle) -> MarketContextPoint:
    """Convert a live candle into a market-context point."""

    return MarketContextPoint(
        symbol=candle.symbol,
        timestamp=candle.close_time,
        close_price=candle.close,
    )
