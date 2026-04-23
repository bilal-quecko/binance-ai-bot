from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.analysis.symbol_sentiment import SymbolSentimentService
from app.market_data.candles import Candle
from app.sentiment.models import SentimentComponent, SymbolSentimentContext
from app.sentiment.sources import SymbolSentimentSourceResult


class StaticSource:
    def __init__(self, component: SentimentComponent | None, note: str | None = None) -> None:
        self._component = component
        self._note = note

    def collect(self, context: SymbolSentimentContext) -> SymbolSentimentSourceResult:
        return SymbolSentimentSourceResult(component=self._component, weakening_note=self._note)


def _candle(
    *,
    symbol: str,
    close: str,
    index: int,
    volume: str = "10",
    quote_volume: str | None = None,
    trade_count: int = 100,
) -> Candle:
    open_time = datetime(2024, 3, 9, 12, 0, tzinfo=UTC) + timedelta(minutes=index)
    close_time = open_time + timedelta(minutes=1) - timedelta(milliseconds=1)
    close_decimal = Decimal(close)
    quote = Decimal(quote_volume) if quote_volume is not None else close_decimal * Decimal(volume)
    return Candle(
        symbol=symbol,
        timeframe="1m",
        open=close_decimal,
        high=close_decimal + Decimal("0.4"),
        low=close_decimal - Decimal("0.4"),
        close=close_decimal,
        volume=Decimal(volume),
        quote_volume=quote,
        open_time=open_time,
        close_time=close_time,
        event_time=close_time,
        trade_count=trade_count,
        is_closed=True,
    )


def _candles(symbol: str, closes: list[str]) -> list[Candle]:
    return [_candle(symbol=symbol, close=close, index=index) for index, close in enumerate(closes)]


def test_symbol_sentiment_detects_bullish_proxy_state() -> None:
    service = SymbolSentimentService(
        sources=[
            StaticSource(
                SentimentComponent(
                    name="price_acceleration",
                    score=Decimal("0.74"),
                    weight=Decimal("0.30"),
                    explanation="Price acceleration is bullish with expanding participation.",
                )
            ),
            StaticSource(
                SentimentComponent(
                    name="search_social_proxy",
                    score=Decimal("0.58"),
                    weight=Decimal("0.22"),
                    explanation="Social/search proxy is bullish with rising attention.",
                )
            ),
            StaticSource(
                SentimentComponent(
                    name="exchange_activity_proxy",
                    score=Decimal("0.42"),
                    weight=Decimal("0.20"),
                    explanation="Exchange activity is bullish with stronger trade flow.",
                )
            ),
        ]
    )

    snapshot = service.analyze(
        symbol="XRPUSDT",
        candles=_candles("XRPUSDT", ["100", "100.8", "101.4", "102.0", "102.9", "103.5", "104.2", "105.0"]),
        benchmark_symbol="BTCUSDT",
        benchmark_closes=[Decimal("100"), Decimal("100.2"), Decimal("100.4"), Decimal("100.6"), Decimal("100.9"), Decimal("101.1")],
    )

    assert snapshot.data_state == "ready"
    assert snapshot.label == "bullish"
    assert snapshot.score is not None and snapshot.score > 35
    assert snapshot.confidence is not None and snapshot.confidence >= 40
    assert snapshot.momentum_state == "rising"
    assert snapshot.risk_flag in {"normal", "hype"}


def test_symbol_sentiment_detects_bearish_proxy_state() -> None:
    service = SymbolSentimentService(
        sources=[
            StaticSource(
                SentimentComponent(
                    name="price_acceleration",
                    score=Decimal("-0.68"),
                    weight=Decimal("0.30"),
                    explanation="Price acceleration is bearish with worsening trend pressure.",
                )
            ),
            StaticSource(
                SentimentComponent(
                    name="volatility_shock",
                    score=Decimal("-0.55"),
                    weight=Decimal("0.18"),
                    explanation="Volatility shock is bearish after a sharp downside move.",
                )
            ),
            StaticSource(
                SentimentComponent(
                    name="exchange_activity_proxy",
                    score=Decimal("-0.40"),
                    weight=Decimal("0.20"),
                    explanation="Exchange activity is bearish with heavy sell-side participation.",
                )
            ),
        ]
    )

    snapshot = service.analyze(
        symbol="ADAUSDT",
        candles=_candles("ADAUSDT", ["100", "99.4", "98.9", "98.2", "97.7", "97.0", "96.5", "95.9"]),
        benchmark_symbol="BTCUSDT",
        benchmark_closes=[Decimal("100"), Decimal("99.9"), Decimal("99.8"), Decimal("99.7"), Decimal("99.6"), Decimal("99.5")],
    )

    assert snapshot.data_state == "ready"
    assert snapshot.label == "bearish"
    assert snapshot.score is not None and snapshot.score < -35
    assert snapshot.confidence is not None and snapshot.confidence >= 40
    assert snapshot.momentum_state == "fading"
    assert snapshot.risk_flag in {"normal", "panic"}


def test_symbol_sentiment_detects_mixed_proxy_state() -> None:
    service = SymbolSentimentService(
        sources=[
            StaticSource(
                SentimentComponent(
                    name="price_acceleration",
                    score=Decimal("0.72"),
                    weight=Decimal("0.30"),
                    explanation="Price acceleration is bullish after a quick rebound.",
                )
            ),
            StaticSource(
                SentimentComponent(
                    name="volatility_shock",
                    score=Decimal("-0.66"),
                    weight=Decimal("0.24"),
                    explanation="Volatility shock is bearish because the rebound remains unstable.",
                )
            ),
            StaticSource(
                SentimentComponent(
                    name="search_social_proxy",
                    score=Decimal("0.02"),
                    weight=Decimal("0.10"),
                    explanation="Search/social proxy is roughly neutral.",
                )
            ),
        ]
    )

    snapshot = service.analyze(
        symbol="SOLUSDT",
        candles=_candles("SOLUSDT", ["100", "99.2", "98.6", "99.3", "98.9", "99.7", "99.4", "100.1"]),
        benchmark_symbol="BTCUSDT",
        benchmark_closes=[Decimal("100"), Decimal("99.8"), Decimal("99.6"), Decimal("99.7"), Decimal("99.8"), Decimal("99.9")],
    )

    assert snapshot.data_state == "ready"
    assert snapshot.label == "mixed"
    assert snapshot.score is not None and -25 <= snapshot.score <= 25
    assert snapshot.confidence is not None and snapshot.confidence < 70
    assert snapshot.explanation


def test_symbol_sentiment_returns_insufficient_data_without_proxy_inputs() -> None:
    service = SymbolSentimentService(sources=[StaticSource(component=None, note="Price acceleration proxy needs more candles.")])

    snapshot = service.analyze(
        symbol="BTCUSDT",
        candles=[],
        benchmark_symbol=None,
        benchmark_closes=[],
    )

    assert snapshot.data_state == "incomplete"
    assert snapshot.label == "insufficient_data"
    assert snapshot.score is None
    assert snapshot.confidence is None
    assert snapshot.momentum_state == "unknown"
    assert snapshot.risk_flag == "unknown"
    assert snapshot.components == ()
