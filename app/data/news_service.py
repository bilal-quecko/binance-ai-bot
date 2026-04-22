"""Symbol-scoped news and evidence aggregation for sentiment analysis."""

from __future__ import annotations

from collections.abc import Iterable

from app.data.sentiment_sources import SymbolSentimentEvidence, SymbolSentimentSource


class NewsService:
    """Aggregate symbol-scoped sentiment evidence from configured sources."""

    def __init__(self, sources: Iterable[SymbolSentimentSource] | None = None) -> None:
        self._sources = tuple(sources or ())

    def load_symbol_evidence(self, symbol: str) -> list[SymbolSentimentEvidence]:
        """Return combined symbol-scoped evidence from every configured source."""

        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            return []

        evidence: list[SymbolSentimentEvidence] = []
        for source in self._sources:
            evidence.extend(source.fetch_symbol_sentiment(symbol=normalized_symbol))
        evidence.sort(key=lambda item: item.published_at, reverse=True)
        return evidence

