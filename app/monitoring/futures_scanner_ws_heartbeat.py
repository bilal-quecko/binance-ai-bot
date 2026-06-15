"""WebSocket-backed live price cache for futures-paper scanner cards."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, Protocol


LOGGER = logging.getLogger(__name__)

LivePriceSource = Literal["websocket", "rest", "cache", "unavailable"]
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{3,30}$")


class FuturesPriceStreamClient(Protocol):
    """Protocol for Binance USD-M Futures price stream clients."""

    def messages(self, streams: Sequence[str]) -> AsyncIterator[dict[str, Any]]:
        """Yield decoded Binance websocket messages."""


@dataclass(slots=True)
class FuturesScannerLivePrice:
    """Latest display-only price for one visible scanner symbol."""

    symbol: str
    live_price: Decimal | None
    updated_at: datetime
    source: LivePriceSource
    data_source: str = "binance_usdm_futures"
    price_type: Literal["mark_price", "futures_last_price"] = "mark_price"
    stale: bool = False
    warning: str | None = None


class FuturesScannerWebSocketHeartbeatService:
    """Maintain USD-M Futures mark-price subscriptions for visible scanner symbols only."""

    def __init__(
        self,
        websocket_client: FuturesPriceStreamClient,
        *,
        max_symbols: int = 100,
        stale_after_seconds: int = 5,
    ) -> None:
        self._websocket_client = websocket_client
        self._max_symbols = max_symbols
        self._stale_after_seconds = stale_after_seconds
        self._active_symbols: tuple[str, ...] = ()
        self._cache: dict[str, FuturesScannerLivePrice] = {}
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()
        self._stream_warning: str | None = None

    @property
    def active_symbols(self) -> tuple[str, ...]:
        """Return the currently subscribed symbols."""

        return self._active_symbols

    async def update_subscriptions(self, symbols: Sequence[str]) -> tuple[str, ...]:
        """Replace active websocket subscriptions with sanitized visible symbols."""

        normalized = sanitize_scanner_symbols(symbols, max_symbols=self._max_symbols)
        async with self._lock:
            if normalized == self._active_symbols:
                return self._active_symbols
            await self._cancel_task()
            self._active_symbols = normalized
            self._stream_warning = None
            if normalized:
                streams = [f"{symbol.lower()}@markPrice" for symbol in normalized]
                LOGGER.info("Built futures scanner websocket subscription: %s", streams)
                self._task = asyncio.create_task(self._run(streams), name="futures-scanner-live-prices")
            return self._active_symbols

    def latest_prices(self, symbols: Sequence[str], *, now: datetime | None = None) -> dict[str, FuturesScannerLivePrice]:
        """Return cached prices for requested symbols, marking stale entries."""

        resolved_now = now or datetime.now(tz=UTC)
        requested = sanitize_scanner_symbols(symbols, max_symbols=self._max_symbols)
        items: dict[str, FuturesScannerLivePrice] = {}
        for symbol in requested:
            cached = self._cache.get(symbol)
            if cached is None:
                items[symbol] = FuturesScannerLivePrice(
                    symbol=symbol,
                    live_price=None,
                    updated_at=resolved_now,
                    source="unavailable",
                    data_source="binance_usdm_futures",
                    price_type="mark_price",
                    stale=True,
                    warning=self._stream_warning or "No WebSocket price has been received for this symbol yet.",
                )
                continue
            age_seconds = (resolved_now - cached.updated_at).total_seconds()
            stale = age_seconds > self._stale_after_seconds
            items[symbol] = FuturesScannerLivePrice(
                symbol=cached.symbol,
                live_price=cached.live_price,
                updated_at=cached.updated_at,
                source=cached.source if not stale else "cache",
                data_source=cached.data_source,
                price_type=cached.price_type,
                stale=stale,
                warning=(
                    cached.warning
                    if cached.warning
                    else "WebSocket price is stale; REST fallback will be used when available."
                    if stale
                    else None
                ),
            )
        return items

    async def close(self) -> None:
        """Stop the active websocket task."""

        async with self._lock:
            await self._cancel_task()
            self._active_symbols = ()

    async def _run(self, streams: Sequence[str]) -> None:
        try:
            LOGGER.info("Starting futures scanner websocket heartbeat for %d streams.", len(streams))
            async for payload in self._websocket_client.messages(streams):
                LOGGER.debug("Received futures scanner websocket payload: %s", payload)
                self._apply_price_payload(payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._stream_warning = "Binance WebSocket heartbeat is unavailable; REST fallback remains active."
            LOGGER.warning("Futures scanner websocket heartbeat stopped: %s", exc)

    async def _cancel_task(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    def _apply_price_payload(self, payload: dict[str, Any]) -> None:
        ticker = payload.get("data", payload)
        if not isinstance(ticker, dict):
            return
        symbol = str(ticker.get("s", "")).upper()
        if not SYMBOL_PATTERN.fullmatch(symbol):
            return
        raw_price = ticker.get("p") or ticker.get("c")
        if raw_price is None:
            return
        try:
            live_price = Decimal(str(raw_price))
        except Exception:
            LOGGER.warning("Ignoring invalid futures price for %s: %s", symbol, raw_price)
            return
        updated_at = datetime.now(tz=UTC)
        event_time = ticker.get("E")
        if event_time is not None:
            try:
                updated_at = datetime.fromtimestamp(int(event_time) / 1000, tz=UTC)
            except Exception:
                LOGGER.warning("Ignoring invalid futures price event time for %s: %s", symbol, event_time)
        price_type: Literal["mark_price", "futures_last_price"] = "mark_price" if ticker.get("p") is not None else "futures_last_price"
        self._cache[symbol] = FuturesScannerLivePrice(
            symbol=symbol,
            live_price=live_price,
            updated_at=updated_at,
            source="websocket",
            data_source="binance_usdm_futures",
            price_type=price_type,
            stale=False,
            warning=None,
        )
        self._stream_warning = None
        LOGGER.debug("Updated futures scanner websocket price for %s: %s", symbol, live_price)


def sanitize_scanner_symbols(symbols: Sequence[str], *, max_symbols: int = 50) -> tuple[str, ...]:
    """Normalize, dedupe, validate, and cap scanner heartbeat symbols."""

    normalized: list[str] = []
    seen: set[str] = set()
    for raw_symbol in symbols:
        symbol = str(raw_symbol).strip().upper()
        if not symbol or symbol in seen or not SYMBOL_PATTERN.fullmatch(symbol):
            continue
        normalized.append(symbol)
        seen.add(symbol)
        if len(normalized) >= max_symbols:
            break
    return tuple(normalized)
