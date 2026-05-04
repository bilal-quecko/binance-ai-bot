"""Paper-only futures long/short opportunity scanner."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from app.analysis.regime import RegimeAnalysisSnapshot
from app.analysis.technical import TechnicalAnalysisSnapshot
from app.market_data.candles import Candle
from app.monitoring.similar_setups import SimilarSetupReport
from app.monitoring.trade_eligibility import TradeEligibilityResult


FuturesDirection = Literal["long", "short", "wait", "avoid"]
FuturesEvidenceStrength = Literal["insufficient", "unvalidated", "weak", "mixed", "promising", "strong"]
FuturesRiskGrade = Literal["low", "medium", "high"]
FuturesScanState = Literal["ready", "partial", "insufficient_data", "degraded"]

MIN_CANDLES_FOR_FUTURES_SIGNAL = 24
MAX_PAPER_LEVERAGE = 3


@dataclass(slots=True)
class FuturesPaperSignal:
    """Paper-only futures directional signal for one symbol."""

    symbol: str
    direction: FuturesDirection
    opportunity_score: int
    direction_score: int
    momentum_score: int
    trend_score: int
    volatility_quality_score: int
    liquidity_score: int
    risk_score: int
    validation_score: int | None
    confidence: int
    evidence_strength: FuturesEvidenceStrength
    trend: str
    momentum: str
    best_horizon: str
    risk_grade: FuturesRiskGrade
    regime: str | None
    current_price: Decimal | None
    reason: str
    invalidation_hint: str | None
    suggested_entry_zone: str | None
    suggested_stop_loss: Decimal | None
    suggested_take_profit: Decimal | None
    estimated_fee_impact: Decimal | None
    leverage_suggestion: str
    liquidation_safety_note: str
    similar_setup_summary: str
    eligibility_status: str
    warnings: tuple[str, ...]
    timestamp: datetime


@dataclass(slots=True)
class FuturesOpportunityScanReport:
    """Multi-symbol paper futures scanner output."""

    generated_at: datetime
    scan_state: FuturesScanState
    long_candidates: list[FuturesPaperSignal] = field(default_factory=list)
    short_candidates: list[FuturesPaperSignal] = field(default_factory=list)
    neutral_candidates: list[FuturesPaperSignal] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    scanned_count: int = 0
    failed_symbols: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FuturesSignalContext:
    """Inputs used to score one paper futures opportunity."""

    symbol: str
    candles: Sequence[Candle]
    technical_analysis: TechnicalAnalysisSnapshot | None
    regime_analysis: RegimeAnalysisSnapshot | None
    higher_timeframe_candles: Sequence[Candle] = ()
    similar_setup: SimilarSetupReport | None = None
    trade_eligibility: TradeEligibilityResult | None = None
    preferred_horizon: str | None = None
    expected_edge_pct: Decimal | None = None
    invalidation_hint: str | None = None
    blocker_reasons: Sequence[str] = ()
    warnings: Sequence[str] = ()
    spread_ratio_pct: Decimal | None = None


class FuturesOpportunityScanner:
    """Score paper futures opportunities without creating any execution path."""

    def analyze_symbol(self, context: FuturesSignalContext) -> FuturesPaperSignal:
        """Return a deterministic paper-only long/short/wait/avoid signal."""

        timestamp = datetime.now(tz=UTC)
        best_horizon = context.preferred_horizon or "15m"
        current_price = context.candles[-1].close if context.candles else None
        leverage = "1x paper-only"
        liquidation_note = (
            f"Paper futures only. Suggested leverage is capped at {MAX_PAPER_LEVERAGE}x and this signal "
            "does not place real Binance futures orders."
        )

        if len(context.candles) < MIN_CANDLES_FOR_FUTURES_SIGNAL:
            return FuturesPaperSignal(
                symbol=context.symbol,
                direction="avoid",
                opportunity_score=0,
                direction_score=0,
                momentum_score=0,
                trend_score=0,
                volatility_quality_score=0,
                liquidity_score=0,
                risk_score=0,
                validation_score=None,
                confidence=0,
                evidence_strength="insufficient",
                trend="insufficient_data",
                momentum="insufficient_data",
                best_horizon=best_horizon,
                risk_grade="high",
                regime=None,
                current_price=current_price,
                reason="Insufficient candle history for a paper futures long/short read.",
                invalidation_hint=None,
                suggested_entry_zone=None,
                suggested_stop_loss=None,
                suggested_take_profit=None,
                estimated_fee_impact=context.spread_ratio_pct,
                leverage_suggestion=leverage,
                liquidation_safety_note=liquidation_note,
                similar_setup_summary=_similar_summary(context.similar_setup),
                eligibility_status=_eligibility_status(context.trade_eligibility),
                warnings=("Backfill more history before treating this symbol as a futures candidate.",),
                timestamp=timestamp,
            )

        technical = context.technical_analysis
        regime = context.regime_analysis
        market_scores = _market_scores(context.candles, context.higher_timeframe_candles)
        evidence_strength = _evidence_strength(context.similar_setup, context.trade_eligibility)
        validation_score = _validation_score(evidence_strength)
        regime_label = regime.regime_label if regime is not None else None
        risk_grade = _risk_grade(
            technical=technical,
            regime_label=regime_label,
            spread_ratio_pct=context.spread_ratio_pct,
            blocker_reasons=context.blocker_reasons,
            volatility_quality_score=market_scores.volatility_quality_score,
            liquidity_score=market_scores.liquidity_score,
            risk_score=market_scores.risk_score,
        )
        warnings = list(dict.fromkeys((*context.warnings, *_regime_warnings(regime), *_safety_warnings(risk_grade, regime_label))))
        eligibility_status = _eligibility_status(context.trade_eligibility)
        fee_impact = _estimated_fee_impact(context.spread_ratio_pct)
        long_score = _long_score(context, market_scores=market_scores)
        short_score = _short_score(context, market_scores=market_scores)
        current_direction_score = max(long_score, short_score)
        opportunity_score = _opportunity_score(
            direction_score=current_direction_score,
            trend_score=market_scores.trend_score,
            momentum_score=market_scores.momentum_score,
            volatility_quality_score=market_scores.volatility_quality_score,
            liquidity_score=market_scores.liquidity_score,
            risk_score=market_scores.risk_score,
            validation_score=validation_score,
        )
        confidence = _confidence_from_scores(
            opportunity_score=opportunity_score,
            validation_score=validation_score,
            risk_score=market_scores.risk_score,
        )

        blocking_reason = _blocking_reason(
            risk_grade=risk_grade,
            regime_label=regime_label,
            blocker_reasons=context.blocker_reasons,
            eligibility_status=eligibility_status,
            fee_impact=fee_impact,
        )
        if blocking_reason is not None:
            return _build_signal(
                context=context,
                direction="avoid",
                scores=market_scores,
                opportunity_score=min(opportunity_score, 45),
                direction_score=current_direction_score,
                validation_score=validation_score,
                confidence=min(confidence, 45),
                evidence_strength=evidence_strength,
                risk_grade=risk_grade,
                current_price=current_price,
                fee_impact=fee_impact,
                reason=blocking_reason,
                warnings=tuple(warnings),
                timestamp=timestamp,
            )

        if opportunity_score >= 70 and long_score >= short_score + 10:
            return _build_signal(
                context=context,
                direction="long",
                scores=market_scores,
                opportunity_score=opportunity_score,
                direction_score=long_score,
                validation_score=validation_score,
                confidence=confidence,
                evidence_strength=evidence_strength,
                risk_grade=risk_grade,
                current_price=current_price,
                fee_impact=fee_impact,
                reason=_direction_reason(
                    direction="long",
                    evidence_strength=evidence_strength,
                    trend=market_scores.trend,
                    momentum=market_scores.momentum,
                ),
                warnings=tuple(warnings),
                timestamp=timestamp,
            )

        if opportunity_score >= 70 and short_score >= long_score + 10:
            return _build_signal(
                context=context,
                direction="short",
                scores=market_scores,
                opportunity_score=opportunity_score,
                direction_score=short_score,
                validation_score=validation_score,
                confidence=confidence,
                evidence_strength=evidence_strength,
                risk_grade=risk_grade,
                current_price=current_price,
                fee_impact=fee_impact,
                reason=_direction_reason(
                    direction="short",
                    evidence_strength=evidence_strength,
                    trend=market_scores.trend,
                    momentum=market_scores.momentum,
                ),
                warnings=tuple(warnings),
                timestamp=timestamp,
            )

        wait_reason = "No high-quality LONG/SHORT candidate found for this symbol under current structure."
        if opportunity_score >= 50:
            wait_reason = "Potential setup is forming, but trend and momentum still need cleaner confirmation."
        return _build_signal(
            context=context,
            direction="wait",
            scores=market_scores,
            opportunity_score=opportunity_score,
            direction_score=current_direction_score,
            validation_score=validation_score,
            confidence=min(confidence, 68),
            evidence_strength=evidence_strength,
            risk_grade=risk_grade,
            current_price=current_price,
            fee_impact=fee_impact,
            reason=wait_reason,
            warnings=tuple(warnings),
            timestamp=timestamp,
        )

    def build_report(
        self,
        *,
        signals: Sequence[FuturesPaperSignal],
        failed_symbols: Sequence[str] = (),
        include_avoid: bool = True,
    ) -> FuturesOpportunityScanReport:
        """Group and rank already scored futures-paper signals."""

        visible_signals = list(signals)
        long_candidates = sorted(
            [signal for signal in visible_signals if signal.direction == "long"],
            key=lambda item: (-item.opportunity_score, -item.confidence, item.risk_grade, item.symbol),
        )
        short_candidates = sorted(
            [signal for signal in visible_signals if signal.direction == "short"],
            key=lambda item: (-item.opportunity_score, -item.confidence, item.risk_grade, item.symbol),
        )
        neutral_candidates = [
            signal
            for signal in visible_signals
            if signal.direction == "wait" or (include_avoid and signal.direction == "avoid")
        ]
        neutral_candidates = sorted(
            neutral_candidates,
            key=lambda item: (item.direction == "avoid", -item.opportunity_score, item.symbol),
        )

        warnings: list[str] = []
        if not visible_signals:
            if failed_symbols:
                scan_state: FuturesScanState = "degraded"
                warnings.append("All requested symbols failed during the futures-paper scan.")
            else:
                scan_state = "insufficient_data"
                warnings.append("No symbols had enough available data for futures-paper scanning.")
        elif failed_symbols:
            warnings.append("Some symbols could not be scanned; partial results are shown.")
            scan_state = "partial"
        elif not long_candidates and not short_candidates:
            scan_state = "ready"
            warnings.append("No high-quality LONG/SHORT candidates found under current filters.")
        else:
            scan_state = "ready"
            if any(signal.evidence_strength in {"insufficient", "unvalidated", "weak"} for signal in long_candidates + short_candidates):
                warnings.append("Candidates shown with weak validation because internal outcome history is still limited.")

        return FuturesOpportunityScanReport(
            generated_at=datetime.now(tz=UTC),
            scan_state=scan_state,
            long_candidates=long_candidates,
            short_candidates=short_candidates,
            neutral_candidates=neutral_candidates,
            warnings=warnings,
            scanned_count=len(visible_signals),
            failed_symbols=list(failed_symbols),
        )


def _build_signal(
    *,
    context: FuturesSignalContext,
    direction: FuturesDirection,
    scores: "MarketOpportunityScores",
    opportunity_score: int,
    direction_score: int,
    validation_score: int | None,
    confidence: int,
    evidence_strength: FuturesEvidenceStrength,
    risk_grade: FuturesRiskGrade,
    current_price: Decimal | None,
    fee_impact: Decimal | None,
    reason: str,
    warnings: tuple[str, ...],
    timestamp: datetime,
) -> FuturesPaperSignal:
    stop_loss, take_profit = _risk_levels(direction=direction, candles=context.candles, current_price=current_price)
    return FuturesPaperSignal(
        symbol=context.symbol,
        direction=direction,
        opportunity_score=max(0, min(100, opportunity_score)),
        direction_score=max(0, min(100, direction_score)),
        momentum_score=scores.momentum_score,
        trend_score=scores.trend_score,
        volatility_quality_score=scores.volatility_quality_score,
        liquidity_score=scores.liquidity_score,
        risk_score=scores.risk_score,
        validation_score=validation_score,
        confidence=max(0, min(100, confidence)),
        evidence_strength=evidence_strength,
        trend=scores.trend,
        momentum=scores.momentum,
        best_horizon=context.preferred_horizon or "15m",
        risk_grade=risk_grade,
        regime=context.regime_analysis.regime_label if context.regime_analysis is not None else None,
        current_price=current_price,
        reason=reason,
        invalidation_hint=context.invalidation_hint or _invalidation_hint(direction, stop_loss),
        suggested_entry_zone=_entry_zone(current_price),
        suggested_stop_loss=stop_loss,
        suggested_take_profit=take_profit,
        estimated_fee_impact=fee_impact,
        leverage_suggestion="1x paper-only",
        liquidation_safety_note=(
            f"Paper futures only. Suggested leverage is capped at {MAX_PAPER_LEVERAGE}x; "
            "this does not place real futures orders or guarantee liquidation safety."
        ),
        similar_setup_summary=_similar_summary(context.similar_setup),
        eligibility_status=_eligibility_status(context.trade_eligibility),
        warnings=warnings,
        timestamp=timestamp,
    )


@dataclass(slots=True)
class MarketOpportunityScores:
    trend: str
    momentum: str
    trend_score: int
    momentum_score: int
    volatility_quality_score: int
    liquidity_score: int
    risk_score: int
    bullish_direction_score: int
    bearish_direction_score: int


def _long_score(context: FuturesSignalContext, *, market_scores: MarketOpportunityScores) -> int:
    score = market_scores.bullish_direction_score
    technical = context.technical_analysis
    regime = context.regime_analysis
    if technical is not None and technical.data_state == "ready":
        if technical.trend_direction == "bullish":
            score += 18
        elif technical.trend_direction == "sideways":
            score -= 25
        if technical.momentum_state in {"bullish", "overbought"}:
            score += 12
        elif technical.momentum_state == "neutral":
            score -= 10
        if technical.multi_timeframe_agreement == "bullish_alignment":
            score += 10
        elif technical.multi_timeframe_agreement == "mixed":
            score -= 10
        if technical.breakout_readiness == "high" and technical.breakout_bias == "upside":
            score += 10
        if technical.trend_strength_score is not None:
            score += min(10, technical.trend_strength_score // 10)
    if regime is not None and regime.data_state == "ready":
        if regime.regime_label in {"trending_up", "breakout_building"}:
            score += 8
        if regime.regime_label in {"trending_down", "choppy", "low_liquidity"}:
            score -= 20
    return max(0, min(100, score))


def _short_score(context: FuturesSignalContext, *, market_scores: MarketOpportunityScores) -> int:
    score = market_scores.bearish_direction_score
    technical = context.technical_analysis
    regime = context.regime_analysis
    if technical is not None and technical.data_state == "ready":
        if technical.trend_direction == "bearish":
            score += 18
        elif technical.trend_direction == "sideways":
            score -= 25
        if technical.momentum_state in {"bearish", "oversold"}:
            score += 12
        elif technical.momentum_state == "neutral":
            score -= 10
        if technical.multi_timeframe_agreement == "bearish_alignment":
            score += 10
        elif technical.multi_timeframe_agreement == "mixed":
            score -= 10
        if technical.breakout_readiness == "high" and technical.breakout_bias == "downside":
            score += 10
        if technical.reversal_risk == "high" and technical.trend_direction == "bearish":
            score += 8
        if technical.trend_strength_score is not None:
            score += min(10, technical.trend_strength_score // 10)
    if regime is not None and regime.data_state == "ready":
        if regime.regime_label in {"trending_down", "reversal_risk"}:
            score += 8
        if regime.regime_label in {"trending_up", "choppy", "low_liquidity"}:
            score -= 20
    return max(0, min(100, score))


def _risk_grade(
    *,
    technical: TechnicalAnalysisSnapshot | None,
    regime_label: str | None,
    spread_ratio_pct: Decimal | None,
    blocker_reasons: Sequence[str],
    volatility_quality_score: int,
    liquidity_score: int,
    risk_score: int,
) -> FuturesRiskGrade:
    if blocker_reasons or regime_label in {"choppy", "low_liquidity", "high_volatility"}:
        return "high"
    if spread_ratio_pct is not None and spread_ratio_pct >= Decimal("0.35"):
        return "high"
    if liquidity_score < 30 or volatility_quality_score < 25 or risk_score < 25:
        return "high"
    if technical is not None and technical.volatility_regime == "high":
        return "high"
    if liquidity_score < 50 or volatility_quality_score < 45 or risk_score < 45:
        return "medium"
    if regime_label in {"reversal_risk", "sideways"}:
        return "medium"
    return "low"


def _blocking_reason(
    *,
    risk_grade: FuturesRiskGrade,
    regime_label: str | None,
    blocker_reasons: Sequence[str],
    eligibility_status: str,
    fee_impact: Decimal | None,
) -> str | None:
    if blocker_reasons:
        return "Current blockers are active, so this symbol is AVOID for paper futures."
    if regime_label in {"choppy", "low_liquidity"}:
        return f"Current regime is {regime_label}; directional futures-paper candidates are avoided."
    if eligibility_status == "not_eligible":
        return "Internal eligibility evidence is negative, so this symbol is AVOID for paper futures."
    if fee_impact is not None and fee_impact >= Decimal("0.45"):
        return "Estimated fee/spread impact is too high for a clean paper futures candidate."
    if risk_grade == "high":
        return "Current volatility, liquidity, or risk conditions are too weak for a paper futures candidate."
    return None


def _evidence_strength(
    similar_setup: SimilarSetupReport | None,
    eligibility: TradeEligibilityResult | None,
) -> FuturesEvidenceStrength:
    if eligibility is not None:
        return eligibility.evidence_strength
    if similar_setup is not None and similar_setup.status == "ready":
        return similar_setup.reliability_label
    return "unvalidated"


def _validation_score(strength: FuturesEvidenceStrength) -> int | None:
    return {
        "strong": 90,
        "promising": 75,
        "mixed": 55,
        "weak": 35,
        "unvalidated": 20,
        "insufficient": None,
    }[strength]


def _eligibility_status(eligibility: TradeEligibilityResult | None) -> str:
    return eligibility.status if eligibility is not None else "insufficient_data"


def _similar_summary(report: SimilarSetupReport | None) -> str:
    if report is None:
        return "No similar-setup evidence is available yet."
    return report.explanation


def _regime_warnings(regime: RegimeAnalysisSnapshot | None) -> tuple[str, ...]:
    if regime is None:
        return ()
    return regime.risk_warnings


def _safety_warnings(risk_grade: FuturesRiskGrade, regime_label: str | None) -> tuple[str, ...]:
    warnings = ["Paper futures scanner is advisory-only and never places real orders."]
    if risk_grade == "high":
        warnings.append("High-risk conditions prevent LONG/SHORT ranking.")
    if regime_label in {"choppy", "low_liquidity"}:
        warnings.append("Directional futures-paper trades are avoided in choppy or low-liquidity regimes.")
    return tuple(warnings)


def _estimated_fee_impact(spread_ratio_pct: Decimal | None) -> Decimal | None:
    if spread_ratio_pct is None:
        return None
    return (spread_ratio_pct + Decimal("0.08")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _market_scores(
    candles: Sequence[Candle],
    higher_timeframe_candles: Sequence[Candle],
) -> MarketOpportunityScores:
    closes = [candle.close for candle in candles]
    latest_close = closes[-1]
    fast_ma = _simple_average(closes[-12:])
    slow_ma = _simple_average(closes[-36:]) if len(closes) >= 36 else _simple_average(closes)
    higher_closes = [candle.close for candle in higher_timeframe_candles]
    higher_fast = _simple_average(higher_closes[-8:]) if len(higher_closes) >= 8 else None
    higher_slow = _simple_average(higher_closes[-24:]) if len(higher_closes) >= 24 else None
    structure = _structure_direction(candles)
    momentum_pct = _momentum_pct(candles)
    flip_rate = _direction_flip_rate(candles[-24:])

    bullish = 0
    bearish = 0
    if latest_close > fast_ma > slow_ma:
        bullish += 35
    elif latest_close < fast_ma < slow_ma:
        bearish += 35
    else:
        bullish += 12 if latest_close > slow_ma else 4
        bearish += 12 if latest_close < slow_ma else 4

    if structure == "bullish":
        bullish += 25
    elif structure == "bearish":
        bearish += 25
    else:
        bullish += 8
        bearish += 8

    if higher_fast is not None and higher_slow is not None:
        if higher_fast > higher_slow:
            bullish += 15
        elif higher_fast < higher_slow:
            bearish += 15

    if momentum_pct > Decimal("1.2"):
        bullish += 25
    elif momentum_pct > Decimal("0.35"):
        bullish += 15
    elif momentum_pct < Decimal("-1.2"):
        bearish += 25
    elif momentum_pct < Decimal("-0.35"):
        bearish += 15

    trend_score = max(bullish, bearish)
    momentum_score = min(100, int(abs(momentum_pct) * Decimal("12")) + (25 if abs(momentum_pct) >= Decimal("0.35") else 5))
    volatility_quality_score = _volatility_quality_score(candles)
    liquidity_score = _liquidity_score(candles)
    risk_score = min(volatility_quality_score, liquidity_score)

    if flip_rate >= Decimal("0.58") and trend_score < 70:
        trend = "choppy"
        momentum = "mixed"
        bullish = min(bullish, 48)
        bearish = min(bearish, 48)
        risk_score = min(risk_score, 35)
    elif bullish >= bearish + 10:
        trend = "bullish"
        momentum = "positive" if momentum_pct > Decimal("0") else "fading"
    elif bearish >= bullish + 10:
        trend = "bearish"
        momentum = "negative" if momentum_pct < Decimal("0") else "fading"
    else:
        trend = "mixed"
        momentum = "mixed"

    return MarketOpportunityScores(
        trend=trend,
        momentum=momentum,
        trend_score=max(0, min(100, trend_score)),
        momentum_score=max(0, min(100, momentum_score)),
        volatility_quality_score=volatility_quality_score,
        liquidity_score=liquidity_score,
        risk_score=max(0, min(100, risk_score)),
        bullish_direction_score=max(0, min(100, bullish)),
        bearish_direction_score=max(0, min(100, bearish)),
    )


def _simple_average(values: Sequence[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return sum(values, start=Decimal("0")) / Decimal(len(values))


def _structure_direction(candles: Sequence[Candle]) -> str:
    recent = list(candles[-24:])
    if len(recent) < 12:
        return "mixed"
    first = recent[:12]
    second = recent[12:]
    first_high = max(candle.high for candle in first)
    first_low = min(candle.low for candle in first)
    second_high = max(candle.high for candle in second)
    second_low = min(candle.low for candle in second)
    if second_high > first_high and second_low > first_low:
        return "bullish"
    if second_high < first_high and second_low < first_low:
        return "bearish"
    return "mixed"


def _direction_flip_rate(candles: Sequence[Candle]) -> Decimal:
    moves: list[int] = []
    for previous, current in zip(candles, candles[1:]):
        change = current.close - previous.close
        if change > Decimal("0"):
            moves.append(1)
        elif change < Decimal("0"):
            moves.append(-1)
    if len(moves) < 2:
        return Decimal("0")
    flips = sum(1 for previous, current in zip(moves, moves[1:]) if previous != current)
    return Decimal(flips) / Decimal(len(moves) - 1)


def _volatility_quality_score(candles: Sequence[Candle]) -> int:
    recent = list(candles[-24:])
    if not recent:
        return 0
    ranges = []
    for candle in recent:
        if candle.close <= Decimal("0"):
            continue
        ranges.append(((candle.high - candle.low) / candle.close) * Decimal("100"))
    if not ranges:
        return 0
    average_range_pct = _simple_average(ranges)
    if Decimal("0.08") <= average_range_pct <= Decimal("2.8"):
        return 85
    if Decimal("0.03") <= average_range_pct <= Decimal("4.5"):
        return 62
    if average_range_pct <= Decimal("7.0"):
        return 35
    return 15


def _liquidity_score(candles: Sequence[Candle]) -> int:
    recent = list(candles[-24:])
    if not recent:
        return 0
    average_quote_volume = _simple_average([candle.quote_volume for candle in recent])
    if average_quote_volume >= Decimal("1000000"):
        return 90
    if average_quote_volume >= Decimal("250000"):
        return 72
    if average_quote_volume >= Decimal("50000"):
        return 48
    if average_quote_volume >= Decimal("10000"):
        return 28
    return 12


def _opportunity_score(
    *,
    direction_score: int,
    trend_score: int,
    momentum_score: int,
    volatility_quality_score: int,
    liquidity_score: int,
    risk_score: int,
    validation_score: int | None,
) -> int:
    validation_component = validation_score if validation_score is not None else 20
    score = (
        Decimal(direction_score) * Decimal("0.28")
        + Decimal(trend_score) * Decimal("0.22")
        + Decimal(momentum_score) * Decimal("0.18")
        + Decimal(volatility_quality_score) * Decimal("0.12")
        + Decimal(liquidity_score) * Decimal("0.10")
        + Decimal(risk_score) * Decimal("0.07")
        + Decimal(validation_component) * Decimal("0.03")
    )
    return max(0, min(100, int(score.quantize(Decimal("1"), rounding=ROUND_HALF_UP))))


def _confidence_from_scores(
    *,
    opportunity_score: int,
    validation_score: int | None,
    risk_score: int,
) -> int:
    validation_component = validation_score if validation_score is not None else 20
    score = (
        Decimal(opportunity_score) * Decimal("0.78")
        + Decimal(validation_component) * Decimal("0.12")
        + Decimal(risk_score) * Decimal("0.10")
    )
    return max(0, min(100, int(score.quantize(Decimal("1"), rounding=ROUND_HALF_UP))))


def _direction_reason(
    *,
    direction: Literal["long", "short"],
    evidence_strength: FuturesEvidenceStrength,
    trend: str,
    momentum: str,
) -> str:
    validation_note = ""
    if evidence_strength in {"insufficient", "unvalidated", "weak"}:
        validation_note = " Internal validation is still limited, so treat this as weakly validated."
    if direction == "long":
        return (
            f"Current market structure favors a paper LONG: trend is {trend}, momentum is {momentum}, "
            f"and liquidity/volatility conditions are acceptable.{validation_note}"
        )
    return (
        f"Current market structure favors a paper SHORT: trend is {trend}, momentum is {momentum}, "
        f"and liquidity/volatility conditions are acceptable.{validation_note}"
    )


def _momentum_pct(candles: Sequence[Candle]) -> Decimal:
    recent = list(candles[-24:])
    if len(recent) < 2 or recent[0].close <= Decimal("0"):
        return Decimal("0")
    return (((recent[-1].close - recent[0].close) / recent[0].close) * Decimal("100")).quantize(
        Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )


def _risk_levels(
    *,
    direction: FuturesDirection,
    candles: Sequence[Candle],
    current_price: Decimal | None,
) -> tuple[Decimal | None, Decimal | None]:
    if current_price is None or direction not in {"long", "short"}:
        return None, None
    recent = list(candles[-24:])
    if not recent:
        return None, None
    average_range = sum((candle.high - candle.low for candle in recent), start=Decimal("0")) / Decimal(len(recent))
    buffer = max(average_range, current_price * Decimal("0.006"))
    if direction == "long":
        return (
            (current_price - buffer).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
            (current_price + (buffer * Decimal("1.8"))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
        )
    return (
        (current_price + buffer).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
        (current_price - (buffer * Decimal("1.8"))).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
    )


def _entry_zone(current_price: Decimal | None) -> str | None:
    if current_price is None:
        return None
    lower = (current_price * Decimal("0.998")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    upper = (current_price * Decimal("1.002")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return f"{lower} - {upper}"


def _invalidation_hint(direction: FuturesDirection, stop_loss: Decimal | None) -> str | None:
    if stop_loss is None or direction not in {"long", "short"}:
        return None
    if direction == "long":
        return f"Paper LONG invalidates below {stop_loss}."
    return f"Paper SHORT invalidates above {stop_loss}."
