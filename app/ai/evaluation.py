"""AI advisory outcome evaluation helpers."""

from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

from app.storage.models import AISignalSnapshotRecord, MarketCandleSnapshotRecord
from app.storage.repositories import StorageRepository


ObservedDirection = Literal["bullish", "bearish", "sideways", "unknown"]
EvaluationHorizon = Literal["5m", "15m", "1h"]

SIDEWAYS_RETURN_THRESHOLD = Decimal("0.001")
HORIZON_WINDOWS: tuple[tuple[EvaluationHorizon, timedelta], ...] = (
    ("5m", timedelta(minutes=5)),
    ("15m", timedelta(minutes=15)),
    ("1h", timedelta(hours=1)),
)


def _round_percent(value: Decimal) -> Decimal:
    """Round a fractional score into a percentage value."""

    return (value * Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _classify_direction(return_pct: Decimal) -> ObservedDirection:
    """Classify a realized return into a coarse direction bucket."""

    if return_pct >= SIDEWAYS_RETURN_THRESHOLD:
        return "bullish"
    if return_pct <= -SIDEWAYS_RETURN_THRESHOLD:
        return "bearish"
    return "sideways"


@dataclass(slots=True)
class AIOutcomeSample:
    """One AI advisory snapshot evaluated against a later price outcome."""

    symbol: str
    snapshot_time: datetime
    horizon: EvaluationHorizon
    bias: str
    confidence: int
    entry_signal: bool
    exit_signal: bool
    suggested_action: str
    baseline_close: Decimal
    future_close: Decimal
    return_pct: Decimal
    observed_direction: ObservedDirection
    directional_correct: bool
    false_positive: bool
    false_reversal: bool


@dataclass(slots=True)
class AIOutcomeSummary:
    """Aggregated AI outcome metrics for one horizon."""

    horizon: EvaluationHorizon
    sample_size: int
    directional_accuracy_pct: Decimal
    confidence_calibration_pct: Decimal
    false_positive_count: int
    false_positive_rate_pct: Decimal
    false_reversal_count: int
    false_reversal_rate_pct: Decimal


@dataclass(slots=True)
class AIOutcomeEvaluation:
    """Symbol-scoped AI outcome evaluation payload."""

    symbol: str
    generated_at: datetime
    horizons: list[AIOutcomeSummary]
    recent_samples: list[AIOutcomeSample]


class AIOutcomeEvaluator:
    """Evaluate persisted AI snapshots against later persisted candle closes."""

    def __init__(self, repository: StorageRepository) -> None:
        self._repository = repository

    def evaluate(
        self,
        *,
        symbol: str,
        timeframe: str = "1m",
        recent_limit: int = 10,
    ) -> AIOutcomeEvaluation:
        """Return symbol-scoped AI outcome metrics and recent evaluated samples."""

        normalized_symbol = symbol.strip().upper()
        ai_history = self._repository.get_ai_signal_history(symbol=normalized_symbol)
        candle_history = self._repository.get_market_candle_history(
            symbol=normalized_symbol,
            timeframe=timeframe,
        )
        samples_by_horizon = self._build_samples(ai_history=ai_history, candle_history=candle_history)
        horizons = [
            self._build_summary(horizon, samples_by_horizon[horizon])
            for horizon, _ in HORIZON_WINDOWS
        ]
        recent_samples: list[AIOutcomeSample] = []
        for horizon, _ in HORIZON_WINDOWS:
            recent_samples.extend(samples_by_horizon[horizon])
        recent_samples.sort(key=lambda sample: sample.snapshot_time, reverse=True)
        return AIOutcomeEvaluation(
            symbol=normalized_symbol,
            generated_at=datetime.now(tz=UTC),
            horizons=horizons,
            recent_samples=recent_samples[:recent_limit],
        )

    def _build_samples(
        self,
        *,
        ai_history: list[AISignalSnapshotRecord],
        candle_history: list[MarketCandleSnapshotRecord],
    ) -> dict[EvaluationHorizon, list[AIOutcomeSample]]:
        """Build evaluated outcome samples across supported horizons."""

        samples_by_horizon: dict[EvaluationHorizon, list[AIOutcomeSample]] = {
            "5m": [],
            "15m": [],
            "1h": [],
        }
        candle_close_times = [candle.close_time for candle in candle_history]
        for snapshot in ai_history:
            for horizon, delta in HORIZON_WINDOWS:
                future_candle = self._find_future_candle(
                    candle_history=candle_history,
                    candle_close_times=candle_close_times,
                    target_time=snapshot.timestamp + delta,
                )
                if future_candle is None:
                    continue
                samples_by_horizon[horizon].append(
                    self._build_sample(
                        snapshot=snapshot,
                        future_candle=future_candle,
                        horizon=horizon,
                    )
                )
        return samples_by_horizon

    def _find_future_candle(
        self,
        *,
        candle_history: list[MarketCandleSnapshotRecord],
        candle_close_times: list[datetime],
        target_time: datetime,
    ) -> MarketCandleSnapshotRecord | None:
        """Return the first persisted candle closing at or after a target time."""

        index = bisect_left(candle_close_times, target_time)
        if index >= len(candle_history):
            return None
        return candle_history[index]

    def _build_sample(
        self,
        *,
        snapshot: AISignalSnapshotRecord,
        future_candle: MarketCandleSnapshotRecord,
        horizon: EvaluationHorizon,
    ) -> AIOutcomeSample:
        """Build one evaluated AI snapshot sample."""

        baseline_close = snapshot.feature_summary.close_price
        return_pct = Decimal("0")
        if baseline_close > Decimal("0"):
            return_pct = (future_candle.close_price - baseline_close) / baseline_close
        observed_direction = _classify_direction(return_pct)
        directional_correct = snapshot.bias == observed_direction
        false_positive = (snapshot.entry_signal or snapshot.exit_signal) and not directional_correct
        false_reversal = (
            (snapshot.bias == "bullish" and observed_direction == "bearish")
            or (snapshot.bias == "bearish" and observed_direction == "bullish")
        )
        return AIOutcomeSample(
            symbol=snapshot.symbol,
            snapshot_time=snapshot.timestamp,
            horizon=horizon,
            bias=snapshot.bias,
            confidence=snapshot.confidence,
            entry_signal=snapshot.entry_signal,
            exit_signal=snapshot.exit_signal,
            suggested_action=snapshot.suggested_action,
            baseline_close=baseline_close,
            future_close=future_candle.close_price,
            return_pct=return_pct,
            observed_direction=observed_direction,
            directional_correct=directional_correct,
            false_positive=false_positive,
            false_reversal=false_reversal,
        )

    def _build_summary(
        self,
        horizon: EvaluationHorizon,
        samples: list[AIOutcomeSample],
    ) -> AIOutcomeSummary:
        """Aggregate evaluated samples into horizon-level metrics."""

        sample_size = len(samples)
        if sample_size == 0:
            return AIOutcomeSummary(
                horizon=horizon,
                sample_size=0,
                directional_accuracy_pct=Decimal("0"),
                confidence_calibration_pct=Decimal("0"),
                false_positive_count=0,
                false_positive_rate_pct=Decimal("0"),
                false_reversal_count=0,
                false_reversal_rate_pct=Decimal("0"),
            )

        correct_count = sum(1 for sample in samples if sample.directional_correct)
        false_positive_count = sum(1 for sample in samples if sample.false_positive)
        false_reversal_count = sum(1 for sample in samples if sample.false_reversal)
        total_calibration_error = sum(
            abs((Decimal(sample.confidence) / Decimal("100")) - (Decimal("1") if sample.directional_correct else Decimal("0")))
            for sample in samples
        )
        average_calibration_error = total_calibration_error / Decimal(sample_size)
        calibration_score = max(Decimal("0"), Decimal("1") - average_calibration_error)
        return AIOutcomeSummary(
            horizon=horizon,
            sample_size=sample_size,
            directional_accuracy_pct=_round_percent(Decimal(correct_count) / Decimal(sample_size)),
            confidence_calibration_pct=_round_percent(calibration_score),
            false_positive_count=false_positive_count,
            false_positive_rate_pct=_round_percent(Decimal(false_positive_count) / Decimal(sample_size)),
            false_reversal_count=false_reversal_count,
            false_reversal_rate_pct=_round_percent(Decimal(false_reversal_count) / Decimal(sample_size)),
        )
