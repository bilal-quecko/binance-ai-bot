"""Deterministic market-regime analysis for selected symbols."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from app.analysis.pattern_summary import PatternAnalysisSnapshot
from app.analysis.technical import TechnicalAnalysisSnapshot
from app.features.models import FeatureSnapshot
from app.market_data.candles import Candle


RegimeDataState = Literal["ready", "incomplete"]
RegimeLabel = Literal[
    "trending_up",
    "trending_down",
    "sideways",
    "high_volatility",
    "low_liquidity",
    "choppy",
    "breakout_building",
    "reversal_risk",
]


@dataclass(slots=True)
class RegimeAnalysisSnapshot:
    """Typed market-regime output for one selected symbol."""

    symbol: str
    generated_at: datetime
    horizon: str
    data_state: RegimeDataState
    status_message: str | None
    regime_label: RegimeLabel | None
    confidence: int
    supporting_evidence: tuple[str, ...]
    risk_warnings: tuple[str, ...]
    preferred_trading_behavior: str
    avoid_conditions: tuple[str, ...]


class RegimeAnalysisService:
    """Classify the selected symbol into a deterministic trading regime."""

    def analyze(
        self,
        *,
        symbol: str,
        horizon: str,
        candles: Sequence[Candle],
        technical_analysis: TechnicalAnalysisSnapshot | None,
        pattern_analysis: PatternAnalysisSnapshot | None,
        feature_snapshot: FeatureSnapshot | None,
    ) -> RegimeAnalysisSnapshot:
        """Return a trader-readable regime classification."""

        if len(candles) < 6 or technical_analysis is None or technical_analysis.data_state != "ready":
            return RegimeAnalysisSnapshot(
                symbol=symbol,
                generated_at=datetime.now(tz=UTC),
                horizon=horizon,
                data_state="incomplete",
                status_message=f"Regime analysis for {symbol} needs more candle and technical context.",
                regime_label=None,
                confidence=0,
                supporting_evidence=(),
                risk_warnings=("Regime classification is unavailable until enough recent candles are stored.",),
                preferred_trading_behavior="Wait for more history before relying on regime-aware filtering.",
                avoid_conditions=("Do not treat missing regime context as a positive trade filter.",),
            )

        scores: dict[RegimeLabel, int] = {
            "trending_up": 0,
            "trending_down": 0,
            "sideways": 0,
            "high_volatility": 0,
            "low_liquidity": 0,
            "choppy": 0,
            "breakout_building": 0,
            "reversal_risk": 0,
        }
        evidence: dict[RegimeLabel, list[str]] = {label: [] for label in scores}
        warnings: list[str] = []
        avoid_conditions: list[str] = []

        self._score_technical(technical_analysis, scores, evidence, warnings, avoid_conditions)
        self._score_pattern(pattern_analysis, scores, evidence, warnings, avoid_conditions)
        self._score_candles(candles, scores, evidence, warnings, avoid_conditions)
        self._score_microstructure(feature_snapshot, candles, scores, evidence, warnings, avoid_conditions)

        regime_label = _dominant_regime(scores)
        selected_evidence = tuple(evidence[regime_label])
        confidence = _confidence(scores[regime_label], selected_evidence, warnings)
        return RegimeAnalysisSnapshot(
            symbol=symbol,
            generated_at=technical_analysis.timestamp,
            horizon=horizon,
            data_state="ready",
            status_message=f"Regime analysis is ready for {symbol}.",
            regime_label=regime_label,
            confidence=confidence,
            supporting_evidence=selected_evidence,
            risk_warnings=tuple(dict.fromkeys(warnings)),
            preferred_trading_behavior=_preferred_behavior(regime_label),
            avoid_conditions=tuple(dict.fromkeys(avoid_conditions or _default_avoid_conditions(regime_label))),
        )

    def _score_technical(
        self,
        technical: TechnicalAnalysisSnapshot,
        scores: dict[RegimeLabel, int],
        evidence: dict[RegimeLabel, list[str]],
        warnings: list[str],
        avoid_conditions: list[str],
    ) -> None:
        strength_score = technical.trend_strength_score or 0
        if technical.trend_direction == "bullish":
            scores["trending_up"] += 2 + (1 if strength_score >= 65 else 0)
            evidence["trending_up"].append(
                f"Technical trend is bullish with {technical.trend_strength or 'unknown'} strength."
            )
        elif technical.trend_direction == "bearish":
            scores["trending_down"] += 2 + (1 if strength_score >= 65 else 0)
            evidence["trending_down"].append(
                f"Technical trend is bearish with {technical.trend_strength or 'unknown'} strength."
            )
        elif technical.trend_direction == "sideways":
            scores["sideways"] += 2
            evidence["sideways"].append("Technical trend is sideways.")

        if technical.multi_timeframe_agreement == "bullish_alignment":
            scores["trending_up"] += 2
            evidence["trending_up"].append("Derived timeframes are aligned bullish.")
        elif technical.multi_timeframe_agreement == "bearish_alignment":
            scores["trending_down"] += 2
            evidence["trending_down"].append("Derived timeframes are aligned bearish.")
        elif technical.multi_timeframe_agreement == "mixed":
            scores["choppy"] += 2
            evidence["choppy"].append("Derived timeframe agreement is mixed.")
            warnings.append("Mixed timeframe alignment can increase false signals.")

        if technical.volatility_regime == "high":
            scores["high_volatility"] += 3
            evidence["high_volatility"].append("ATR-based volatility regime is high.")
            warnings.append("High volatility can widen adverse moves and make stops less reliable.")
            avoid_conditions.append("Avoid weak-confidence entries while volatility remains high.")
        if technical.breakout_readiness == "high" and technical.breakout_bias in {"upside", "downside"}:
            scores["breakout_building"] += 3
            evidence["breakout_building"].append(
                f"Breakout readiness is high with {technical.breakout_bias} bias."
            )
        if technical.reversal_risk == "high":
            scores["reversal_risk"] += 3
            evidence["reversal_risk"].append("Technical reversal risk is high.")
            warnings.append("Reversal risk is elevated; trend-following entries need confirmation.")
            avoid_conditions.append("Avoid chasing extended moves without fresh confirmation.")

    def _score_pattern(
        self,
        pattern: PatternAnalysisSnapshot | None,
        scores: dict[RegimeLabel, int],
        evidence: dict[RegimeLabel, list[str]],
        warnings: list[str],
        avoid_conditions: list[str],
    ) -> None:
        if pattern is None or pattern.data_state != "ready":
            warnings.append("Pattern context is incomplete for this regime read.")
            return
        if pattern.overall_direction == "bullish" and pattern.trend_character == "persistent":
            scores["trending_up"] += 2
            evidence["trending_up"].append(f"{pattern.horizon.upper()} pattern is persistently bullish.")
        elif pattern.overall_direction == "bearish" and pattern.trend_character == "persistent":
            scores["trending_down"] += 2
            evidence["trending_down"].append(f"{pattern.horizon.upper()} pattern is persistently bearish.")
        if pattern.trend_character == "choppy":
            scores["choppy"] += 3
            evidence["choppy"].append(f"{pattern.horizon.upper()} pattern behavior is choppy.")
            warnings.append("Choppy pattern behavior can turn directional signals into noise.")
            avoid_conditions.append("Avoid directional entries until persistence improves.")
        if pattern.breakout_tendency == "breakout_prone":
            scores["breakout_building"] += 2
            evidence["breakout_building"].append(f"{pattern.horizon.upper()} pattern is breakout-prone.")
        elif pattern.breakout_tendency == "range_bound":
            scores["sideways"] += 2
            evidence["sideways"].append(f"{pattern.horizon.upper()} pattern is range-bound.")
        if pattern.reversal_tendency == "elevated":
            scores["reversal_risk"] += 2
            evidence["reversal_risk"].append(f"{pattern.horizon.upper()} reversal tendency is elevated.")
        if pattern.realized_volatility_pct is not None and pattern.realized_volatility_pct >= Decimal("3"):
            scores["high_volatility"] += 2
            evidence["high_volatility"].append(
                f"{pattern.horizon.upper()} realized volatility is {pattern.realized_volatility_pct}%."
            )

    def _score_candles(
        self,
        candles: Sequence[Candle],
        scores: dict[RegimeLabel, int],
        evidence: dict[RegimeLabel, list[str]],
        warnings: list[str],
        avoid_conditions: list[str],
    ) -> None:
        recent = list(candles[-24:])
        if len(recent) < 6:
            return
        flip_rate = _direction_flip_rate(recent)
        average_range_pct = _average_range_pct(recent)
        if flip_rate >= Decimal("45"):
            scores["choppy"] += 2
            evidence["choppy"].append(f"Recent candle direction flip rate is {flip_rate}%.")
        if average_range_pct >= Decimal("1.2"):
            scores["high_volatility"] += 2
            evidence["high_volatility"].append(f"Recent average candle range is {average_range_pct}%.")
        if average_range_pct <= Decimal("0.08"):
            scores["sideways"] += 1
            evidence["sideways"].append("Recent candle ranges are unusually compressed.")
            avoid_conditions.append("Avoid breakout assumptions until range expansion appears.")
        average_quote_volume = sum((candle.quote_volume for candle in recent), start=Decimal("0")) / Decimal(len(recent))
        if average_quote_volume <= Decimal("50000"):
            scores["low_liquidity"] += 1
            evidence["low_liquidity"].append("Recent quote volume is thin.")
            warnings.append("Thin quote volume can make fills and slippage less reliable.")

    def _score_microstructure(
        self,
        feature: FeatureSnapshot | None,
        candles: Sequence[Candle],
        scores: dict[RegimeLabel, int],
        evidence: dict[RegimeLabel, list[str]],
        warnings: list[str],
        avoid_conditions: list[str],
    ) -> None:
        if feature is None:
            return
        latest_close = candles[-1].close if candles else Decimal("0")
        spread_ratio = None
        if feature.bid_ask_spread is not None and feature.mid_price is not None and feature.mid_price > Decimal("0"):
            spread_ratio = (feature.bid_ask_spread / feature.mid_price) * Decimal("100")
        elif feature.bid_ask_spread is not None and latest_close > Decimal("0"):
            spread_ratio = (feature.bid_ask_spread / latest_close) * Decimal("100")
        if spread_ratio is not None and spread_ratio >= Decimal("0.35"):
            scores["low_liquidity"] += 4
            evidence["low_liquidity"].append(f"Bid/ask spread is wide at {spread_ratio.quantize(Decimal('0.0001'))}%.")
            warnings.append("Wide spread can erase expected edge before a trade begins.")
            avoid_conditions.append("Avoid entries when spread remains wide relative to price.")
        if feature.order_book_imbalance is not None and abs(feature.order_book_imbalance) >= Decimal("0.65"):
            warnings.append("Order-book imbalance is extreme; short-term movement may be unstable.")


def _dominant_regime(scores: dict[RegimeLabel, int]) -> RegimeLabel:
    priority: dict[RegimeLabel, int] = {
        "low_liquidity": 8,
        "high_volatility": 7,
        "reversal_risk": 6,
        "breakout_building": 5,
        "choppy": 4,
        "trending_down": 3,
        "trending_up": 2,
        "sideways": 1,
    }
    return max(scores, key=lambda label: (scores[label], priority[label]))


def _confidence(score: int, evidence: tuple[str, ...], warnings: list[str]) -> int:
    if score <= 0:
        return 35
    base = min(85, 40 + score * 8 + min(12, len(evidence) * 3))
    base -= min(15, len(warnings) * 2)
    return max(20, min(95, base))


def _preferred_behavior(regime: RegimeLabel) -> str:
    return {
        "trending_up": "Prefer long-biased paper setups with confirmation and normal cost checks.",
        "trending_down": "Prefer caution in spot mode; exits or avoidance are usually cleaner than new long entries.",
        "sideways": "Prefer waiting, range awareness, and stronger confirmation before acting.",
        "high_volatility": "Use smaller risk, demand stronger confirmation, and expect wider adverse moves.",
        "low_liquidity": "Avoid automation consideration until spread and liquidity normalize.",
        "choppy": "Favor watch-only behavior until directional persistence improves.",
        "breakout_building": "Watch for confirmed breakout direction before treating the setup as actionable.",
        "reversal_risk": "Protect open paper positions and avoid chasing the current move.",
    }[regime]


def _default_avoid_conditions(regime: RegimeLabel) -> tuple[str, ...]:
    return {
        "trending_up": ("Avoid long entries if confidence is weak or support fails.",),
        "trending_down": ("Avoid new spot-long entries against bearish structure.",),
        "sideways": ("Avoid low-edge trades inside a range.",),
        "high_volatility": ("Avoid trades where expected edge does not clear costs and volatility buffer.",),
        "low_liquidity": ("Avoid trades while spread is wide or quote volume is thin.",),
        "choppy": ("Avoid single-signal entries without multi-timeframe confirmation.",),
        "breakout_building": ("Avoid pre-breakout entries without confirmation.",),
        "reversal_risk": ("Avoid chasing extended moves near reversal conditions.",),
    }[regime]


def _direction_flip_rate(candles: Sequence[Candle]) -> Decimal:
    directions: list[int] = []
    for previous, current in zip(candles, candles[1:]):
        if current.close > previous.close:
            directions.append(1)
        elif current.close < previous.close:
            directions.append(-1)
        else:
            directions.append(0)
    meaningful = [direction for direction in directions if direction != 0]
    if len(meaningful) < 2:
        return Decimal("0")
    flips = sum(1 for previous, current in zip(meaningful, meaningful[1:]) if previous != current)
    return ((Decimal(flips) / Decimal(len(meaningful) - 1)) * Decimal("100")).quantize(
        Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )


def _average_range_pct(candles: Sequence[Candle]) -> Decimal:
    ranges = [
        ((candle.high - candle.low) / candle.close) * Decimal("100")
        for candle in candles
        if candle.close > Decimal("0")
    ]
    if not ranges:
        return Decimal("0")
    return (sum(ranges, start=Decimal("0")) / Decimal(len(ranges))).quantize(
        Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )
