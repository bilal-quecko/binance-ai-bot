"""Source abstractions for symbol-scoped sentiment evidence."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol


@dataclass(slots=True)
class SymbolSentimentEvidence:
    """One source-backed sentiment item for a selected symbol."""

    symbol: str
    source_name: str
    published_at: datetime
    headline: str
    summary: str | None
    sentiment_score: Decimal
    confidence: int
    url: str | None = None


class SymbolSentimentSource(Protocol):
    """Protocol for symbol-scoped sentiment evidence providers."""

    def fetch_symbol_sentiment(
        self,
        *,
        symbol: str,
    ) -> Sequence[SymbolSentimentEvidence]:
        """Return source-backed sentiment evidence for one symbol."""

