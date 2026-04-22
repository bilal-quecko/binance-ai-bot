"""Deterministic scoring helpers for symbol-scoped sentiment evidence."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from app.data.sentiment_sources import SymbolSentimentEvidence


SentimentState = Literal["bullish", "bearish", "neutral", "mixed", "insufficient_data"]
FreshnessState = Literal["fresh", "recent", "stale", "unknown"]


@dataclass(slots=True)
class SymbolSentimentScore:
    """Deterministic scored sentiment output for one symbol."""

    sentiment_state: SentimentState
    sentiment_score: int | None
    source_count: int
    freshness: FreshnessState
    freshness_minutes: int | None
    confidence: int | None
    evidence_summary: tuple[str, ...]
    explanation: str


def score_symbol_sentiment(
    *,
    symbol: str,
    evidence: Sequence[SymbolSentimentEvidence],
    now: datetime | None = None,
) -> SymbolSentimentScore:
    """Score symbol-scoped sentiment from explicit source-backed evidence."""

    timestamp = now or datetime.now(tz=UTC)
    if not evidence:
        return SymbolSentimentScore(
            sentiment_state="insufficient_data",
            sentiment_score=None,
            source_count=0,
            freshness="unknown",
            freshness_minutes=None,
            confidence=None,
            evidence_summary=(),
            explanation=(
                f"No configured symbol-sentiment sources returned usable external evidence for {symbol}, so sentiment stays insufficient."
            ),
        )

    weighted_sum = Decimal("0")
    total_weight = Decimal("0")
    bullish_count = 0
    bearish_count = 0
    latest_age_minutes = max(
        0,
        int((timestamp - max(item.published_at for item in evidence)).total_seconds() // 60),
    )
    evidence_summaries: list[str] = []

    for item in evidence:
        age_minutes = max(0, int((timestamp - item.published_at).total_seconds() // 60))
        recency_weight = _recency_weight(age_minutes)
        confidence_weight = Decimal(item.confidence) / Decimal("100")
        weight = recency_weight * confidence_weight
        score = max(Decimal("-1"), min(Decimal("1"), item.sentiment_score))
        weighted_sum += score * weight
        total_weight += weight
        if score >= Decimal("0.20"):
            bullish_count += 1
        elif score <= Decimal("-0.20"):
            bearish_count += 1
        evidence_summaries.append(f"{item.source_name}: {item.headline}")

    if total_weight <= 0:
        return SymbolSentimentScore(
            sentiment_state="insufficient_data",
            sentiment_score=None,
            source_count=len(evidence),
            freshness=_classify_freshness(latest_age_minutes),
            freshness_minutes=latest_age_minutes,
            confidence=None,
            evidence_summary=tuple(evidence_summaries[:3]),
            explanation=(
                f"Symbol sentiment for {symbol} has evidence records, but none were fresh and confident enough to score cleanly."
            ),
        )

    normalized_score = weighted_sum / total_weight
    sentiment_score = _to_sentiment_score(normalized_score)
    sentiment_state = _classify_sentiment_state(
        normalized_score=normalized_score,
        bullish_count=bullish_count,
        bearish_count=bearish_count,
    )
    confidence = _shape_confidence(
        normalized_score=normalized_score,
        evidence_count=len(evidence),
        bullish_count=bullish_count,
        bearish_count=bearish_count,
        latest_age_minutes=latest_age_minutes,
    )
    freshness = _classify_freshness(latest_age_minutes)

    return SymbolSentimentScore(
        sentiment_state=sentiment_state,
        sentiment_score=sentiment_score,
        source_count=len(evidence),
        freshness=freshness,
        freshness_minutes=latest_age_minutes,
        confidence=confidence,
        evidence_summary=tuple(evidence_summaries[:3]),
        explanation=_build_explanation(
            symbol=symbol,
            sentiment_state=sentiment_state,
            confidence=confidence,
            freshness=freshness,
            source_count=len(evidence),
            bullish_count=bullish_count,
            bearish_count=bearish_count,
        ),
    )


def _recency_weight(age_minutes: int) -> Decimal:
    """Return a deterministic recency weight for one evidence item."""

    if age_minutes <= 180:
        return Decimal("1.0")
    if age_minutes <= 720:
        return Decimal("0.75")
    if age_minutes <= 1_440:
        return Decimal("0.5")
    if age_minutes <= 4_320:
        return Decimal("0.25")
    return Decimal("0.10")


def _to_sentiment_score(normalized_score: Decimal) -> int:
    """Convert a normalized `[-1, 1]` score to a bounded `0..100` score."""

    scaled = ((normalized_score + Decimal("1")) / Decimal("2")) * Decimal("100")
    return int(max(Decimal("0"), min(Decimal("100"), scaled)).quantize(Decimal("1")))


def _classify_sentiment_state(
    *,
    normalized_score: Decimal,
    bullish_count: int,
    bearish_count: int,
) -> SentimentState:
    """Map weighted evidence into a readable sentiment label."""

    if bullish_count > 0 and bearish_count > 0 and abs(normalized_score) < Decimal("0.25"):
        return "mixed"
    if normalized_score >= Decimal("0.25"):
        return "bullish"
    if normalized_score <= Decimal("-0.25"):
        return "bearish"
    if bullish_count > 0 and bearish_count > 0:
        return "mixed"
    return "neutral"


def _shape_confidence(
    *,
    normalized_score: Decimal,
    evidence_count: int,
    bullish_count: int,
    bearish_count: int,
    latest_age_minutes: int,
) -> int:
    """Return a bounded confidence score for the symbol-sentiment view."""

    score_strength = min(Decimal("1"), abs(normalized_score))
    confidence = int((score_strength * Decimal("55")).quantize(Decimal("1")))
    confidence += min(20, evidence_count * 5)
    if bullish_count > 0 and bearish_count > 0:
        confidence -= 18
    if latest_age_minutes > 720:
        confidence -= 12
    elif latest_age_minutes > 180:
        confidence -= 6
    return max(5, min(95, confidence))


def _classify_freshness(age_minutes: int | None) -> FreshnessState:
    """Map evidence age into a readable freshness bucket."""

    if age_minutes is None:
        return "unknown"
    if age_minutes <= 180:
        return "fresh"
    if age_minutes <= 1_440:
        return "recent"
    return "stale"


def _build_explanation(
    *,
    symbol: str,
    sentiment_state: SentimentState,
    confidence: int | None,
    freshness: FreshnessState,
    source_count: int,
    bullish_count: int,
    bearish_count: int,
) -> str:
    """Build a concise explanation for the symbol-sentiment result."""

    if sentiment_state == "insufficient_data":
        return f"Symbol sentiment for {symbol} is insufficient because no usable external evidence was available."

    parts = [
        f"Symbol sentiment for {symbol} reads {sentiment_state}.",
        f"{source_count} source-backed items were available.",
    ]
    if bullish_count > 0 or bearish_count > 0:
        parts.append(
            f"Evidence split: {bullish_count} bullish and {bearish_count} bearish items."
        )
    parts.append(f"Freshness is {freshness}.")
    if confidence is not None:
        parts.append(f"Confidence is {confidence}/100.")
    return " ".join(parts)
