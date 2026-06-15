"""Binance Futures force-liquidation event feed.

Binance force-order streams publish actual liquidation events after they occur.
They are useful for event-based liquidation pressure, not future heatmap zones.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Literal, Protocol

from app.data.heatmap_models import LiquidationPressure

LOGGER = logging.getLogger(__name__)
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{3,30}$")
ForceOrderMode = Literal["all_market", "symbol"]


class ForceOrderStreamClient(Protocol):
    """Protocol for Binance websocket clients used by the feed."""

    def messages(self, streams: Sequence[str]) -> AsyncIterator[dict[str, Any]]:
        """Yield decoded Binance force-order payloads."""


@dataclass(slots=True, frozen=True)
class BinanceLiquidationEvent:
    """Normalized Binance USD-M Futures force-order event."""

    symbol: str
    event_time: datetime
    side: str
    order_type: str
    time_in_force: str
    original_quantity: Decimal
    price: Decimal
    average_price: Decimal
    order_status: str
    last_filled_quantity: Decimal
    accumulated_filled_quantity: Decimal
    trade_time: datetime
    notional_value: Decimal


@dataclass(slots=True, frozen=True)
class LiquidationPressureSnapshot:
    """Recent liquidation pressure computed from normalized events."""

    symbol: str
    timestamp: datetime
    recent_long_liquidation_notional: Decimal
    recent_short_liquidation_notional: Decimal
    liquidation_imbalance: Decimal
    liquidation_pressure: LiquidationPressure
    liquidation_spike_detected: bool
    recent_liquidation_direction: Literal["long", "short", "balanced", "none"]
    event_count: int
    data_available: bool


class BinanceLiquidationFeedService:
    """Maintain recent Binance force-liquidation events in memory."""

    def __init__(
        self,
        websocket_client: ForceOrderStreamClient,
        *,
        symbols: Sequence[str] | None = None,
        mode: ForceOrderMode = "all_market",
        retention_minutes: int = 60,
    ) -> None:
        self._websocket_client = websocket_client
        self._symbols = sanitize_symbols(symbols or ())
        self._mode = mode
        self._retention = timedelta(minutes=max(1, retention_minutes))
        self._events: dict[str, deque[BinanceLiquidationEvent]] = defaultdict(deque)
        self._task: asyncio.Task[None] | None = None
        self._last_update_time: datetime | None = None
        self._last_error: str | None = None

    @property
    def last_update_time(self) -> datetime | None:
        return self._last_update_time

    @property
    def last_error(self) -> str | None:
        return self._last_error

    @property
    def active_streams(self) -> tuple[str, ...]:
        return tuple(build_force_order_streams(symbols=self._symbols, mode=self._mode))

    def start(self) -> None:
        """Start consuming Binance force-order events."""

        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="binance-force-order-feed")

    async def close(self) -> None:
        """Stop the feed task."""

        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    def add_event(self, event: BinanceLiquidationEvent) -> None:
        """Add one normalized liquidation event."""

        self._prune(symbol=event.symbol, now=event.event_time)
        self._events[event.symbol].append(event)
        self._last_update_time = event.event_time
        self._last_error = None

    def pressure_snapshot(
        self,
        symbol: str,
        *,
        now: datetime | None = None,
        lookback_minutes: int = 15,
    ) -> LiquidationPressureSnapshot:
        """Compute recent liquidation pressure for one symbol."""

        normalized = symbol.upper()
        resolved_now = now or datetime.now(tz=UTC)
        self._prune(symbol=normalized, now=resolved_now)
        cutoff = resolved_now - timedelta(minutes=max(1, lookback_minutes))
        events = [event for event in self._events.get(normalized, ()) if event.event_time >= cutoff]
        long_notional = sum(
            (event.notional_value for event in events if _liquidated_position_side(event.side) == "long"),
            Decimal("0"),
        )
        short_notional = sum(
            (event.notional_value for event in events if _liquidated_position_side(event.side) == "short"),
            Decimal("0"),
        )
        total = long_notional + short_notional
        imbalance = Decimal("0") if total <= 0 else ((short_notional - long_notional) / total) * Decimal("100")
        abs_imbalance = abs(imbalance)
        pressure: LiquidationPressure = "low"
        if total >= Decimal("100000") or abs_imbalance >= Decimal("65"):
            pressure = "high"
        elif total >= Decimal("25000") or abs_imbalance >= Decimal("35"):
            pressure = "medium"
        direction: Literal["long", "short", "balanced", "none"] = "none"
        if total > 0:
            if long_notional > short_notional * Decimal("1.25"):
                direction = "long"
            elif short_notional > long_notional * Decimal("1.25"):
                direction = "short"
            else:
                direction = "balanced"
        return LiquidationPressureSnapshot(
            symbol=normalized,
            timestamp=resolved_now,
            recent_long_liquidation_notional=_quantize(long_notional),
            recent_short_liquidation_notional=_quantize(short_notional),
            liquidation_imbalance=imbalance.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
            liquidation_pressure=pressure,
            liquidation_spike_detected=pressure == "high",
            recent_liquidation_direction=direction,
            event_count=len(events),
            data_available=bool(events),
        )

    def recent_events(
        self,
        symbol: str,
        *,
        now: datetime | None = None,
        lookback_minutes: int = 5,
    ) -> tuple[BinanceLiquidationEvent, ...]:
        """Return recent normalized liquidation events for one symbol."""

        normalized = symbol.upper()
        resolved_now = now or datetime.now(tz=UTC)
        self._prune(symbol=normalized, now=resolved_now)
        cutoff = resolved_now - timedelta(minutes=max(1, lookback_minutes))
        return tuple(event for event in self._events.get(normalized, ()) if event.event_time >= cutoff)

    async def _run(self) -> None:
        streams = build_force_order_streams(symbols=self._symbols, mode=self._mode)
        if not streams:
            self._last_error = "No Binance force-order streams configured."
            return
        try:
            LOGGER.info("Starting Binance force-order feed with streams: %s", streams)
            async for payload in self._websocket_client.messages(streams):
                event = normalize_force_order_payload(payload)
                if event is not None:
                    self.add_event(event)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._last_error = f"Binance force-order feed unavailable: {exc}"
            LOGGER.warning("Binance force-order feed stopped: %s", exc)

    def _prune(self, *, symbol: str, now: datetime) -> None:
        cutoff = now - self._retention
        queue = self._events.get(symbol)
        if queue is None:
            return
        while queue and queue[0].event_time < cutoff:
            queue.popleft()


def build_force_order_streams(
    *,
    symbols: Sequence[str] = (),
    mode: ForceOrderMode = "all_market",
) -> list[str]:
    """Build Binance force-order stream names."""

    if mode == "all_market" or not symbols:
        return ["!forceOrder@arr"]
    return [f"{symbol.lower()}@forceOrder" for symbol in sanitize_symbols(symbols)]


def sanitize_symbols(symbols: Sequence[str]) -> tuple[str, ...]:
    """Normalize and validate Binance symbols."""

    normalized: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        symbol = str(raw).strip().upper()
        if not symbol or symbol in seen or not SYMBOL_PATTERN.fullmatch(symbol):
            continue
        normalized.append(symbol)
        seen.add(symbol)
    return tuple(normalized)


def normalize_force_order_payload(payload: dict[str, Any]) -> BinanceLiquidationEvent | None:
    """Normalize Binance force-order payloads from combined or direct streams."""

    root = payload.get("data", payload)
    if isinstance(root, list):
        root = root[0] if root else {}
    if not isinstance(root, dict):
        return None
    order = root.get("o")
    if not isinstance(order, dict):
        return None
    symbol = str(order.get("s", "")).upper()
    if not SYMBOL_PATTERN.fullmatch(symbol):
        return None
    try:
        event_ms = int(root.get("E", order.get("T", 0)))
        trade_ms = int(order.get("T", event_ms))
        original_quantity = Decimal(str(order.get("q", "0")))
        price = Decimal(str(order.get("p", "0")))
        average_price = Decimal(str(order.get("ap", price)))
        accumulated = Decimal(str(order.get("z", "0")))
        notional_price = average_price if average_price > 0 else price
    except (ValueError, ArithmeticError):
        return None
    return BinanceLiquidationEvent(
        symbol=symbol,
        event_time=datetime.fromtimestamp(event_ms / 1000, tz=UTC),
        side=str(order.get("S", "")).upper(),
        order_type=str(order.get("o", "")),
        time_in_force=str(order.get("f", "")),
        original_quantity=original_quantity,
        price=price,
        average_price=average_price,
        order_status=str(order.get("X", "")),
        last_filled_quantity=Decimal(str(order.get("l", "0"))),
        accumulated_filled_quantity=accumulated,
        trade_time=datetime.fromtimestamp(trade_ms / 1000, tz=UTC),
        notional_value=_quantize(abs(accumulated * notional_price)),
    )


def _liquidated_position_side(order_side: str) -> Literal["long", "short", "unknown"]:
    if order_side.upper() == "SELL":
        return "long"
    if order_side.upper() == "BUY":
        return "short"
    return "unknown"


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


_GLOBAL_FEED_SERVICE: BinanceLiquidationFeedService | None = None


def set_global_liquidation_feed_service(service: BinanceLiquidationFeedService | None) -> None:
    """Register the process-wide Binance liquidation feed used by providers."""

    global _GLOBAL_FEED_SERVICE
    _GLOBAL_FEED_SERVICE = service


def get_global_liquidation_feed_service() -> BinanceLiquidationFeedService | None:
    """Return the process-wide Binance liquidation feed if one is running."""

    return _GLOBAL_FEED_SERVICE
