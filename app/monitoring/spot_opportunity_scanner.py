"""Paper-only Spot opportunity scanner."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Sequence

from app.analysis.regime import RegimeAnalysisSnapshot
from app.analysis.technical import TechnicalAnalysisSnapshot
from app.market_data.candles import Candle
from app.monitoring.signal_validation import SignalValidationReport
from app.monitoring.trade_eligibility import TradeEligibilityResult


SpotAction = Literal["buy_candidate", "watch", "avoid", "exit_watch"]
SpotEvidenceStrength = Literal["insufficient", "weak", "mixed", "promising", "strong"]
SpotRiskGrade = Literal["low", "medium", "high"]
SpotScanState = Literal["ready", "partial", "insufficient_data", "degraded"]


@dataclass(slots=True)
class SpotScannerContext:
    """Inputs for one Spot scanner symbol."""

    symbol: str
    candles: Sequence[Candle]
    technical_analysis: TechnicalAnalysisSnapshot | None = None
    regime_analysis: RegimeAnalysisSnapshot | None = None
    signal_validation: SignalValidationReport | None = None
    trade_eligibility: TradeEligibilityResult | None = None
    spread_ratio_pct: Decimal | None = None
    current_position_quantity: Decimal = Decimal("0")
    horizon: str = "7d"


@dataclass(slots=True)
class SpotOpportunitySignal:
    """One paper-only Spot scanner result."""

    symbol: str
    action: SpotAction
    opportunity_score: int
    confidence: int
    trend_score: int
    momentum_score: int
    volatility_quality_score: int
    liquidity_score: int
    structure_score: int
    regime_score: int
    validation_score: int | None
    eligibility_score: int
    evidence_strength: SpotEvidenceStrength
    trend: str
    momentum: str
    best_horizon: str
    risk_grade: SpotRiskGrade
    current_price: Decimal | None
    suggested_entry_zone: str | None
    suggested_stop_loss: Decimal | None
    suggested_take_profit: Decimal | None
    regime: str | None
    reason: str
    warnings: tuple[str, ...]
    timestamp: datetime
    data_source: str = "binance_spot"
    price_type: str = "spot_last_price"


@dataclass(slots=True)
class SpotOpportunityScanReport:
    """Ranked paper-only Spot scanner report."""

    generated_at: datetime
    scan_state: SpotScanState
    buy_candidates: list[SpotOpportunitySignal] = field(default_factory=list)
    watch_candidates: list[SpotOpportunitySignal] = field(default_factory=list)
    avoid_candidates: list[SpotOpportunitySignal] = field(default_factory=list)
    exit_watch_candidates: list[SpotOpportunitySignal] = field(default_factory=list)
    scanned_count: int = 0
    failed_symbols: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class SpotOpportunityScanner:
    """Score Binance Spot symbols for paper-only entry/watch/avoid decisions."""

    def build_signal(self, context: SpotScannerContext) -> SpotOpportunitySignal:
        """Return one deterministic paper-only Spot opportunity signal."""

        timestamp = datetime.now(tz=UTC)
        candles = list(context.candles)
        if len(candles) < 48:
            return _empty_signal(
                context=context,
                timestamp=timestamp,
                reason="Not enough stored Spot candle history is available for this symbol yet.",
                action="avoid",
            )

        current_price = candles[-1].close
        trend_score, trend_label = _trend_score(context.technical_analysis)
        momentum_score, momentum_label = _momentum_score(candles)
        volatility_score = _volatility_quality_score(candles, context.technical_analysis)
        liquidity_score = _liquidity_score(candles)
        structure_score = _structure_score(context.technical_analysis, current_price)
        regime_score = _regime_score(context.regime_analysis)
        validation_score = _validation_score(context.signal_validation, context.horizon)
        eligibility_score = _eligibility_score(context.trade_eligibility)
        evidence_strength = _evidence_strength(context.signal_validation, context.trade_eligibility)
        risk_grade = _risk_grade(
            volatility_score=volatility_score,
            liquidity_score=liquidity_score,
            regime_score=regime_score,
            eligibility_score=eligibility_score,
            spread_ratio_pct=context.spread_ratio_pct,
        )
        raw_score = (
            Decimal(trend_score) * Decimal("0.18")
            + Decimal(momentum_score) * Decimal("0.20")
            + Decimal(volatility_score) * Decimal("0.13")
            + Decimal(liquidity_score) * Decimal("0.13")
            + Decimal(structure_score) * Decimal("0.12")
            + Decimal(regime_score) * Decimal("0.10")
            + Decimal(validation_score if validation_score is not None else 50) * Decimal("0.08")
            + Decimal(eligibility_score) * Decimal("0.06")
        )
        if context.spread_ratio_pct is not None and context.spread_ratio_pct > Decimal("0.35"):
            raw_score -= Decimal("10")
        opportunity_score = _bounded_int(raw_score)
        confidence = _confidence(
            opportunity_score=opportunity_score,
            evidence_strength=evidence_strength,
            risk_grade=risk_grade,
            validation_score=validation_score,
        )
        action = _action(
            context=context,
            opportunity_score=opportunity_score,
            confidence=confidence,
            risk_grade=risk_grade,
            trend_score=trend_score,
            momentum_score=momentum_score,
        )
        stop_loss, take_profit = _risk_levels(action=action, candles=candles, current_price=current_price)
        return SpotOpportunitySignal(
            symbol=context.symbol,
            action=action,
            opportunity_score=opportunity_score,
            confidence=confidence,
            trend_score=trend_score,
            momentum_score=momentum_score,
            volatility_quality_score=volatility_score,
            liquidity_score=liquidity_score,
            structure_score=structure_score,
            regime_score=regime_score,
            validation_score=validation_score,
            eligibility_score=eligibility_score,
            evidence_strength=evidence_strength,
            trend=trend_label,
            momentum=momentum_label,
            best_horizon=context.horizon,
            risk_grade=risk_grade,
            current_price=current_price,
            suggested_entry_zone=_entry_zone(current_price),
            suggested_stop_loss=stop_loss,
            suggested_take_profit=take_profit,
            regime=context.regime_analysis.regime_label if context.regime_analysis is not None else None,
            reason=_reason(action=action, trend=trend_label, momentum=momentum_label, risk_grade=risk_grade),
            warnings=_warnings(context=context, risk_grade=risk_grade, evidence_strength=evidence_strength),
            timestamp=timestamp,
        )

    def build_report(
        self,
        *,
        signals: Sequence[SpotOpportunitySignal],
        failed_symbols: Sequence[str] = (),
        include_avoid: bool = True,
    ) -> SpotOpportunityScanReport:
        """Rank Spot signals into Spot-safe candidate groups."""

        buy = sorted(
            [signal for signal in signals if signal.action == "buy_candidate"],
            key=lambda item: (-item.opportunity_score, -item.confidence, item.symbol),
        )
        watch = sorted(
            [signal for signal in signals if signal.action == "watch"],
            key=lambda item: (-item.opportunity_score, -item.confidence, item.symbol),
        )
        exit_watch = sorted(
            [signal for signal in signals if signal.action == "exit_watch"],
            key=lambda item: (-item.opportunity_score, item.symbol),
        )
        avoid = sorted(
            [signal for signal in signals if signal.action == "avoid"],
            key=lambda item: (-item.opportunity_score, item.symbol),
        )
        if not include_avoid:
            avoid = []
        scan_state: SpotScanState = "ready"
        warnings = ["Spot scanner is paper-only and never places real Binance orders."]
        if failed_symbols and signals:
            scan_state = "partial"
            warnings.append("Some Spot symbols failed to scan; visible results are partial.")
        elif failed_symbols and not signals:
            scan_state = "degraded"
            warnings.append("No Spot symbols could be scanned successfully.")
        elif not signals:
            scan_state = "insufficient_data"
            warnings.append("No Spot scanner signals are available yet.")
        return SpotOpportunityScanReport(
            generated_at=datetime.now(tz=UTC),
            scan_state=scan_state,
            buy_candidates=buy[:10],
            watch_candidates=watch[:10],
            avoid_candidates=avoid[:10],
            exit_watch_candidates=exit_watch[:5],
            scanned_count=len(signals),
            failed_symbols=list(dict.fromkeys(failed_symbols)),
            warnings=warnings,
        )


def _empty_signal(
    *,
    context: SpotScannerContext,
    timestamp: datetime,
    reason: str,
    action: SpotAction,
) -> SpotOpportunitySignal:
    return SpotOpportunitySignal(
        symbol=context.symbol,
        action=action,
        opportunity_score=0,
        confidence=0,
        trend_score=0,
        momentum_score=0,
        volatility_quality_score=0,
        liquidity_score=0,
        structure_score=0,
        regime_score=0,
        validation_score=None,
        eligibility_score=0,
        evidence_strength="insufficient",
        trend="insufficient_data",
        momentum="insufficient_data",
        best_horizon=context.horizon,
        risk_grade="high",
        current_price=context.candles[-1].close if context.candles else None,
        suggested_entry_zone=None,
        suggested_stop_loss=None,
        suggested_take_profit=None,
        regime=context.regime_analysis.regime_label if context.regime_analysis is not None else None,
        reason=reason,
        warnings=("Not enough Spot candle history for scanner scoring.",),
        timestamp=timestamp,
    )


def _trend_score(technical: TechnicalAnalysisSnapshot | None) -> tuple[int, str]:
    if technical is None or technical.data_state != "ready":
        return 35, "unknown"
    strength = technical.trend_strength_score or 0
    if technical.trend_direction == "bullish":
        return _bounded_int(Decimal(52 + strength * 0.48)), "bullish"
    if technical.trend_direction == "bearish":
        return _bounded_int(Decimal(44 - strength * 0.30)), "bearish"
    return 50, "sideways"


def _momentum_score(candles: Sequence[Candle]) -> tuple[int, str]:
    close_now = candles[-1].close
    close_24 = candles[-24].close
    close_8 = candles[-8].close
    if close_now <= Decimal("0") or close_24 <= Decimal("0") or close_8 <= Decimal("0"):
        return 35, "unknown"
    momentum_24 = ((close_now - close_24) / close_24) * Decimal("100")
    momentum_8 = ((close_now - close_8) / close_8) * Decimal("100")
    score = Decimal("50") + (momentum_24 * Decimal("6")) + (momentum_8 * Decimal("5"))
    label = "bullish" if momentum_24 >= Decimal("1.0") else ("bearish" if momentum_24 <= Decimal("-1.0") else "mixed")
    return _bounded_int(score), label


def _volatility_quality_score(
    candles: Sequence[Candle],
    technical: TechnicalAnalysisSnapshot | None,
) -> int:
    ranges = [
        ((candle.high - candle.low) / candle.close) * Decimal("100")
        for candle in candles[-24:]
        if candle.close > Decimal("0")
    ]
    average_range = sum(ranges, start=Decimal("0")) / Decimal(max(1, len(ranges)))
    if technical is not None and technical.volatility_regime == "high":
        return 52
    if Decimal("0.25") <= average_range <= Decimal("1.8"):
        return 78
    if average_range < Decimal("0.12"):
        return 42
    return 62


def _liquidity_score(candles: Sequence[Candle]) -> int:
    average_quote_volume = sum((candle.quote_volume for candle in candles[-24:]), start=Decimal("0")) / Decimal("24")
    if average_quote_volume >= Decimal("10000000"):
        return 85
    if average_quote_volume >= Decimal("1000000"):
        return 70
    if average_quote_volume >= Decimal("250000"):
        return 52
    return 30


def _structure_score(technical: TechnicalAnalysisSnapshot | None, current_price: Decimal) -> int:
    if technical is None or technical.data_state != "ready":
        return 45
    score = Decimal("50")
    if technical.breakout_readiness == "high" and technical.breakout_bias == "upside":
        score += Decimal("22")
    elif technical.breakout_readiness == "medium" and technical.breakout_bias == "upside":
        score += Decimal("12")
    if technical.reversal_risk == "high":
        score -= Decimal("18")
    nearest_support = max([level for level in technical.support_levels if level < current_price], default=None)
    nearest_resistance = min([level for level in technical.resistance_levels if level > current_price], default=None)
    if nearest_support is not None and current_price > Decimal("0"):
        distance = ((current_price - nearest_support) / current_price) * Decimal("100")
        if distance <= Decimal("1.0"):
            score += Decimal("8")
    if nearest_resistance is not None and current_price > Decimal("0"):
        distance = ((nearest_resistance - current_price) / current_price) * Decimal("100")
        if distance <= Decimal("0.35") and technical.breakout_bias != "upside":
            score -= Decimal("8")
    return _bounded_int(score)


def _regime_score(regime: RegimeAnalysisSnapshot | None) -> int:
    if regime is None or regime.regime_label is None:
        return 50
    return {
        "trending_up": 82,
        "breakout_building": 76,
        "sideways": 55,
        "reversal_risk": 42,
        "trending_down": 35,
        "choppy": 30,
        "high_volatility": 35,
        "low_liquidity": 25,
    }.get(regime.regime_label, 50)


def _validation_score(report: SignalValidationReport | None, horizon: str) -> int | None:
    if report is None or not report.horizons:
        return None
    selected = next((item for item in report.horizons if item.horizon == horizon), None)
    if selected is None:
        selected = max(report.horizons, key=lambda item: (item.actionable_sample_size, item.expectancy_pct or Decimal("-999")))
    if selected.actionable_sample_size < 5 or selected.expectancy_pct is None:
        return 45
    score = Decimal("50") + (selected.expectancy_pct * Decimal("10"))
    if selected.win_rate_pct is not None:
        score += (selected.win_rate_pct - Decimal("50")) * Decimal("0.35")
    return _bounded_int(score)


def _eligibility_score(eligibility: TradeEligibilityResult | None) -> int:
    if eligibility is None:
        return 50
    return {
        "eligible": 85,
        "watch_only": 62,
        "insufficient_data": 48,
        "not_eligible": 25,
    }.get(eligibility.status, 50)


def _evidence_strength(
    validation: SignalValidationReport | None,
    eligibility: TradeEligibilityResult | None,
) -> SpotEvidenceStrength:
    if eligibility is not None and eligibility.evidence_strength in {"promising", "strong", "mixed", "weak", "insufficient"}:
        return eligibility.evidence_strength
    if validation is None or validation.status == "insufficient_data":
        return "insufficient"
    best = max(validation.horizons, key=lambda item: item.actionable_sample_size, default=None)
    if best is None or best.actionable_sample_size < 5:
        return "insufficient"
    if best.expectancy_pct is not None and best.expectancy_pct > Decimal("0.20"):
        return "promising"
    return "mixed"


def _risk_grade(
    *,
    volatility_score: int,
    liquidity_score: int,
    regime_score: int,
    eligibility_score: int,
    spread_ratio_pct: Decimal | None,
) -> SpotRiskGrade:
    if liquidity_score < 45 or regime_score < 35 or eligibility_score < 35:
        return "high"
    if spread_ratio_pct is not None and spread_ratio_pct > Decimal("0.45"):
        return "high"
    if volatility_score < 50 or regime_score < 50:
        return "medium"
    return "low"


def _confidence(
    *,
    opportunity_score: int,
    evidence_strength: SpotEvidenceStrength,
    risk_grade: SpotRiskGrade,
    validation_score: int | None,
) -> int:
    confidence = Decimal(opportunity_score)
    if validation_score is None:
        confidence -= Decimal("10")
    if evidence_strength == "insufficient":
        confidence -= Decimal("12")
    elif evidence_strength == "weak":
        confidence -= Decimal("8")
    elif evidence_strength == "strong":
        confidence += Decimal("5")
    if risk_grade == "high":
        confidence -= Decimal("12")
    elif risk_grade == "low":
        confidence += Decimal("4")
    return _bounded_int(confidence)


def _action(
    *,
    context: SpotScannerContext,
    opportunity_score: int,
    confidence: int,
    risk_grade: SpotRiskGrade,
    trend_score: int,
    momentum_score: int,
) -> SpotAction:
    if context.current_position_quantity > Decimal("0") and (trend_score < 42 or momentum_score < 38):
        return "exit_watch"
    if risk_grade == "high" or opportunity_score < 45:
        return "avoid"
    if opportunity_score >= 70 and confidence >= 62 and trend_score >= 58 and momentum_score >= 55:
        return "buy_candidate"
    return "watch"


def _risk_levels(
    *,
    action: SpotAction,
    candles: Sequence[Candle],
    current_price: Decimal,
) -> tuple[Decimal | None, Decimal | None]:
    if action not in {"buy_candidate", "watch"} or current_price <= Decimal("0"):
        return None, None
    lows = [candle.low for candle in candles[-24:]]
    highs = [candle.high for candle in candles[-24:]]
    recent_low = min(lows)
    recent_high = max(highs)
    stop = min(current_price * Decimal("0.985"), recent_low * Decimal("0.998"))
    target = max(current_price * Decimal("1.025"), recent_high * Decimal("1.002"))
    return _quantize_price(stop), _quantize_price(target)


def _entry_zone(current_price: Decimal | None) -> str | None:
    if current_price is None:
        return None
    lower = _quantize_price(current_price * Decimal("0.998"))
    upper = _quantize_price(current_price * Decimal("1.002"))
    return f"{lower}-{upper}"


def _reason(*, action: SpotAction, trend: str, momentum: str, risk_grade: SpotRiskGrade) -> str:
    if action == "buy_candidate":
        return f"Spot buy candidate: {trend} trend, {momentum} momentum, and {risk_grade} risk."
    if action == "exit_watch":
        return "Existing Spot exposure should be reviewed because trend or momentum is weakening."
    if action == "avoid":
        return f"Spot setup is avoid-only under current {risk_grade} risk and {momentum} momentum."
    return f"Spot setup is watch-only with {trend} trend and {momentum} momentum."


def _warnings(
    *,
    context: SpotScannerContext,
    risk_grade: SpotRiskGrade,
    evidence_strength: SpotEvidenceStrength,
) -> tuple[str, ...]:
    warnings = ["Spot scanner is advisory-only and paper-only."]
    if evidence_strength in {"insufficient", "weak"}:
        warnings.append("Validation evidence is still limited for this symbol.")
    if risk_grade == "high":
        warnings.append("Risk grade is high; do not route this to paper execution without deterministic checks.")
    if context.trade_eligibility is not None and context.trade_eligibility.status != "eligible":
        warnings.append(context.trade_eligibility.reason)
    return tuple(dict.fromkeys(warnings))


def _bounded_int(value: Decimal) -> int:
    return int(max(Decimal("0"), min(Decimal("100"), value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _quantize_price(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
