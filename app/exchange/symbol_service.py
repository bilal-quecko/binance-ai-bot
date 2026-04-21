"""Symbol discovery helpers for Binance Spot paper trading."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.exchange.binance_rest import BinanceRestClient
from app.exchange.models import ExchangeSymbol


POPULAR_SYMBOL_FALLBACK = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "LINKUSDT",
    "AVAXUSDT",
    "MATICUSDT",
)


@dataclass(slots=True)
class SpotSymbolRecord:
    """Frontend-friendly Binance Spot symbol metadata."""

    symbol: str
    base_asset: str
    quote_asset: str
    status: str


class SpotSymbolService:
    """Fetch and search tradable Binance Spot symbols for paper mode."""

    def __init__(
        self,
        client: BinanceRestClient,
        *,
        cache_ttl_seconds: int = 300,
    ) -> None:
        self._client = client
        self._cache_ttl_seconds = cache_ttl_seconds
        self._cached_symbols: list[SpotSymbolRecord] = []
        self._last_refresh_at: float = 0.0
        self._lock = asyncio.Lock()

    @staticmethod
    def _rank_by_fallback(symbols: Iterable[SpotSymbolRecord]) -> list[SpotSymbolRecord]:
        """Apply a deterministic popularity fallback order."""

        fallback_order = {symbol: index for index, symbol in enumerate(POPULAR_SYMBOL_FALLBACK)}
        return sorted(
            symbols,
            key=lambda item: (fallback_order.get(item.symbol, len(fallback_order)), item.symbol),
        )

    @staticmethod
    def _parse_quote_volume(value: object) -> Decimal:
        """Convert a Binance quote-volume field into a sortable Decimal."""

        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return Decimal("0")

    async def _rank_active_symbols(
        self,
        symbols: list[SpotSymbolRecord],
    ) -> list[SpotSymbolRecord]:
        """Rank symbols by activity, falling back to a deterministic shortlist."""

        symbol_lookup = {symbol.symbol: symbol for symbol in symbols}
        try:
            ticker_payload = await self._client.get_ticker_24h()
        except Exception:
            return self._rank_by_fallback(symbols)

        ranked_symbols = sorted(
            (
                (self._parse_quote_volume(item.get("quoteVolume")), symbol_lookup[item["symbol"]])
                for item in ticker_payload
                if isinstance(item.get("symbol"), str) and item["symbol"] in symbol_lookup
            ),
            key=lambda entry: (-entry[0], entry[1].symbol),
        )
        if not ranked_symbols:
            return self._rank_by_fallback(symbols)

        seen_symbols: set[str] = set()
        ordered = []
        for _, symbol in ranked_symbols:
            if symbol.symbol in seen_symbols:
                continue
            seen_symbols.add(symbol.symbol)
            ordered.append(symbol)

        if len(ordered) < len(symbols):
            ordered.extend(
                symbol
                for symbol in self._rank_by_fallback(symbols)
                if symbol.symbol not in seen_symbols
            )
        return ordered

    @staticmethod
    def _is_supported_symbol(symbol: ExchangeSymbol) -> bool:
        """Return whether the symbol is tradable in v1 paper mode."""

        return (
            symbol.quote_asset == "USDT"
            and symbol.status == "TRADING"
            and "SPOT" in symbol.permissions
        )

    @staticmethod
    def _to_record(symbol: ExchangeSymbol) -> SpotSymbolRecord:
        """Convert exchange metadata into a lightweight symbol record."""

        return SpotSymbolRecord(
            symbol=symbol.symbol,
            base_asset=symbol.base_asset,
            quote_asset=symbol.quote_asset,
            status=symbol.status,
        )

    async def list_symbols(self, *, refresh: bool = False) -> list[SpotSymbolRecord]:
        """Return cached tradable USDT Spot symbols, refreshing as needed."""

        now = time.monotonic()
        if (
            not refresh
            and self._cached_symbols
            and now - self._last_refresh_at < self._cache_ttl_seconds
        ):
            return list(self._cached_symbols)

        async with self._lock:
            now = time.monotonic()
            if (
                not refresh
                and self._cached_symbols
                and now - self._last_refresh_at < self._cache_ttl_seconds
            ):
                return list(self._cached_symbols)

            exchange_info = await self._client.get_exchange_info()
            self._cached_symbols = [
                self._to_record(symbol)
                for symbol in exchange_info.symbols
                if self._is_supported_symbol(symbol)
            ]
            self._cached_symbols.sort(key=lambda item: item.symbol)
            self._last_refresh_at = now
            return list(self._cached_symbols)

    async def search_symbols(
        self,
        *,
        query: str = "",
        limit: int = 20,
    ) -> list[SpotSymbolRecord]:
        """Search tradable Spot symbols by prefix-first or substring match."""

        normalized_query = query.strip().upper()
        symbols = await self.list_symbols()
        if not normalized_query:
            ranked_symbols = await self._rank_active_symbols(symbols)
            return ranked_symbols[:limit]

        prefix_matches = [
            symbol
            for symbol in symbols
            if symbol.symbol.startswith(normalized_query)
            or symbol.base_asset.startswith(normalized_query)
        ]
        remaining = [
            symbol
            for symbol in symbols
            if symbol not in prefix_matches
            and (
                normalized_query in symbol.symbol
                or normalized_query in symbol.base_asset
            )
        ]
        return (prefix_matches + remaining)[:limit]
