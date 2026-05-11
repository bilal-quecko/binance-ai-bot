from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.analysis.regime import RegimeAnalysisSnapshot
from app.analysis.technical import TechnicalAnalysisSnapshot
from app.market_data.candles import Candle
from app.monitoring.futures_opportunity_scanner import (
    FuturesOpportunityScanner,
    FuturesSignalContext,
)
from app.monitoring.crowd_positioning import CrowdPositioningSnapshot
from app.monitoring.liquidation_intelligence import LiquidationIntelligenceSnapshot
from app.monitoring.liquidity_bias import LiquidityBiasSnapshot
from app.monitoring.similar_setups import SimilarSetupReport
from app.monitoring.trade_eligibility import TradeEligibilityResult


def _candles(symbol: str, *, step: Decimal, count: int = 48) -> list[Candle]:
    base_time = datetime(2024, 3, 9, 10, 0, tzinfo=UTC)
    price = Decimal("100")
    candles = []
    for index in range(count):
        open_price = price + (Decimal(index) * step)
        close_price = open_price + (step / Decimal("2"))
        high = max(open_price, close_price) + Decimal("0.25")
        low = min(open_price, close_price) - Decimal("0.25")
        candles.append(
            Candle(
                symbol=symbol,
                timeframe="1m",
                open=open_price,
                high=high,
                low=low,
                close=close_price,
                volume=Decimal("100"),
                quote_volume=Decimal("1000000"),
                open_time=base_time + timedelta(minutes=index),
                close_time=base_time + timedelta(minutes=index, seconds=59),
                event_time=base_time + timedelta(minutes=index, seconds=59),
                trade_count=100,
                is_closed=True,
            )
        )
    return candles


def _technical(symbol: str, *, direction: str, momentum: str, agreement: str, volatility: str = "normal") -> TechnicalAnalysisSnapshot:
    return TechnicalAnalysisSnapshot(
        symbol=symbol,
        timestamp=datetime(2024, 3, 9, 11, 0, tzinfo=UTC),
        data_state="ready",
        status_message="ready",
        trend_direction=direction,  # type: ignore[arg-type]
        trend_strength="strong",
        trend_strength_score=76,
        support_levels=[Decimal("98")],
        resistance_levels=[Decimal("104")],
        momentum_state=momentum,  # type: ignore[arg-type]
        volatility_regime=volatility,  # type: ignore[arg-type]
        breakout_readiness="high",
        breakout_bias="upside" if direction == "bullish" else "downside",
        reversal_risk="high" if direction == "bearish" else "low",
        multi_timeframe_agreement=agreement,  # type: ignore[arg-type]
        timeframe_summaries=[],
        explanation="test technical",
    )


def _regime(symbol: str, label: str) -> RegimeAnalysisSnapshot:
    return RegimeAnalysisSnapshot(
        symbol=symbol,
        generated_at=datetime(2024, 3, 9, 11, 0, tzinfo=UTC),
        horizon="7d",
        data_state="ready",
        status_message="ready",
        regime_label=label,  # type: ignore[arg-type]
        confidence=80,
        supporting_evidence=("test evidence",),
        risk_warnings=(),
        preferred_trading_behavior="paper only",
        avoid_conditions=(),
    )


def _similar(label: str = "strong") -> SimilarSetupReport:
    return SimilarSetupReport(
        status="ready",
        reliability_label=label,  # type: ignore[arg-type]
        matching_sample_size=12,
        best_horizon="15m",
        horizons=[],
        explanation=f"Similar setups are {label}.",
        matched_attributes=["symbol", "risk_grade"],
    )


def _eligibility(status: str = "eligible", strength: str = "strong") -> TradeEligibilityResult:
    return TradeEligibilityResult(
        status=status,  # type: ignore[arg-type]
        evidence_strength=strength,  # type: ignore[arg-type]
        reason="eligible",
        preferred_horizon="15m",
    )


