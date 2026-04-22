"""Symbol-scoped external sentiment analysis."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from app.analysis.sentiment_scoring import (
    FreshnessState,
    SentimentState,
    score_symbol_sentiment,
)
from app.data.news_service import NewsService


AnalysisState = Literal["ready", "incomplete"]


@dataclass(slots=True)
class SymbolSentimentSnapshot:
    """Typed symbol-scoped sentiment payload."""

    symbol: str
    generated_at: datetime
    data_state: AnalysisState
    status_message: str | None
    sentiment_state: SentimentState
    sentiment_score: int | None
    source_count: int
    freshness: FreshnessState
    freshness_minutes: int | None
    confidence: int | None
    evidence_summary: tuple[str, ...]
    explanation: str


class SymbolSentimentService:
    """Build a symbol-scoped sentiment view from explicit external evidence."""

    def __init__(self, *, news_service: NewsService) -> None:
        self._news_service = news_service

    def analyze(self, *, symbol: str) -> SymbolSentimentSnapshot:
        """Return a symbol-scoped sentiment snapshot for one selected symbol."""

        normalized_symbol = symbol.strip().upper()
        scored = score_symbol_sentiment(
            symbol=normalized_symbol,
            evidence=self._news_service.load_symbol_evidence(normalized_symbol),
        )
        incomplete = scored.sentiment_state == "insufficient_data"
        status_message = (
            f"Symbol sentiment is ready for {normalized_symbol}."
            if not incomplete
            else f"Symbol sentiment for {normalized_symbol} is insufficient until source-backed evidence becomes available."
        )
        return SymbolSentimentSnapshot(
            symbol=normalized_symbol,
            generated_at=datetime.now(tz=UTC),
            data_state="incomplete" if incomplete else "ready",
            status_message=status_message,
            sentiment_state=scored.sentiment_state,
            sentiment_score=scored.sentiment_score,
            source_count=scored.source_count,
            freshness=scored.freshness,
            freshness_minutes=scored.freshness_minutes,
            confidence=scored.confidence,
            evidence_summary=scored.evidence_summary,
            explanation=scored.explanation,
        )
