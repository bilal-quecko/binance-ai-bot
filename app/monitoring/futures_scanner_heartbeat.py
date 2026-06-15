"""Display-only heartbeat calculations for futures-paper scanner cards."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal


HeartbeatStatus = Literal[
    "active",
    "near_take_profit",
    "take_profit_touched",
    "near_stop",
    "invalidated",
    "stale",
]


@dataclass(slots=True)
class FuturesScannerHeartbeat:
    """Display-only live state for one scanner candidate."""

    live_change_since_scan: Decimal | None
    distance_to_stop: Decimal | None
    distance_to_take_profit: Decimal | None
    signal_age_seconds: int
    status: HeartbeatStatus


def calculate_futures_scanner_heartbeat(
    *,
    direction: str,
    scan_price: Decimal | None,
    live_price: Decimal | None,
    signal_time: datetime,
    live_price_updated_at: datetime | None,
    stop_loss: Decimal | None,
    take_profit: Decimal | None,
    now: datetime | None = None,
    stale_after_seconds: int = 30,
) -> FuturesScannerHeartbeat:
    """Calculate display-only heartbeat values without rescoring a scanner signal."""

    resolved_now = now or datetime.now(tz=UTC)
    age_seconds = max(0, int((resolved_now - signal_time).total_seconds()))
    if (
        live_price is None
        or live_price_updated_at is None
        or (resolved_now - live_price_updated_at).total_seconds() > stale_after_seconds
    ):
        return FuturesScannerHeartbeat(
            live_change_since_scan=None,
            distance_to_stop=None,
            distance_to_take_profit=None,
            signal_age_seconds=age_seconds,
            status="stale",
        )

    live_change = _change_since_scan(direction=direction, scan_price=scan_price, live_price=live_price)
    distance_to_stop = _distance_to_level(direction=direction, live_price=live_price, level=stop_loss, kind="stop")
    distance_to_take_profit = _distance_to_level(
        direction=direction,
        live_price=live_price,
        level=take_profit,
        kind="take_profit",
    )
    status = _status(
        direction=direction,
        live_price=live_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        distance_to_stop=distance_to_stop,
        distance_to_take_profit=distance_to_take_profit,
    )
    return FuturesScannerHeartbeat(
        live_change_since_scan=live_change,
        distance_to_stop=distance_to_stop,
        distance_to_take_profit=distance_to_take_profit,
        signal_age_seconds=age_seconds,
        status=status,
    )


def _change_since_scan(
    *,
    direction: str,
    scan_price: Decimal | None,
    live_price: Decimal,
) -> Decimal | None:
    if scan_price is None or scan_price <= Decimal("0") or direction not in {"long", "short"}:
        return None
    if direction == "long":
        return _pct(((live_price - scan_price) / scan_price) * Decimal("100"))
    return _pct(((scan_price - live_price) / scan_price) * Decimal("100"))


def _distance_to_level(
    *,
    direction: str,
    live_price: Decimal,
    level: Decimal | None,
    kind: Literal["stop", "take_profit"],
) -> Decimal | None:
    if level is None or live_price <= Decimal("0") or direction not in {"long", "short"}:
        return None
    if direction == "long":
        distance = level - live_price if kind == "take_profit" else live_price - level
    else:
        distance = live_price - level if kind == "take_profit" else level - live_price
    return _pct((distance / live_price) * Decimal("100"))


def _status(
    *,
    direction: str,
    live_price: Decimal,
    stop_loss: Decimal | None,
    take_profit: Decimal | None,
    distance_to_stop: Decimal | None,
    distance_to_take_profit: Decimal | None,
) -> HeartbeatStatus:
    if direction == "long":
        if stop_loss is not None and live_price <= stop_loss:
            return "invalidated"
        if take_profit is not None and live_price >= take_profit:
            return "take_profit_touched"
    elif direction == "short":
        if stop_loss is not None and live_price >= stop_loss:
            return "invalidated"
        if take_profit is not None and live_price <= take_profit:
            return "take_profit_touched"
    else:
        return "active"

    if distance_to_stop is not None and Decimal("0") <= distance_to_stop <= Decimal("0.35"):
        return "near_stop"
    if distance_to_take_profit is not None and Decimal("0") <= distance_to_take_profit <= Decimal("0.35"):
        return "near_take_profit"
    return "active"


def _pct(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