def test_bullish_setup_returns_long() -> None:
    scanner = FuturesOpportunityScanner()

    signal = scanner.analyze_symbol(
        FuturesSignalContext(
            symbol="BTCUSDT",
            candles=_candles("BTCUSDT", step=Decimal("0.8")),
            technical_analysis=_technical("BTCUSDT", direction="bullish", momentum="bullish", agreement="bullish_alignment"),
            regime_analysis=_regime("BTCUSDT", "trending_up"),
            similar_setup=_similar("strong"),
            trade_eligibility=_eligibility("eligible", "strong"),
        )
    )

    assert signal.direction == "long"
    assert signal.confidence >= 72
    assert signal.leverage_suggestion == "1x paper-only"
    assert "Paper futures only" in signal.liquidation_safety_note
    assert signal.opportunity_score >= 70
    assert signal.evidence_strength == "strong"


def test_bullish_setup_returns_long_without_internal_validation() -> None:
    scanner = FuturesOpportunityScanner()

    signal = scanner.analyze_symbol(
        FuturesSignalContext(
            symbol="BTCUSDT",
            candles=_candles("BTCUSDT", step=Decimal("0.8")),
            higher_timeframe_candles=_candles("BTCUSDT", step=Decimal("2.0"), count=48),
            technical_analysis=_technical("BTCUSDT", direction="bullish", momentum="bullish", agreement="bullish_alignment"),
            regime_analysis=_regime("BTCUSDT", "trending_up"),
        )
    )

    assert signal.direction == "long"
    assert signal.evidence_strength == "unvalidated"
    assert signal.opportunity_score >= 70
    assert signal.nearest_liquidity_target_direction in {"up", "down", "none"}
    assert signal.sweep_risk in {"none", "upside_sweep", "downside_sweep", "both_sides"}
    assert signal.tp_sl_alignment in {
        "aligned",
        "stop_too_close_to_liquidity",
        "target_before_liquidity",
        "target_after_liquidity",
        "needs_review",
    }


def test_bearish_setup_returns_short() -> None:
    scanner = FuturesOpportunityScanner()

    signal = scanner.analyze_symbol(
        FuturesSignalContext(
            symbol="ETHUSDT",
            candles=_candles("ETHUSDT", step=Decimal("-0.8")),
            technical_analysis=_technical("ETHUSDT", direction="bearish", momentum="bearish", agreement="bearish_alignment"),
            regime_analysis=_regime("ETHUSDT", "trending_down"),
            similar_setup=_similar("strong"),
            trade_eligibility=_eligibility("eligible", "strong"),
        )
    )

    assert signal.direction == "short"
    assert signal.confidence >= 72


def test_bearish_setup_returns_short_without_internal_validation() -> None:
    scanner = FuturesOpportunityScanner()

    signal = scanner.analyze_symbol(
        FuturesSignalContext(
            symbol="ETHUSDT",
            candles=_candles("ETHUSDT", step=Decimal("-0.8")),
            higher_timeframe_candles=_candles("ETHUSDT", step=Decimal("-2.0"), count=48),
            technical_analysis=_technical("ETHUSDT", direction="bearish", momentum="bearish", agreement="bearish_alignment"),
            regime_analysis=_regime("ETHUSDT", "trending_down"),
        )
    )

    assert signal.direction == "short"
    assert signal.evidence_strength == "unvalidated"
    assert signal.validation_score == 20
    assert signal.liquidity_zone_explanation.startswith("Estimated liquidity zones only:")


