"""Scoring helpers for symbol-scoped sentiment intelligence."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.market_data.candles import Candle
from app.sentiment.models import MomentumState, RiskFlag, SentimentComponent, SentimentLabel


@dataclass(slots=True)
class SymbolSentimentScore:
    """Scored symbol-sentiment result before API serialization."""

    score: int | None
    label: SentimentLabel
    confidence: int | None
    momentum_state: MomentumState
    risk_flag: RiskFlag
    explanation: str
    components: tuple[SentimentComponent, ...]


def score_symbol_sentiment(
    *,
    symbol: str,
    candles: Sequence[Candle],
    components: Sequence[SentimentComponent],
    missing_inputs: Sequence[str],
) -> SymbolSentimentScore:
    """Score symbol sentiment from deterministic proxy components."""

    if not components:
        return SymbolSentimentScore(
            score=None,
            label="insufficient_data",
            confidence=None,
            momentum_state="unknown",
            risk_flag="unknown",
            explanation=(
                f"Symbol sentiment for {symbol} is unavailable because proxy inputs are incomplete. "
                + " ".join(missing_inputs[:2])
            ).strip(),
            components=(),
        )

    weighted_sum = Decimal("0")
    total_weight = Decimal("0")
    bullish_components = 0
    bearish_components = 0
    for component in components:
        weighted_sum += component.score * component.weight
        total_weight += component.weight
        if component.score >= Decimal("0.20"):
            bullish_components += 1
        elif component.score <= Decimal("-0.20"):
            bearish_components += 1

    normalized_score = weighted_sum / total_weight if total_weight > Decimal("0") else Decimal("0")
    final_score = int((normalized_score * Decimal("100")).to_integral_value(rounding=ROUND_HALF_UP))
    label = _label_from_score(normalized_score, bullish_components, bearish_components)
    confidence = _confidence_from_components(normalized_score, components, bullish_components, bearish_components)
    momentum_state = _momentum_state(candles, normalized_score)
    risk_flag = _risk_flag(components, final_score)

    return SymbolSentimentScore(
        score=final_score,
        label=label,
        confidence=confidence,
        momentum_state=momentum_state,
        risk_flag=risk_flag,
        explanation=_build_explanation(
            symbol=symbol,
            label=label,
            confidence=confidence,
            risk_flag=risk_flag,
            components=components,
            missing_inputs=missing_inputs,
        ),
        components=tuple(components),
    )


def _label_from_score(
    normalized_score: Decimal,
    bullish_components: int,
    bearish_components: int,
) -> SentimentLabel:
    """Map weighted score and component conflict into a readable label."""

    if bullish_components > 0 and bearish_components > 0 and abs(normalized_score) < Decimal("0.22"):
        return "mixed"
    if normalized_score >= Decimal("0.18"):
        return "bullish"
    if normalized_score <= Decimal("-0.18"):
        return "bearish"
    if bullish_components > 0 and bearish_components > 0:
        return "mixed"
    return "neutral"


def _confidence_from_components(
    normalized_score: Decimal,
    components: Sequence[SentimentComponent],
    bullish_components: int,
    bearish_components: int,
) -> int:
    """Shape confidence from strength, agreement, and component breadth."""

    strength = min(Decimal("1"), abs(normalized_score))
    confidence = int((strength * Decimal("45")).to_integral_value(rounding=ROUND_HALF_UP))
    confidence += min(30, len(components) * 10)
    if bullish_components > 0 and bearish_components > 0:
        confidence -= 18
    if len(components) < 3:
        confidence -= 10
    return max(10, min(95, confidence))


def _momentum_state(candles: Sequence[Candle], normalized_score: Decimal) -> MomentumState:
    """Return a short-horizon sentiment momentum label."""

    if len(candles) < 6:
        return "unknown"

    closes = [candle.close for candle in candles]
    latest_direction = closes[-1] - closes[-2]
    previous_direction = closes[-2] - closes[-3]
    recent_strength = (closes[-1] - closes[-4]) / closes[-4] if closes[-4] != Decimal("0") else Decimal("0")

    if normalized_score > Decimal("0.15") and latest_direction > Decimal("0") and previous_direction > Decimal("0"):
        return "rising"
    if normalized_score < Decimal("-0.15") and latest_direction < Decimal("0") and previous_direction < Decimal("0"):
        return "fading"
    if abs(recent_strength) < Decimal("0.002"):
        return "stable"
    if latest_direction == Decimal("0"):
        return "stable"
    return "rising" if recent_strength > Decimal("0") else "fading"


def _risk_flag(components: Sequence[SentimentComponent], final_score: int) -> RiskFlag:
    """Classify obvious hype/panic conditions from proxy components."""

    components_by_name = {component.name: component for component in components}
    volatility = components_by_name.get("volatility_shock")
    social = components_by_name.get("search_social_proxy")
    activity = components_by_name.get("exchange_activity_proxy")

    if (
        final_score >= 35
        and volatility is not None
        and social is not None
        and activity is not None
        and volatility.score >= Decimal("0.45")
        and social.score >= Decimal("0.35")
        and activity.score >= Decimal("0.30")
    ):
        return "hype"
    if (
        final_score <= -35
        and volatility is not None
        and social is not None
        and activity is not None
        and volatility.score <= Decimal("-0.45")
        and social.score <= Decimal("-0.25")
        and activity.score <= Decimal("-0.25")
    ):
        return "panic"
    return "normal"


def _build_explanation(
    *,
    symbol: str,
    label: SentimentLabel,
    confidence: int | None,
    risk_flag: RiskFlag,
    components: Sequence[SentimentComponent],
    missing_inputs: Sequence[str],
) -> str:
    """Build a short human-readable sentiment explanation."""

    if label == "insufficient_data":
        return f"Symbol sentiment for {symbol} is unavailable because proxy sentiment inputs are still incomplete."

    ranked_components = sorted(components, key=lambda item: abs(item.score), reverse=True)
    top_components = ranked_components[:2]
    parts = [
        f"Proxy symbol sentiment for {symbol} reads {label}.",
        " ".join(component.explanation for component in top_components),
    ]
    if confidence is not None:
        parts.append(f"Confidence is {confidence}/100.")
    if risk_flag != "normal":
        parts.append(f"Risk flag is {risk_flag}.")
    if missing_inputs:
        parts.append("Remaining gaps: " + " ".join(missing_inputs[:2]))
    return " ".join(part for part in parts if part).strip()
