from datetime import UTC, datetime
from decimal import Decimal

from app.ai.models import AIFeatureVector, AISignalSnapshot
from app.analysis.pattern_summary import PatternAnalysisSnapshot
from app.analysis.technical import TechnicalAnalysisSnapshot, TimeframeTechnicalSummary
from app.fusion.engine import UnifiedSignalFusionEngine
from app.fusion.models import FusionInputs
from app.runner.models import TradeReadiness
from app.sentiment.models import SentimentComponent, SymbolSentimentSnapshot


def _technical(*, direction: str, volatility: str = "normal", reversal_risk: str = "low") -> TechnicalAnalysisSnapshot:
    return TechnicalAnalysisSnapshot(
        symbol="BTCUSDT",
        timestamp=datetime(2024, 3, 9, 16, 2, tzinfo=UTC),
        data_state="ready",
        status_message="ready",
        trend_direction=direction,  # type: ignore[arg-type]
        trend_strength="strong",
        trend_strength_score=78,
        support_levels=[Decimal("99")],
        resistance_levels=[Decimal("103")],
        momentum_state="bullish" if direction == "bullish" else "bearish",
        volatility_regime=volatility,  # type: ignore[arg-type]
        breakout_readiness="high" if direction != "sideways" else "low",
        breakout_bias="upside" if direction == "bullish" else ("downside" if direction == "bearish" else "none"),
        reversal_risk=reversal_risk,  # type: ignore[arg-type]
        multi_timeframe_agreement="bullish_alignment" if direction == "bullish" else ("bearish_alignment" if direction == "bearish" else "mixed"),
        timeframe_summaries=[TimeframeTechnicalSummary(timeframe="1m", trend_direction=direction, trend_strength="strong")],  # type: ignore[arg-type]
        explanation="technical",
    )


def _pattern(*, direction: str, character: str = "persistent", tendency: str = "breakout_prone") -> PatternAnalysisSnapshot:
    return PatternAnalysisSnapshot(
        symbol="BTCUSDT",
        horizon="7d",
        generated_at=datetime(2024, 3, 9, 16, 2, tzinfo=UTC),
        data_state="ready",
        status_message="ready",
        coverage_start=datetime(2024, 3, 2, 16, 2, tzinfo=UTC),
        coverage_end=datetime(2024, 3, 9, 16, 2, tzinfo=UTC),
        coverage_ratio_pct=Decimal("100"),
        partial_coverage=False,
        overall_direction=direction,  # type: ignore[arg-type]
        net_return_pct=Decimal("6.5") if direction == "bullish" else (Decimal("-5.5") if direction == "bearish" else Decimal("0.4")),
        up_moves=8,
        down_moves=3,
        flat_moves=1,
        up_move_ratio_pct=Decimal("66"),
        down_move_ratio_pct=Decimal("25"),
        realized_volatility_pct=Decimal("1.2"),
        max_drawdown_pct=Decimal("2.5"),
        trend_character=character,  # type: ignore[arg-type]
        breakout_tendency=tendency,  # type: ignore[arg-type]
        reversal_tendency="low",
        explanation="pattern",
    )


def _ai(*, bias: str, confidence: int, regime: str = "trending", action: str = "enter", abstain: bool = False) -> AISignalSnapshot:
    return AISignalSnapshot(
        symbol="BTCUSDT",
        bias=bias,  # type: ignore[arg-type]
        confidence=confidence,
        entry_signal=bias == "bullish",
        exit_signal=bias == "bearish",
        suggested_action=action,  # type: ignore[arg-type]
        explanation="ai",
        feature_vector=AIFeatureVector(
            symbol="BTCUSDT",
            timestamp=datetime(2024, 3, 9, 16, 2, tzinfo=UTC),
            candle_count=30,
            close_price=Decimal("101"),
            ema_fast=Decimal("102"),
            ema_slow=Decimal("100"),
            rsi=Decimal("61"),
            atr=Decimal("1"),
            volatility_pct=Decimal("0.012"),
            momentum=Decimal("0.021"),
        ),
        regime=regime,  # type: ignore[arg-type]
        noise_level="low",
        abstain=abstain,
        preferred_horizon="15m",
    )