def test_liquidity_zone_context_does_not_change_opportunity_score_ranking_input() -> None:
    scanner = FuturesOpportunityScanner()
    base_context = FuturesSignalContext(
        symbol="BTCUSDT",
        candles=_candles("BTCUSDT", step=Decimal("0.8")),
        higher_timeframe_candles=_candles("BTCUSDT", step=Decimal("2.0"), count=48),
        technical_analysis=_technical("BTCUSDT", direction="bullish", momentum="bullish", agreement="bullish_alignment"),
        regime_analysis=_regime("BTCUSDT", "trending_up"),
    )
    biased_context = FuturesSignalContext(
        symbol="BTCUSDT",
        candles=base_context.candles,
        higher_timeframe_candles=base_context.higher_timeframe_candles,
        technical_analysis=base_context.technical_analysis,
        regime_analysis=base_context.regime_analysis,
        liquidity_bias=LiquidityBiasSnapshot(
            liquidity_bias="bearish",
            liquidity_pressure="high",
            likely_liquidation_direction="down",
            trap_risk="long_trap",
            explanation="Estimated crowded longs.",
        ),
    )

    base_signal = scanner.analyze_symbol(base_context)
    biased_signal = scanner.analyze_symbol(biased_context)

    assert biased_signal.opportunity_score == base_signal.opportunity_score


def test_crowd_positioning_payload_does_not_change_opportunity_score() -> None:
    scanner = FuturesOpportunityScanner()
    base_context = FuturesSignalContext(
        symbol="BTCUSDT",
        candles=_candles("BTCUSDT", step=Decimal("0.8")),
        higher_timeframe_candles=_candles("BTCUSDT", step=Decimal("2.0"), count=48),
        technical_analysis=_technical("BTCUSDT", direction="bullish", momentum="bullish", agreement="bullish_alignment"),
        regime_analysis=_regime("BTCUSDT", "trending_up"),
    )
    crowd_context = FuturesSignalContext(
        symbol="BTCUSDT",
        candles=base_context.candles,
        higher_timeframe_candles=base_context.higher_timeframe_candles,
        technical_analysis=base_context.technical_analysis,
        regime_analysis=base_context.regime_analysis,
        crowd_positioning=CrowdPositioningSnapshot(
            crowd_side="long_crowded",
            crowd_strength="high",
            positioning_confidence="high",
            squeeze_risk="long_squeeze",
            explanation="Crowded longs.",
        ),
        funding_rate=Decimal("0.0006"),
        open_interest=Decimal("10000"),
        oi_trend="rising",
    )

    base_signal = scanner.analyze_symbol(base_context)
    crowd_signal = scanner.analyze_symbol(crowd_context)

    assert crowd_signal.opportunity_score == base_signal.opportunity_score
    assert crowd_signal.crowd_side == "long_crowded"
    assert crowd_signal.squeeze_risk == "long_squeeze"
    assert crowd_signal.funding_rate == Decimal("0.0006")


def test_mixed_setup_returns_wait() -> None:
    scanner = FuturesOpportunityScanner()

    signal = scanner.analyze_symbol(
        FuturesSignalContext(
            symbol="SOLUSDT",
            candles=_candles("SOLUSDT", step=Decimal("0.05")),
            technical_analysis=_technical("SOLUSDT", direction="sideways", momentum="neutral", agreement="mixed"),
            regime_analysis=_regime("SOLUSDT", "sideways"),
            similar_setup=_similar("mixed"),
            trade_eligibility=_eligibility("watch_only", "mixed"),
        )
    )

    assert signal.direction == "wait"
    assert signal.evidence_strength == "mixed"


def test_choppy_or_low_liquidity_setup_returns_avoid() -> None:
    scanner = FuturesOpportunityScanner()

    choppy = scanner.analyze_symbol(
        FuturesSignalContext(
            symbol="BNBUSDT",
            candles=_candles("BNBUSDT", step=Decimal("0.8")),
            technical_analysis=_technical("BNBUSDT", direction="bullish", momentum="bullish", agreement="bullish_alignment"),
            regime_analysis=_regime("BNBUSDT", "choppy"),
            similar_setup=_similar("strong"),
            trade_eligibility=_eligibility("eligible", "strong"),
        )
    )
    low_liquidity = scanner.analyze_symbol(
        FuturesSignalContext(
            symbol="XRPUSDT",
            candles=_candles("XRPUSDT", step=Decimal("-0.8")),
            technical_analysis=_technical("XRPUSDT", direction="bearish", momentum="bearish", agreement="bearish_alignment"),
            regime_analysis=_regime("XRPUSDT", "low_liquidity"),
            similar_setup=_similar("strong"),
            trade_eligibility=_eligibility("eligible", "strong"),
        )
    )

    assert choppy.direction == "avoid"
    assert low_liquidity.direction == "avoid"


