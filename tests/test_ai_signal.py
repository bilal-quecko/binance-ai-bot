from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.analysis.market_sentiment import MarketSentimentSnapshot
from app.analysis.technical import TechnicalAnalysisSnapshot
from app.ai.service import AISignalService
from app.features.models import FeatureSnapshot
from app.market_data.candles import Candle
from app.market_data.orderbook import TopOfBook


BASE_TIME = datetime(2024, 3, 9, 16, 0, 0, tzinfo=UTC)


def build_candle(
    index: int,
    close_price: str,
    *,
    open_price: str | None = None,
    high: str | None = None,
    low: str | None = None,
    volume: str = "10",
) -> Candle:
    close = Decimal(close_price)
    open_ = Decimal(open_price) if open_price is not None else close - Decimal("0.5")
    high_value = Decimal(high) if high is not None else max(open_, close) + Decimal("0.5")
    low_value = Decimal(low) if low is not None else min(open_, close) - Decimal("0.5")
    open_time = BASE_TIME + timedelta(minutes=index)
    close_time = open_time + timedelta(minutes=1) - timedelta(milliseconds=1)
    return Candle(
        symbol="BTCUSDT",
        timeframe="1m",
        open=open_,
        high=high_value,
        low=low_value,
        close=close,
        volume=Decimal(volume),
        quote_volume=close * Decimal(volume),
        open_time=open_time,
        close_time=close_time,
        event_time=close_time,
        trade_count=100 + index,
        is_closed=True,
    )


def build_top_of_book(price: str, *, spread: str = "0.10") -> TopOfBook:
    mid = Decimal(price)
    half_spread = Decimal(spread) / Decimal("2")
    return TopOfBook(
        symbol="BTCUSDT",
        bid_price=mid - half_spread,
        bid_quantity=Decimal("2"),
        ask_price=mid + half_spread,
        ask_quantity=Decimal("3"),
        event_time=BASE_TIME + timedelta(minutes=65),
    )


def build_feature_snapshot(**overrides: object) -> FeatureSnapshot:
    payload: dict[str, object] = {
        "symbol": "BTCUSDT",
        "timestamp": BASE_TIME + timedelta(minutes=65),
        "ema_fast": Decimal("105"),
        "ema_slow": Decimal("100"),
        "rsi": Decimal("60"),
        "atr": Decimal("1.2"),
        "mid_price": Decimal("106"),
        "bid_ask_spread": Decimal("0.10"),
        "order_book_imbalance": Decimal("0.20"),
        "regime": "bullish",
    }
    payload.update(overrides)
    return FeatureSnapshot(**payload)


def build_technical_analysis(**overrides: object) -> TechnicalAnalysisSnapshot:
    payload: dict[str, object] = {
        "symbol": "BTCUSDT",
        "timestamp": BASE_TIME + timedelta(minutes=65),
        "data_state": "ready",
        "status_message": "ready",
        "trend_direction": "bullish",
        "trend_strength": "strong",
        "trend_strength_score": 74,
        "support_levels": [Decimal("102")],
        "resistance_levels": [Decimal("108")],
        "momentum_state": "bullish",
        "volatility_regime": "normal",
        "breakout_readiness": "medium",
        "breakout_bias": "upside",
        "reversal_risk": "low",
        "multi_timeframe_agreement": "bullish_alignment",
        "timeframe_summaries": [],
        "explanation": "Strong uptrend.",
    }
    payload.update(overrides)
    return TechnicalAnalysisSnapshot(**payload)


def build_market_sentiment(**overrides: object) -> MarketSentimentSnapshot:
    payload: dict[str, object] = {
        "symbol": "BTCUSDT",
        "generated_at": BASE_TIME + timedelta(minutes=65),
        "data_state": "ready",
        "status_message": "ready",
        "market_state": "risk_on",
        "sentiment_score": 72,
        "btc_bias": "bullish",
        "eth_bias": "bullish",
        "selected_symbol_relative_strength": "outperforming_btc",
        "relative_strength_pct": Decimal("1.2"),
        "market_breadth_state": "positive",
        "breadth_advancing_symbols": 4,
        "breadth_declining_symbols": 1,
        "breadth_sample_size": 5,
        "volatility_environment": "normal",
        "explanation": "Broader market is supportive.",
    }
    payload.update(overrides)
    return MarketSentimentSnapshot(**payload)


