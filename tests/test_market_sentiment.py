from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.analysis.market_sentiment import MarketSentimentService
from app.data import MarketContextPoint


def _points(
    symbol: str,
    prices: list[str],
    *,
    start: datetime | None = None,
) -> list[MarketContextPoint]:
    baseline = start or datetime(2024, 3, 9, 12, 0, tzinfo=UTC)
    return [
        MarketContextPoint(
            symbol=symbol,
            timestamp=baseline + timedelta(minutes=index),
            close_price=Decimal(price),
        )
        for index, price in enumerate(prices)
    ]


def _trend_prices(
    *,
    start: Decimal,
    step: Decimal,
    count: int = 90,
) -> list[str]:
    return [str(start + (step * Decimal(index))) for index in range(count)]


def test_market_sentiment_detects_bullish_broad_market() -> None:
    service = MarketSentimentService()

    snapshot = service.analyze(
        symbol="SOLUSDT",
        symbol_points={
            "BTCUSDT": _points("BTCUSDT", _trend_prices(start=Decimal("100"), step=Decimal("0.35"))),
            "ETHUSDT": _points("ETHUSDT", _trend_prices(start=Decimal("50"), step=Decimal("0.25"))),
            "SOLUSDT": _points("SOLUSDT", _trend_prices(start=Decimal("20"), step=Decimal("0.20"))),
            "BNBUSDT": _points("BNBUSDT", _trend_prices(start=Decimal("30"), step=Decimal("0.12"))),
            "XRPUSDT": _points("XRPUSDT", _trend_prices(start=Decimal("10"), step=Decimal("0.04"))),
        },
    )

    assert snapshot.data_state == "ready"
    assert snapshot.market_state == "risk_on"
    assert snapshot.sentiment_score is not None
    assert snapshot.sentiment_score >= 65
    assert snapshot.btc_bias == "bullish"
    assert snapshot.eth_bias == "bullish"
    assert snapshot.market_breadth_state == "positive"
    assert snapshot.selected_symbol_relative_strength == "outperforming_btc"


def test_market_sentiment_detects_bearish_broad_market() -> None:
    service = MarketSentimentService()

    snapshot = service.analyze(
        symbol="ADAUSDT",
        symbol_points={
            "BTCUSDT": _points("BTCUSDT", _trend_prices(start=Decimal("150"), step=Decimal("-0.45"))),
            "ETHUSDT": _points("ETHUSDT", _trend_prices(start=Decimal("80"), step=Decimal("-0.30"))),
            "ADAUSDT": _points("ADAUSDT", _trend_prices(start=Decimal("40"), step=Decimal("-0.20"))),
            "BNBUSDT": _points("BNBUSDT", _trend_prices(start=Decimal("60"), step=Decimal("-0.18"))),
            "XRPUSDT": _points("XRPUSDT", _trend_prices(start=Decimal("12"), step=Decimal("-0.05"))),
        },
    )

    assert snapshot.data_state == "ready"
    assert snapshot.market_state == "risk_off"
    assert snapshot.sentiment_score is not None
    assert snapshot.sentiment_score <= 35
    assert snapshot.btc_bias == "bearish"
    assert snapshot.eth_bias == "bearish"
    assert snapshot.market_breadth_state == "negative"


def test_market_sentiment_detects_mixed_market() -> None:
    service = MarketSentimentService()

    btc_prices = []
    eth_prices = []
    sol_prices = []
    bnb_prices = []
    xrp_prices = []
    for index in range(90):
        btc_prices.append(str(Decimal("100") + Decimal(index) * Decimal("0.05")))
        eth_prices.append(str(Decimal("80") - Decimal(index) * Decimal("0.03")))
        sol_prices.append(str(Decimal("20") + (Decimal("0.12") if index % 2 == 0 else Decimal("-0.10")) * Decimal(index)))
        bnb_prices.append(str(Decimal("40") + (Decimal("0.07") if index % 3 == 0 else Decimal("-0.04")) * Decimal(index)))
        xrp_prices.append(str(Decimal("10") + (Decimal("0.03") if index % 4 == 0 else Decimal("-0.02")) * Decimal(index)))

    snapshot = service.analyze(
        symbol="SOLUSDT",
        symbol_points={
            "BTCUSDT": _points("BTCUSDT", btc_prices),
            "ETHUSDT": _points("ETHUSDT", eth_prices),
            "SOLUSDT": _points("SOLUSDT", sol_prices),
            "BNBUSDT": _points("BNBUSDT", bnb_prices),
            "XRPUSDT": _points("XRPUSDT", xrp_prices),
        },
    )

    assert snapshot.data_state == "ready"
    assert snapshot.market_state == "mixed"
    assert snapshot.sentiment_score is not None
    assert 35 < snapshot.sentiment_score < 65
    assert snapshot.market_breadth_state in {"mixed", "positive", "negative"}


def test_market_sentiment_returns_incomplete_state_when_btc_context_is_missing() -> None:
    service = MarketSentimentService()

    snapshot = service.analyze(
        symbol="XRPUSDT",
        symbol_points={
            "XRPUSDT": _points("XRPUSDT", _trend_prices(start=Decimal("10"), step=Decimal("0.03"), count=25)),
        },
    )

    assert snapshot.data_state == "incomplete"
    assert snapshot.market_state == "insufficient_data"
    assert snapshot.sentiment_score is None
    assert snapshot.btc_bias is None
    assert snapshot.explanation is None