def test_choppy_market_structure_returns_wait_or_avoid() -> None:
    scanner = FuturesOpportunityScanner()
    candles: list[Candle] = []
    base_time = datetime(2024, 3, 9, 10, 0, tzinfo=UTC)
    price = Decimal("100")
    for index in range(48):
        price += Decimal("1.2") if index % 2 == 0 else Decimal("-1.2")
        candles.append(
            Candle(
                symbol="CHOPUSDT",
                timeframe="15m",
                open=price,
                high=price + Decimal("0.9"),
                low=price - Decimal("0.9"),
                close=price + (Decimal("0.2") if index % 2 == 0 else Decimal("-0.2")),
                volume=Decimal("100"),
                quote_volume=Decimal("1000000"),
                open_time=base_time + timedelta(minutes=15 * index),
                close_time=base_time + timedelta(minutes=15 * index + 14),
                event_time=base_time + timedelta(minutes=15 * index + 14),
                trade_count=100,
                is_closed=True,
            )
        )

    signal = scanner.analyze_symbol(
        FuturesSignalContext(
            symbol="CHOPUSDT",
            candles=candles,
            technical_analysis=None,
            regime_analysis=None,
        )
    )

    assert signal.direction in {"wait", "avoid"}
    assert signal.trend in {"choppy", "mixed"}


def test_insufficient_data_behavior() -> None:
    scanner = FuturesOpportunityScanner()

    signal = scanner.analyze_symbol(
        FuturesSignalContext(
            symbol="ADAUSDT",
            candles=_candles("ADAUSDT", step=Decimal("0.1"), count=5),
            technical_analysis=None,
            regime_analysis=None,
        )
    )

    assert signal.direction == "avoid"
    assert signal.evidence_strength == "insufficient"
    assert signal.risk_grade == "high"


def test_scanner_partial_failure_report() -> None:
    scanner = FuturesOpportunityScanner()
    signal = scanner.analyze_symbol(
        FuturesSignalContext(
            symbol="BTCUSDT",
            candles=_candles("BTCUSDT", step=Decimal("0.8")),
            technical_analysis=_technical("BTCUSDT", direction="bullish", momentum="bullish", agreement="bullish_alignment"),
            regime_analysis=_regime("BTCUSDT", "trending_up"),
            similar_setup=_similar("strong"),
            trade_eligibility=_eligibility("eligible", "strong"),
        )
    )

    report = scanner.build_report(signals=[signal], failed_symbols=["ETHUSDT"])

    assert report.scan_state == "partial"
    assert report.failed_symbols == ["ETHUSDT"]
    assert report.long_candidates[0].symbol == "BTCUSDT"


