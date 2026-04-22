"""Multi-horizon pattern analysis service."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.analysis.pattern_summary import (
    PatternAnalysisSnapshot,
    PatternPricePoint,
    empty_pattern_snapshot,
)
from app.analysis.range_behavior import (
    breakout_tendency,
    max_drawdown_pct,
    move_counts,
    move_ratio_pct,
    net_return_pct,
    overall_direction,
    realized_volatility_pct,
    reversal_tendency,
    trend_character,
)


SUPPORTED_HORIZONS: dict[str, int] = {
    "1d": 1,
    "3d": 3,
    "7d": 7,
    "14d": 14,
    "30d": 30,
}


class HorizonPatternAnalysisService:
    """Build pattern-analysis summaries for user-selected horizons."""

    def analyze(
        self,
        *,
        symbol: str,
        horizon: str,
        points: Sequence[PatternPricePoint],
        runtime_active: bool,
    ) -> PatternAnalysisSnapshot:
        """Analyze one selected symbol over one selected horizon."""

        normalized_horizon = normalize_horizon(horizon)
        required_days = SUPPORTED_HORIZONS[normalized_horizon]
        if len(points) < 2:
            return empty_pattern_snapshot(
                symbol=symbol,
                horizon=normalized_horizon,
                data_state="waiting_for_history" if runtime_active else "waiting_for_runtime",
                status_message=(
                    f"Pattern analysis for {symbol} needs more closed-candle history for the selected {normalized_horizon.upper()} horizon."
                ),
            )

        sorted_points = sorted(points, key=lambda item: item.timestamp)
        latest_time = sorted_points[-1].timestamp
        cutoff = latest_time - timedelta(days=required_days)
        horizon_points = [point for point in sorted_points if point.timestamp >= cutoff]
        if len(horizon_points) < 2:
            return empty_pattern_snapshot(
                symbol=symbol,
                horizon=normalized_horizon,
                data_state="waiting_for_history" if runtime_active else "waiting_for_runtime",
                status_message=(
                    f"Pattern analysis for {symbol} does not yet cover enough data for {normalized_horizon.upper()}."
                ),
            )

        actual_span = max(horizon_points[-1].timestamp - horizon_points[0].timestamp, timedelta(0))
        requested_span = timedelta(days=required_days)
        coverage_ratio = min(
            Decimal("100"),
            (Decimal(actual_span.total_seconds()) / Decimal(requested_span.total_seconds())) * Decimal("100")
            if requested_span.total_seconds() > 0
            else Decimal("0"),
        )
        partial_coverage = coverage_ratio < Decimal("90")

        direction = overall_direction(horizon_points)
        horizon_return = net_return_pct(horizon_points)
        up_moves, down_moves, flat_moves = move_counts(horizon_points)
        total_moves = up_moves + down_moves + flat_moves
        volatility = realized_volatility_pct(horizon_points)
        drawdown = max_drawdown_pct(horizon_points)
        trend_state = trend_character(horizon_points)
        breakout_state = breakout_tendency(
            direction=direction,
            horizon_return_pct=horizon_return,
            volatility_pct=volatility,
            drawdown_pct=drawdown,
        )
        reversal_state = reversal_tendency(
            direction=direction,
            horizon_return_pct=horizon_return,
            drawdown_pct=drawdown,
            trend_state=trend_state,
        )

        return PatternAnalysisSnapshot(
            symbol=symbol,
            horizon=normalized_horizon,
            generated_at=datetime.now(tz=UTC),
            data_state="waiting_for_history" if partial_coverage else "ready",
            status_message=(
                f"Pattern analysis for {symbol} covers only about {coverage_ratio.quantize(Decimal('1'))}% of the requested {normalized_horizon.upper()} window."
                if partial_coverage
                else f"Pattern analysis is ready for {symbol} over {normalized_horizon.upper()}."
            ),
            coverage_start=horizon_points[0].timestamp,
            coverage_end=horizon_points[-1].timestamp,
            coverage_ratio_pct=coverage_ratio,
            partial_coverage=partial_coverage,
            overall_direction=direction,
            net_return_pct=horizon_return,
            up_moves=up_moves,
            down_moves=down_moves,
            flat_moves=flat_moves,
            up_move_ratio_pct=move_ratio_pct(up_moves, total_moves),
            down_move_ratio_pct=move_ratio_pct(down_moves, total_moves),
            realized_volatility_pct=volatility,
            max_drawdown_pct=drawdown,
            trend_character=trend_state,
            breakout_tendency=breakout_state,
            reversal_tendency=reversal_state,
            explanation=_build_explanation(
                symbol=symbol,
                horizon=normalized_horizon,
                direction=direction,
                horizon_return=horizon_return,
                up_moves=up_moves,
                down_moves=down_moves,
                volatility=volatility,
                drawdown=drawdown,
                trend_state=trend_state,
                breakout_state=breakout_state,
                reversal_state=reversal_state,
                partial_coverage=partial_coverage,
            ),
        )


def normalize_horizon(horizon: str) -> str:
    """Normalize and validate a horizon string."""

    normalized = horizon.strip().lower()
    if normalized not in SUPPORTED_HORIZONS:
        raise ValueError(f"Unsupported horizon '{horizon}'.")
    return normalized


def merge_pattern_points(
    *,
    persisted_points: Sequence[PatternPricePoint],
    live_points: Sequence[PatternPricePoint],
) -> list[PatternPricePoint]:
    """Merge persisted and live close-price points by timestamp."""

    merged: dict[datetime, PatternPricePoint] = {}
    for point in persisted_points:
        merged[point.timestamp] = point
    for point in live_points:
        merged[point.timestamp] = point
    return [merged[timestamp] for timestamp in sorted(merged)]


def _build_explanation(
    *,
    symbol: str,
    horizon: str,
    direction: str | None,
    horizon_return: Decimal | None,
    up_moves: int,
    down_moves: int,
    volatility: Decimal | None,
    drawdown: Decimal | None,
    trend_state: str | None,
    breakout_state: str | None,
    reversal_state: str | None,
    partial_coverage: bool,
) -> str | None:
    """Build a concise human-readable pattern summary."""

    if direction is None or horizon_return is None:
        return None
    parts = [
        f"Over the selected {horizon.upper()} horizon, {symbol} behaved {direction} with a net return of {horizon_return.quantize(Decimal('0.01'))}%.",
        f"Up moves outnumbered down moves {up_moves} to {down_moves}." if up_moves != down_moves else f"Up and down moves were balanced at {up_moves} each.",
    ]
    if volatility is not None:
        parts.append(f"Realized volatility was about {volatility.quantize(Decimal('0.01'))}%.")
    if drawdown is not None:
        parts.append(f"Max drawdown over the window was {drawdown.quantize(Decimal('0.01'))}%.")
    if trend_state is not None:
        parts.append(f"The path looked {trend_state}.")
    if breakout_state is not None:
        parts.append(f"Overall behavior appears {breakout_state.replace('_', ' ')}.")
    if reversal_state is not None:
        parts.append(f"Reversal tendency is {reversal_state}.")
    if partial_coverage:
        parts.append("Coverage is still partial, so this horizon read is incomplete.")
    return " ".join(parts)