def test_ai_signal_abstains_in_noisy_short_timeframe_conditions() -> None:
    service = AISignalService()
    candles = [
        build_candle(index, str(Decimal("100") + (Decimal("1.2") if index % 2 == 0 else Decimal("-1.1"))))
        for index in range(70)
    ]

    signal = service.build_signal(
        symbol="BTCUSDT",
        candles=candles,
        feature_snapshot=build_feature_snapshot(
            ema_fast=Decimal("100.2"),
            ema_slow=Decimal("100.1"),
            rsi=Decimal("51"),
            atr=Decimal("5.2"),
            mid_price=candles[-1].close,
            regime="neutral",
        ),
        top_of_book=build_top_of_book(str(candles[-1].close), spread="0.80"),
        technical_analysis=build_technical_analysis(
            trend_direction="sideways",
            trend_strength="weak",
            trend_strength_score=24,
            volatility_regime="high",
            breakout_readiness="low",
            breakout_bias="none",
            reversal_risk="medium",
            multi_timeframe_agreement="mixed",
        ),
        market_sentiment=build_market_sentiment(
            market_state="mixed",
            sentiment_score=48,
            selected_symbol_relative_strength="underperforming_btc",
            market_breadth_state="mixed",
        ),
        recent_false_positive_rate_5m=Decimal("42"),
        recent_false_reversal_rate_5m=Decimal("25"),
    )

    assert signal.abstain is True
    assert signal.suggested_action == "abstain"
    assert signal.regime in {"choppy", "high_volatility_unstable"}
    assert signal.confidence < 45
    assert signal.noise_level in {"high", "extreme"}
    assert any(item.horizon == "5m" and item.abstain for item in signal.horizon_signals)


def test_ai_signal_has_higher_confidence_in_clean_trending_conditions() -> None:
    service = AISignalService()
    candles = [build_candle(index, str(Decimal("100") + (Decimal(index) * Decimal("0.4")))) for index in range(70)]

    signal = service.build_signal(
        symbol="BTCUSDT",
        candles=candles,
        feature_snapshot=build_feature_snapshot(
            ema_fast=Decimal("128"),
            ema_slow=Decimal("121"),
            rsi=Decimal("63"),
            atr=Decimal("1.1"),
            mid_price=candles[-1].close,
            regime="bullish",
        ),
        top_of_book=build_top_of_book(str(candles[-1].close), spread="0.08"),
        technical_analysis=build_technical_analysis(
            trend_direction="bullish",
            trend_strength="strong",
            trend_strength_score=81,
            breakout_readiness="medium",
            breakout_bias="upside",
            reversal_risk="low",
            multi_timeframe_agreement="bullish_alignment",
        ),
        market_sentiment=build_market_sentiment(
            market_state="risk_on",
            sentiment_score=78,
            selected_symbol_relative_strength="outperforming_btc",
            market_breadth_state="positive",
        ),
        recent_false_positive_rate_5m=Decimal("8"),
        recent_false_reversal_rate_5m=Decimal("5"),
    )

    assert signal.abstain is False
    assert signal.bias == "bullish"
    assert signal.confidence >= 60
    assert signal.regime in {"trending", "breakout_building"}
    assert signal.suggested_action in {"enter", "hold"}


def test_ai_signal_identifies_breakout_building_and_waits_for_confirmation() -> None:
    service = AISignalService()
    closes = [Decimal("100") + (Decimal(index) * Decimal("0.08")) for index in range(65)]
    closes[-5:] = [Decimal("105"), Decimal("105.4"), Decimal("105.8"), Decimal("106.0"), Decimal("106.2")]
    candles = [build_candle(index, str(close)) for index, close in enumerate(closes)]

    signal = service.build_signal(
        symbol="BTCUSDT",
        candles=candles,
        feature_snapshot=build_feature_snapshot(
            ema_fast=Decimal("106.1"),
            ema_slow=Decimal("104.8"),
            rsi=Decimal("59"),
            atr=Decimal("1.6"),
            mid_price=candles[-1].close,
        ),
        top_of_book=build_top_of_book(str(candles[-1].close), spread="0.14"),
        technical_analysis=build_technical_analysis(
            trend_direction="bullish",
            trend_strength="moderate",
            trend_strength_score=58,
            breakout_readiness="high",
            breakout_bias="upside",
            reversal_risk="low",
            multi_timeframe_agreement="mixed",
        ),
        market_sentiment=build_market_sentiment(market_state="risk_on", sentiment_score=66),
    )

    assert signal.regime == "breakout_building"
    assert signal.confirmation_needed is True
    assert signal.suggested_action == "wait"
    assert signal.preferred_horizon in {"5m", "15m", "1h"}