def test_report_ranking_uses_opportunity_score() -> None:
    scanner = FuturesOpportunityScanner()
    lower_confidence = scanner.analyze_symbol(
        FuturesSignalContext(
            symbol="HIGHUSDT",
            candles=_candles("HIGHUSDT", step=Decimal("1.2")),
            higher_timeframe_candles=_candles("HIGHUSDT", step=Decimal("2.0")),
            technical_analysis=_technical("HIGHUSDT", direction="bullish", momentum="bullish", agreement="bullish_alignment"),
            regime_analysis=_regime("HIGHUSDT", "trending_up"),
        )
    )
    higher_confidence = scanner.analyze_symbol(
        FuturesSignalContext(
            symbol="LOWUSDT",
            candles=_candles("LOWUSDT", step=Decimal("0.8")),
            technical_analysis=_technical("LOWUSDT", direction="bullish", momentum="bullish", agreement="bullish_alignment"),
            regime_analysis=_regime("LOWUSDT", "trending_up"),
            similar_setup=_similar("strong"),
            trade_eligibility=_eligibility("eligible", "strong"),
        )
    )

    report = scanner.build_report(signals=[higher_confidence, lower_confidence])

    assert report.long_candidates[0].opportunity_score >= report.long_candidates[1].opportunity_score
    assert {"opportunity_score", "evidence_strength"} <= set(report.long_candidates[0].__dataclass_fields__)


def test_liquidity_bias_fields_preserve_opportunity_score() -> None:
    scanner = FuturesOpportunityScanner()
    context = FuturesSignalContext(
        symbol="BTCUSDT",
        candles=_candles("BTCUSDT", step=Decimal("0.8")),
        technical_analysis=_technical("BTCUSDT", direction="bullish", momentum="bullish", agreement="bullish_alignment"),
        regime_analysis=_regime("BTCUSDT", "trending_up"),
        similar_setup=_similar("strong"),
        trade_eligibility=_eligibility("eligible", "strong"),
    )
    baseline = scanner.analyze_symbol(context)
    with_liquidity = scanner.analyze_symbol(
        FuturesSignalContext(
            symbol="BTCUSDT",
            candles=context.candles,
            technical_analysis=context.technical_analysis,
            regime_analysis=context.regime_analysis,
            similar_setup=context.similar_setup,
            trade_eligibility=context.trade_eligibility,
            liquidity_bias=LiquidityBiasSnapshot(
                liquidity_bias="bearish",
                liquidity_pressure="high",
                likely_liquidation_direction="down",
                trap_risk="long_trap",
                explanation="Liquidity estimate: crowded longs.",
            ),
        )
    )

    assert with_liquidity.opportunity_score == baseline.opportunity_score
    assert with_liquidity.confidence < baseline.confidence
    assert with_liquidity.trap_risk == "long_trap"
    assert with_liquidity.likely_liquidation_direction == "down"


def test_liquidation_fields_preserve_opportunity_score_and_ranking_inputs() -> None:
    scanner = FuturesOpportunityScanner()
    context = FuturesSignalContext(
        symbol="BTCUSDT",
        candles=_candles("BTCUSDT", step=Decimal("0.8")),
        technical_analysis=_technical("BTCUSDT", direction="bullish", momentum="bullish", agreement="bullish_alignment"),
        regime_analysis=_regime("BTCUSDT", "trending_up"),
        similar_setup=_similar("strong"),
        trade_eligibility=_eligibility("eligible", "strong"),
    )
    baseline = scanner.analyze_symbol(context)
    with_liquidation = scanner.analyze_symbol(
        FuturesSignalContext(
            symbol="BTCUSDT",
            candles=context.candles,
            technical_analysis=context.technical_analysis,
            regime_analysis=context.regime_analysis,
            similar_setup=context.similar_setup,
            trade_eligibility=context.trade_eligibility,
            liquidation_intelligence=LiquidationIntelligenceSnapshot(
                liquidation_signal="cascade_down",
                liquidation_intensity="high",
                dominant_side="longs_liquidated",
                interpretation_confidence="high",
                explanation="Downside cascade.",
                liquidation_volume_long=Decimal("125000"),
                liquidation_volume_short=Decimal("0"),
                imbalance_ratio=Decimal("-100"),
                event_frequency=Decimal("2"),
            ),
        )
    )

    assert with_liquidation.opportunity_score == baseline.opportunity_score
    assert with_liquidation.direction_score == baseline.direction_score
    assert with_liquidation.liquidation_signal == "cascade_down"
    assert with_liquidation.dominant_side == "longs_liquidated"
