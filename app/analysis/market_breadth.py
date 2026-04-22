"""Deterministic market-breadth helpers."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from math import sqrt
from typing import Literal

from app.data import MarketContextPoint


BreadthState = Literal["positive", "negative", "mixed", "insufficient_data"]
RelativeStrengthState = Literal[
    "outperforming_btc",
    "underperforming_btc",
    "in_line",
    "insufficient_data",
]


@dataclass(slots=True)
class BreadthSummary:
    """Market-breadth summary across tracked symbols."""

    state: BreadthState
    advancing_symbols: int
    declining_symbols: int
    sample_size: int


def recent_return_pct(
    points: Sequence[MarketContextPoint],
    *,
    lookback_points: int,
) -> Decimal | None:
    """Return the close-to-close return over the requested lookback window."""

    if len(points) <= lookback_points:
        return None
    baseline = points[-(lookback_points + 1)].close_price
    if baseline <= Decimal("0"):
        return None
    return (points[-1].close_price - baseline) / baseline


def realized_volatility_pct(
    points: Sequence[MarketContextPoint],
    *,
    lookback_points: int,
) -> Decimal | None:
    """Return simple realized volatility over recent percentage returns."""

    window = points[-(lookback_points + 1) :]
    if len(window) < 3:
        return None
    returns = []
    for previous, current in zip(window[:-1], window[1:]):
        if previous.close_price <= Decimal("0"):
            continue
        returns.append(float((current.close_price - previous.close_price) / previous.close_price))
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / len(returns)
    return Decimal(str(sqrt(variance) * 100))


def classify_market_breadth(
    symbol_points: Mapping[str, Sequence[MarketContextPoint]],
    *,
    lookback_points: int = 30,
) -> BreadthSummary:
    """Classify market breadth from recent symbol returns."""

    advancing = 0
    declining = 0
    sampled = 0
    for points in symbol_points.values():
        move = recent_return_pct(points, lookback_points=lookback_points)
        if move is None:
            continue
        sampled += 1
        if move > Decimal("0.003"):
            advancing += 1
        elif move < Decimal("-0.003"):
            declining += 1

    if sampled < 3:
        return BreadthSummary(
            state="insufficient_data",
            advancing_symbols=advancing,
            declining_symbols=declining,
            sample_size=sampled,
        )

    positive_ratio = Decimal(advancing) / Decimal(sampled)
    negative_ratio = Decimal(declining) / Decimal(sampled)
    if positive_ratio >= Decimal("0.60"):
        state: BreadthState = "positive"
    elif negative_ratio >= Decimal("0.60"):
        state = "negative"
    else:
        state = "mixed"
    return BreadthSummary(
        state=state,
        advancing_symbols=advancing,
        declining_symbols=declining,
        sample_size=sampled,
    )


def classify_relative_strength(
    symbol_points: Sequence[MarketContextPoint],
    btc_points: Sequence[MarketContextPoint],
    *,
    lookback_points: int = 30,
) -> tuple[RelativeStrengthState, Decimal | None]:
    """Compare the selected symbol's recent return versus BTC."""

    symbol_return = recent_return_pct(symbol_points, lookback_points=lookback_points)
    btc_return = recent_return_pct(btc_points, lookback_points=lookback_points)
    if symbol_return is None or btc_return is None:
        return ("insufficient_data", None)
    difference = symbol_return - btc_return
    if difference >= Decimal("0.005"):
        return ("outperforming_btc", difference * Decimal("100"))
    if difference <= Decimal("-0.005"):
        return ("underperforming_btc", difference * Decimal("100"))
    return ("in_line", difference * Decimal("100"))
