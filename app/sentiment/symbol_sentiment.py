"""Symbol-scoped sentiment service using deterministic proxy inputs."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from app.market_data.candles import Candle
from app.sentiment.models import SymbolSentimentContext, SymbolSentimentSnapshot
from app.sentiment.scoring import score_symbol_sentiment
from app.sentiment.sources import SymbolSentimentSource, default_symbol_sentiment_sources


class SymbolSentimentService:
    """Build symbol sentiment from deterministic proxies and future source adapters."""

    def __init__(self, sources: Sequence[SymbolSentimentSource] | None = None) -> None:
        self._sources = tuple(sources or default_symbol_sentiment_sources())

    def analyze(
        self,
        *,
        symbol: str,
        candles: Sequence[Candle],
        benchmark_symbol: str | None = None,
        benchmark_closes: Sequence = (),
    ) -> SymbolSentimentSnapshot:
        """Return a symbol-scoped sentiment snapshot for one selected symbol."""

        normalized_symbol = symbol.strip().upper()
        generated_at = datetime.now(tz=UTC)
        closed_candles = tuple(candle for candle in candles if candle.is_closed)
        context = SymbolSentimentContext(
            symbol=normalized_symbol,
            generated_at=generated_at,
            candles=closed_candles,
            benchmark_symbol=benchmark_symbol,
            benchmark_closes=tuple(benchmark_closes),
        )

        components = []
        missing_inputs: list[str] = []
        for source in self._sources:
            result = source.collect(context)
            if result.component is not None:
                components.append(result.component)
            elif result.weakening_note:
                missing_inputs.append(result.weakening_note)

        scored = score_symbol_sentiment(
            symbol=normalized_symbol,
            candles=closed_candles,
            components=components,
            missing_inputs=missing_inputs,
        )
        incomplete = scored.label == "insufficient_data"
        status_message = (
            f"Proxy sentiment is ready for {normalized_symbol}."
            if not incomplete
            else f"Proxy sentiment for {normalized_symbol} still needs more live history."
        )
        return SymbolSentimentSnapshot(
            symbol=normalized_symbol,
            generated_at=generated_at,
            data_state="incomplete" if incomplete else "ready",
            status_message=status_message,
            score=scored.score,
            label=scored.label,
            confidence=scored.confidence,
            momentum_state=scored.momentum_state,
            risk_flag=scored.risk_flag,
            explanation=scored.explanation,
            source_mode="proxy",
            components=scored.components,
        )