def test_ai_signal_identifies_reversal_risk() -> None:
    service = AISignalService()
    closes = [Decimal("100") + (Decimal(index) * Decimal("0.35")) for index in range(60)] + [
        Decimal("121"),
        Decimal("119.5"),
        Decimal("118"),
        Decimal("116.5"),
        Decimal("115"),
        Decimal("113.5"),
        Decimal("112"),
        Decimal("111"),
        Decimal("110"),
        Decimal("109"),
    ]
    candles = [build_candle(index, str(close)) for index, close in enumerate(closes)]

    signal = service.build_signal(
        symbol="BTCUSDT",
        candles=candles,
        feature_snapshot=build_feature_snapshot(
            ema_fast=Decimal("110"),
            ema_slow=Decimal("111"),
            rsi=Decimal("44"),
            atr=Decimal("2.4"),
            mid_price=candles[-1].close,
            regime="bearish",
        ),
        top_of_book=build_top_of_book(str(candles[-1].close), spread="0.12"),
        technical_analysis=build_technical_analysis(
            trend_direction="bearish",
            trend_strength="moderate",
            trend_strength_score=54,
            breakout_readiness="low",
            breakout_bias="none",
            reversal_risk="high",
            multi_timeframe_agreement="mixed",
            momentum_state="bearish",
        ),
        market_sentiment=build_market_sentiment(market_state="mixed", sentiment_score=46),
    )

    assert signal.regime == "reversal_risk"
    assert signal.exit_signal is True
    assert signal.suggested_action in {"exit", "wait", "abstain"}


def test_ai_signal_differentiates_horizon_outputs() -> None:
    service = AISignalService()
    closes = [Decimal("100") + (Decimal(index) * Decimal("0.25")) for index in range(60)] + [
        Decimal("115"),
        Decimal("114.6"),
        Decimal("115.4"),
        Decimal("114.9"),
        Decimal("115.8"),
        Decimal("115.5"),
        Decimal("116.2"),
        Decimal("116.0"),
        Decimal("116.4"),
        Decimal("116.1"),
    ]
    candles = [build_candle(index, str(close)) for index, close in enumerate(closes)]

    signal = service.build_signal(
        symbol="BTCUSDT",
        candles=candles,
        feature_snapshot=build_feature_snapshot(
            ema_fast=Decimal("116.4"),
            ema_slow=Decimal("113"),
            rsi=Decimal("58"),
            atr=Decimal("1.5"),
            mid_price=candles[-1].close,
        ),
        top_of_book=build_top_of_book(str(candles[-1].close), spread="0.18"),
        technical_analysis=build_technical_analysis(
            trend_direction="bullish",
            trend_strength="moderate",
            trend_strength_score=62,
            breakout_readiness="medium",
            breakout_bias="upside",
            reversal_risk="low",
            multi_timeframe_agreement="bullish_alignment",
        ),
        market_sentiment=build_market_sentiment(market_state="risk_on", sentiment_score=70),
    )

    horizons = {item.horizon: item for item in signal.horizon_signals}
    assert set(horizons) == {"5m", "15m", "1h"}
    assert len({item.confidence for item in horizons.values()}) > 1
    assert horizons["5m"].confidence != horizons["1h"].confidence


def test_ai_signal_confidence_stays_within_bounds() -> None:
    service = AISignalService()
    candles = [build_candle(index, str(Decimal("100") + (Decimal(index) * Decimal("0.8"))), volume="20") for index in range(70)]

    signal = service.build_signal(
        symbol="BTCUSDT",
        candles=candles,
        feature_snapshot=build_feature_snapshot(
            ema_fast=Decimal("156"),
            ema_slow=Decimal("118"),
            rsi=Decimal("78"),
            atr=Decimal("8"),
            mid_price=candles[-1].close,
            bid_ask_spread=Decimal("0.80"),
            order_book_imbalance=Decimal("0.80"),
        ),
        top_of_book=build_top_of_book(str(candles[-1].close), spread="0.80"),
        technical_analysis=build_technical_analysis(
            trend_direction="bullish",
            trend_strength="strong",
            trend_strength_score=84,
            volatility_regime="high",
            breakout_readiness="medium",
            reversal_risk="medium",
        ),
        market_sentiment=build_market_sentiment(market_state="risk_on", sentiment_score=73),
    )

    assert 0 <= signal.confidence <= 100
    assert isinstance(signal.explanation, str)
