"""Trade-blocker categorization and analytics."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.storage.models import RunnerEventRecord

BLOCKER_CATEGORIES: tuple[str, ...] = (
    "insufficient_history",
    "weak_signal",
    "low_volatility",
    "volatility_too_high",
    "spread_too_wide",
    "edge_below_costs",
    "no_trend_confirmation",
    "position_limit",
    "daily_loss_limit",
    "no_position_to_exit",
    "unknown",
)

_CATEGORY_EXPLANATIONS: dict[str, str] = {
    "insufficient_history": "The bot needs more closed candles or feature context before it can trade.",
    "weak_signal": "The setup did not produce enough deterministic trend or momentum evidence.",
    "low_volatility": "Market movement is too small for a useful paper trade after costs.",
    "volatility_too_high": "Volatility is outside the configured risk envelope.",
    "spread_too_wide": "The bid/ask spread or microstructure quality is not acceptable.",
    "edge_below_costs": "Expected edge does not clear estimated fees, slippage, and buffer.",
    "no_trend_confirmation": "Trend or regime confirmation is missing.",
    "position_limit": "The configured open-position limit is already reached.",
    "daily_loss_limit": "The daily loss protection gate is active.",
    "no_position_to_exit": "An exit was requested, but there is no paper position to close.",
    "unknown": "The event did not include a recognized blocker code.",
}

_NEXT_ACTIONS: dict[str, str] = {
    "insufficient_history": "Let backfill/runtime collect more candles, then recheck the symbol.",
    "weak_signal": "Wait for stronger trend, EMA, or momentum confirmation.",
    "low_volatility": "Use a more active symbol or wait for volatility to return.",
    "volatility_too_high": "Wait for volatility to normalize before allowing paper entries.",
    "spread_too_wide": "Avoid entries until liquidity and spread improve.",
    "edge_below_costs": "Wait for a cleaner edge or review fee/slippage assumptions.",
    "no_trend_confirmation": "Wait for regime confirmation or scan stronger symbols.",
    "position_limit": "Close an existing paper position or raise the paper-only position limit deliberately.",
    "daily_loss_limit": "Stop trading for the day or reset only after reviewing losses.",
    "no_position_to_exit": "Open a paper position before testing close flow.",
    "unknown": "Inspect recent event payloads for unmapped blocker codes.",
}

_REASON_CATEGORY_MAP: dict[str, str] = {
    "WAITING_FOR_HISTORY": "insufficient_history",
    "MISSING_EMA": "insufficient_history",
    "MISSING_ATR_CONTEXT": "insufficient_history",
    "INSUFFICIENT_HISTORY": "insufficient_history",
    "NON_ACTIONABLE_SIGNAL": "weak_signal",
    "MOMENTUM_TOO_WEAK": "weak_signal",
    "EMA_GAP_TOO_SMALL": "weak_signal",
    "EMA_NOT_BULLISH": "weak_signal",
    "SIZE_BELOW_MINIMUM": "weak_signal",
    "VOL_TOO_LOW": "low_volatility",
    "VOL_TOO_HIGH": "volatility_too_high",
    "VOLATILITY_UNSAFE": "volatility_too_high",
    "MICROSTRUCTURE_UNHEALTHY": "spread_too_wide",
    "SPREAD_UNSAFE": "spread_too_wide",
    "EDGE_BELOW_COSTS": "edge_below_costs",
    "EXPECTED_EDGE_TOO_SMALL": "edge_below_costs",
    "REGIME_NOT_TREND": "no_trend_confirmation",
    "REGIME_NOT_SUPPORTED": "no_trend_confirmation",
    "OPEN_POSITION_LIMIT": "position_limit",
    "POSITION_LIMIT": "position_limit",
    "DAILY_LOSS_LIMIT": "daily_loss_limit",
    "daily_loss_limit_reached": "daily_loss_limit",
    "NO_POSITION_TO_EXIT": "no_position_to_exit",
}


@dataclass(slots=True)
class BlockerGroup:
    """Aggregate count for one blocker category."""

    category: str
    count: int
    percentage: float
    explanation: str


@dataclass(slots=True)
class RecentBlocker:
    """Recent blocker event used by the operator panel."""

    symbol: str
    event_type: str
    category: str
    message: str
    reason_codes: tuple[str, ...]
    event_time: datetime


@dataclass(slots=True)
class BlockerAnalytics:
    """Summary of recent no-trade blockers."""

    symbol: str | None
    total_events: int
    groups: list[BlockerGroup]
    most_common_blocker: str | None
    explanation: str
    next_suggested_action: str
    recent_blockers: list[RecentBlocker]


def categorize_blocker(reason_codes: tuple[str, ...] | list[str] | None, message: str | None = None) -> str:
    """Return the canonical blocker category for reason codes or message text."""

    for reason_code in reason_codes or ():
        category = _REASON_CATEGORY_MAP.get(str(reason_code))
        if category is not None:
            return category
    normalized_message = (message or "").lower()
    for phrase, category in (
        ("history", "insufficient_history"),
        ("volatility too low", "low_volatility"),
        ("volatility", "volatility_too_high"),
        ("spread", "spread_too_wide"),
        ("edge", "edge_below_costs"),
        ("trend", "no_trend_confirmation"),
        ("position limit", "position_limit"),
        ("daily loss", "daily_loss_limit"),
        ("no position", "no_position_to_exit"),
    ):
        if phrase in normalized_message:
            return category
    return "unknown"


def blocker_explanation(category: str) -> str:
    """Return a trader-readable explanation for one blocker category."""

    return _CATEGORY_EXPLANATIONS.get(category, _CATEGORY_EXPLANATIONS["unknown"])


def blocker_next_action(category: str) -> str:
    """Return the suggested next operator action for one blocker category."""

    return _NEXT_ACTIONS.get(category, _NEXT_ACTIONS["unknown"])


def summarize_blockers(
    events: list[RunnerEventRecord],
    *,
    symbol: str | None,
    limit: int,
) -> BlockerAnalytics:
    """Summarize recent trade blocker, risk, and execution events."""

    relevant = [
        event
        for event in events
        if event.event_type in {"trade_blocked", "risk_decision", "execution_result"}
    ]
    recent_events = sorted(relevant, key=lambda event: event.event_time, reverse=True)[:limit]
    recent_blockers: list[RecentBlocker] = []
    counter: Counter[str] = Counter()
    for event in recent_events:
        payload = _payload(event)
        reason_codes = _reason_codes(payload)
        decision = str(payload.get("decision", ""))
        status = str(payload.get("status", ""))
        if event.event_type == "risk_decision" and decision in {"approve", "resize"}:
            continue
        if event.event_type == "execution_result" and status == "executed":
            continue
        category = str(payload.get("blocker_category") or categorize_blocker(reason_codes, event.message))
        counter[category] += 1
        recent_blockers.append(
            RecentBlocker(
                symbol=event.symbol,
                event_type=event.event_type,
                category=category,
                message=event.message,
                reason_codes=reason_codes,
                event_time=event.event_time,
            )
        )

    total = sum(counter.values())
    groups = [
        BlockerGroup(
            category=category,
            count=count,
            percentage=(count / total * 100) if total else 0.0,
            explanation=blocker_explanation(category),
        )
        for category, count in counter.most_common()
    ]
    most_common = groups[0].category if groups else None
    return BlockerAnalytics(
        symbol=symbol.upper() if symbol else None,
        total_events=total,
        groups=groups,
        most_common_blocker=most_common,
        explanation=blocker_explanation(most_common or "unknown") if total else "No recent blockers found.",
        next_suggested_action=blocker_next_action(most_common or "unknown") if total else "Run the paper bot or scanner to collect trade-attempt events.",
        recent_blockers=recent_blockers,
    )


def _payload(event: RunnerEventRecord) -> dict[str, Any]:
    try:
        payload = json.loads(event.payload_json)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _reason_codes(payload: dict[str, Any]) -> tuple[str, ...]:
    raw = payload.get("reason_codes")
    if isinstance(raw, list | tuple):
        return tuple(str(item) for item in raw)
    if isinstance(raw, str):
        return (raw,)
    return ()