def _sentiment(*, score: int, label: str, risk_flag: str = "normal") -> SymbolSentimentSnapshot:
    return SymbolSentimentSnapshot(
        symbol="BTCUSDT",
        generated_at=datetime(2024, 3, 9, 16, 2, tzinfo=UTC),
        data_state="ready",
        status_message="ready",
        score=score,
        label=label,  # type: ignore[arg-type]
        confidence=72,
        momentum_state="rising" if score > 0 else ("fading" if score < 0 else "stable"),
        risk_flag=risk_flag,  # type: ignore[arg-type]
        explanation="sentiment",
        source_mode="proxy",
        components=(
            SentimentComponent(
                name="price_acceleration",
                score=Decimal(str(score / 100)),
                weight=Decimal("0.30"),
                explanation="component",
            ),
        ),
    )


def _readiness(*, risk_ready: bool = True, risk_blocked: bool = False, entry: bool = True, exit_signal: bool = False, expected_edge: str = "0.030", costs: str = "0.010") -> TradeReadiness:
    return TradeReadiness(
        selected_symbol="BTCUSDT",
        runtime_active=True,
        mode="auto_paper",
        enough_candle_history=True,
        deterministic_entry_signal=entry,
        deterministic_exit_signal=exit_signal,
        risk_ready=risk_ready,
        risk_blocked=risk_blocked,
        broker_ready=True,
        next_action="enter" if entry else "wait_for_history",
        reason_if_not_trading=None,
        risk_reason_codes=("APPROVED",) if risk_ready else ("BLOCKED",),
        expected_edge_pct=Decimal(expected_edge),
        estimated_round_trip_cost_pct=Decimal(costs),
    )


def test_fusion_engine_returns_long_for_bullish_alignment() -> None:
    snapshot = UnifiedSignalFusionEngine().build_signal(
        FusionInputs(
            symbol="BTCUSDT",
            technical_analysis=_technical(direction="bullish"),
            pattern_analysis=_pattern(direction="bullish"),
            ai_signal=_ai(bias="bullish", confidence=76),
            symbol_sentiment=_sentiment(score=58, label="bullish"),
            trade_readiness=_readiness(),
            current_position_quantity=Decimal("0"),
        )
    )

    assert snapshot.final_signal == "long"
    assert snapshot.confidence >= 55
    assert snapshot.alignment_score >= 40
    assert snapshot.risk_grade in {"low", "medium"}


def test_fusion_engine_returns_short_for_bearish_alignment() -> None:
    snapshot = UnifiedSignalFusionEngine().build_signal(
        FusionInputs(
            symbol="BTCUSDT",
            technical_analysis=_technical(direction="bearish"),
            pattern_analysis=_pattern(direction="bearish"),
            ai_signal=_ai(bias="bearish", confidence=74, action="exit"),
            symbol_sentiment=_sentiment(score=-61, label="bearish"),
            trade_readiness=_readiness(entry=False, exit_signal=True),
            current_position_quantity=Decimal("0"),
        )
    )

    assert snapshot.final_signal == "short"
    assert snapshot.confidence >= 50


def test_fusion_engine_returns_wait_for_mixed_alignment() -> None:
    snapshot = UnifiedSignalFusionEngine().build_signal(
        FusionInputs(
            symbol="BTCUSDT",
            technical_analysis=_technical(direction="bullish"),
            pattern_analysis=_pattern(direction="sideways", character="balanced", tendency="mixed"),
            ai_signal=_ai(bias="sideways", confidence=41, action="wait", abstain=True, regime="choppy"),
            symbol_sentiment=_sentiment(score=-5, label="mixed"),
            trade_readiness=_readiness(risk_ready=False, risk_blocked=True, entry=False, expected_edge="0.005", costs="0.010"),
            current_position_quantity=Decimal("0"),
        )
    )

    assert snapshot.final_signal == "wait"
    assert snapshot.risk_grade == "high"
    assert any("blocking" in warning.lower() for warning in snapshot.warnings)


def test_fusion_engine_returns_reduce_risk_for_unstable_volatility() -> None:
    snapshot = UnifiedSignalFusionEngine().build_signal(
        FusionInputs(
            symbol="BTCUSDT",
            technical_analysis=_technical(direction="bullish", volatility="high"),
            pattern_analysis=_pattern(direction="bullish"),
            ai_signal=_ai(bias="bullish", confidence=68, regime="high_volatility_unstable"),
            symbol_sentiment=_sentiment(score=42, label="bullish", risk_flag="hype"),
            trade_readiness=_readiness(),
            current_position_quantity=Decimal("1"),
        )
    )

    assert snapshot.final_signal == "reduce_risk"
    assert snapshot.risk_grade == "high"
