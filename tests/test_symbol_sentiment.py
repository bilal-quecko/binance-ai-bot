from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.analysis.symbol_sentiment import SymbolSentimentService
from app.data.news_service import NewsService
from app.data.sentiment_sources import SymbolSentimentEvidence


class StaticSentimentSource:
    def __init__(self, evidence: list[SymbolSentimentEvidence]) -> None:
        self._evidence = evidence

    def fetch_symbol_sentiment(self, *, symbol: str) -> list[SymbolSentimentEvidence]:
        normalized_symbol = symbol.strip().upper()
        return [item for item in self._evidence if item.symbol == normalized_symbol]


def _evidence(
    *,
    symbol: str,
    source_name: str,
    score: str,
    confidence: int,
    headline: str,
    minutes_ago: int,
) -> SymbolSentimentEvidence:
    published_at = datetime.now(tz=UTC) - timedelta(minutes=minutes_ago)
    return SymbolSentimentEvidence(
        symbol=symbol,
        source_name=source_name,
        published_at=published_at,
        headline=headline,
        summary=None,
        sentiment_score=Decimal(score),
        confidence=confidence,
    )


def test_symbol_sentiment_detects_bullish_state() -> None:
    service = SymbolSentimentService(
        news_service=NewsService(
            [
                StaticSentimentSource(
                    [
                        _evidence(symbol="XRPUSDT", source_name="DeskA", score="0.80", confidence=82, headline="Strong partnership update", minutes_ago=20),
                        _evidence(symbol="XRPUSDT", source_name="DeskB", score="0.55", confidence=74, headline="Exchange liquidity improves", minutes_ago=55),
                    ]
                )
            ]
        )
    )

    snapshot = service.analyze(symbol="XRPUSDT")

    assert snapshot.data_state == "ready"
    assert snapshot.sentiment_state == "bullish"
    assert snapshot.sentiment_score is not None
    assert snapshot.sentiment_score >= 65
    assert snapshot.confidence is not None
    assert snapshot.source_count == 2
    assert snapshot.freshness == "fresh"
    assert len(snapshot.evidence_summary) == 2


def test_symbol_sentiment_detects_bearish_state() -> None:
    service = SymbolSentimentService(
        news_service=NewsService(
            [
                StaticSentimentSource(
                    [
                        _evidence(symbol="ADAUSDT", source_name="DeskA", score="-0.75", confidence=80, headline="Development delay concerns", minutes_ago=30),
                        _evidence(symbol="ADAUSDT", source_name="DeskB", score="-0.50", confidence=68, headline="Token unlock pressure discussed", minutes_ago=120),
                    ]
                )
            ]
        )
    )

    snapshot = service.analyze(symbol="ADAUSDT")

    assert snapshot.data_state == "ready"
    assert snapshot.sentiment_state == "bearish"
    assert snapshot.sentiment_score is not None
    assert snapshot.sentiment_score <= 35
    assert snapshot.confidence is not None
    assert snapshot.confidence >= 40


def test_symbol_sentiment_detects_mixed_state() -> None:
    service = SymbolSentimentService(
        news_service=NewsService(
            [
                StaticSentimentSource(
                    [
                        _evidence(symbol="SOLUSDT", source_name="DeskA", score="0.70", confidence=77, headline="Network growth accelerates", minutes_ago=25),
                        _evidence(symbol="SOLUSDT", source_name="DeskB", score="-0.62", confidence=75, headline="Outage fears return", minutes_ago=35),
                    ]
                )
            ]
        )
    )

    snapshot = service.analyze(symbol="SOLUSDT")

    assert snapshot.data_state == "ready"
    assert snapshot.sentiment_state == "mixed"
    assert snapshot.sentiment_score is not None
    assert 35 <= snapshot.sentiment_score <= 65
    assert snapshot.confidence is not None
    assert snapshot.confidence < 70


def test_symbol_sentiment_returns_insufficient_data_without_source_backing() -> None:
    service = SymbolSentimentService(news_service=NewsService())

    snapshot = service.analyze(symbol="BTCUSDT")

    assert snapshot.data_state == "incomplete"
    assert snapshot.sentiment_state == "insufficient_data"
    assert snapshot.sentiment_score is None
    assert snapshot.confidence is None
    assert snapshot.source_count == 0
    assert snapshot.evidence_summary == ()
