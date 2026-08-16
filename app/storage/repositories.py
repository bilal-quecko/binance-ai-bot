"""SQLite repository helpers for paper-mode persistence."""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Iterator
from uuid import uuid4

from app.ai.models import AISignalSnapshot
from app.market_data.candles import Candle
from app.paper.models import FillResult, Position
from app.risk.models import RiskDecision
from app.storage.db import create_db_connection
from app.storage.models import (
    AISignalFeatureSummaryRecord,
    AISignalSnapshotRecord,
    ContinuousIntelligenceCandidateRecord,
    ContinuousIntelligenceCycleRecord,
    ContinuousIntelligenceStateRecord,
    DailyPnlRecord,
    DrawdownPoint,
    DrawdownSummary,
    EquityHistoryPoint,
    FillRecord,
    FuturesPaperFillRecord,
    FuturesPaperPositionRecord,
    HistoricalCandleRecord,
    MarketCandleSnapshotRecord,
    PaperBrokerStateRecord,
    PaperSessionRunRecord,
    PnlHistoryPoint,
    PnlSnapshotRecord,
    PositionSnapshotRecord,
    ProfileTuningSetRecord,
    RuntimeSessionRecord,
    ScannerCandidatePriceRecord,
    ScannerCandidateRecord,
    ScannerRunRecord,
    RunnerEventRecord,
    ScannerValidationOutcomeRecord,
    ScannerValidationSnapshotRecord,
    SignalOutcomeRecord,
    SignalOutcomeSnapshotRecord,
    SignalTimingBaselineRecord,
    SignalValidationSnapshotRecord,
    SymbolAnalysisCacheRecord,
    SymbolBackfillJobRecord,
    TradeRecord,
)


LOGGER = logging.getLogger(__name__)


def _decimal(value: Any) -> Decimal:
    """Convert a stored numeric value into Decimal."""

    return Decimal(str(value))


def _safe_datetime(value: Any) -> datetime | None:
    """Convert an ISO string into datetime, returning ``None`` when invalid."""

    if value in {None, ""}:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _parse_reason_codes(value: str) -> tuple[str, ...]:
    """Parse persisted reason codes from JSON."""

    raw = json.loads(value)
    return tuple(str(item) for item in raw)


def _parse_json_tuple(value: str) -> tuple[str, ...]:
    """Parse a persisted JSON string list into a stable tuple."""

    try:
        raw = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return ()
    if not isinstance(raw, list):
        return ()
    return tuple(str(item) for item in raw)


def _parse_ai_feature_summary(value: str) -> AISignalFeatureSummaryRecord:
    """Parse a compact persisted AI feature summary."""

    try:
        raw = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return _empty_ai_feature_summary()
    return AISignalFeatureSummaryRecord(
        candle_count=int(raw.get("candle_count", 0)),
        close_price=_decimal(raw.get("close_price", "0")),
        volatility_pct=_decimal(raw["volatility_pct"]) if raw.get("volatility_pct") is not None else None,
        momentum=_decimal(raw["momentum"]) if raw.get("momentum") is not None else None,
        volume_change_pct=(
            _decimal(raw["volume_change_pct"]) if raw.get("volume_change_pct") is not None else None
        ),
        volume_spike_ratio=(
            _decimal(raw["volume_spike_ratio"]) if raw.get("volume_spike_ratio") is not None else None
        ),
        spread_ratio=_decimal(raw["spread_ratio"]) if raw.get("spread_ratio") is not None else None,
        microstructure_healthy=bool(raw.get("microstructure_healthy", False)),
        regime=str(raw["regime"]) if raw.get("regime") is not None else None,
        noise_level=str(raw["noise_level"]) if raw.get("noise_level") is not None else None,
        abstain=bool(raw.get("abstain", False)),
        low_confidence=bool(raw.get("low_confidence", False)),
        confirmation_needed=bool(raw.get("confirmation_needed", False)),
        preferred_horizon=str(raw["preferred_horizon"]) if raw.get("preferred_horizon") is not None else None,
        momentum_persistence=(
            _decimal(raw["momentum_persistence"]) if raw.get("momentum_persistence") is not None else None
        ),
        direction_flip_rate=(
            _decimal(raw["direction_flip_rate"]) if raw.get("direction_flip_rate") is not None else None
        ),
        structure_quality=(
            _decimal(raw["structure_quality"]) if raw.get("structure_quality") is not None else None
        ),
        recent_false_positive_rate_5m=(
            _decimal(raw["recent_false_positive_rate_5m"])
            if raw.get("recent_false_positive_rate_5m") is not None
            else None
        ),
        horizons=raw.get("horizons") if isinstance(raw.get("horizons"), dict) else None,
        weakening_factors=tuple(str(item) for item in raw.get("weakening_factors", [])),
    )


def _empty_ai_feature_summary() -> AISignalFeatureSummaryRecord:
    """Return a neutral compact AI feature summary."""

    return AISignalFeatureSummaryRecord(
        candle_count=0,
        close_price=Decimal("0"),
        volatility_pct=None,
        momentum=None,
        volume_change_pct=None,
        volume_spike_ratio=None,
        spread_ratio=None,
        microstructure_healthy=False,
        regime=None,
        noise_level=None,
        abstain=False,
        low_confidence=False,
        confirmation_needed=False,
        preferred_horizon=None,
        momentum_persistence=None,
        direction_flip_rate=None,
        structure_quality=None,
        recent_false_positive_rate_5m=None,
        horizons=None,
        weakening_factors=(),
    )


def _signal_validation_snapshot_from_row(row: sqlite3.Row) -> SignalValidationSnapshotRecord:
    """Convert a SQLite row into a signal-validation snapshot record."""

    return SignalValidationSnapshotRecord(
        id=int(row["id"]),
        symbol=row["symbol"],
        timestamp=datetime.fromisoformat(row["snapshot_time"]),
        price=_decimal(row["price"]),
        final_action=row["final_action"],
        fusion_final_signal=row["fusion_final_signal"],
        confidence=int(row["confidence"]),
        expected_edge_pct=_decimal(row["expected_edge_pct"]) if row["expected_edge_pct"] is not None else None,
        estimated_cost_pct=_decimal(row["estimated_cost_pct"]) if row["estimated_cost_pct"] is not None else None,
        risk_grade=row["risk_grade"],
        preferred_horizon=row["preferred_horizon"],
        technical_score=_decimal(row["technical_score"]) if row["technical_score"] is not None else None,
        technical_context_json=row["technical_context_json"],
        sentiment_score=_decimal(row["sentiment_score"]) if row["sentiment_score"] is not None else None,
        sentiment_context_json=row["sentiment_context_json"],
        pattern_score=_decimal(row["pattern_score"]) if row["pattern_score"] is not None else None,
        pattern_context_json=row["pattern_context_json"],
        ai_context_json=row["ai_context_json"],
        top_reasons=_parse_json_tuple(row["top_reasons_json"]),
        warnings=_parse_json_tuple(row["warnings_json"]),
        invalidation_hint=row["invalidation_hint"],
        trade_opened=bool(row["trade_opened"]),
        signal_ignored_or_blocked=bool(row["signal_ignored_or_blocked"]),
        blocker_reasons=_parse_json_tuple(row["blocker_reasons_json"]),
        regime_label=row["regime_label"],
    )


def _scanner_validation_snapshot_from_row(row: sqlite3.Row) -> ScannerValidationSnapshotRecord:
    """Convert a SQLite row into a scanner-validation snapshot record."""

    return ScannerValidationSnapshotRecord(
        id=int(row["id"]),
        scan_id=row["scan_id"],
        symbol=row["symbol"],
        direction=row["direction"],
        price_at_scan=_decimal(row["price_at_scan"]) if row["price_at_scan"] is not None else None,
        opportunity_score=int(row["opportunity_score"]),
        confidence=int(row["confidence"]),
        horizon=row["horizon"],
        risk_grade=row["risk_grade"],
        trend_score=int(row["trend_score"]),
        momentum_score=int(row["momentum_score"]),
        volatility_quality_score=int(row["volatility_quality_score"]),
        liquidity_score=int(row["liquidity_score"]),
        risk_score=int(row["risk_score"]),
        direction_score=int(row["direction_score"]),
        validation_score=int(row["validation_score"]) if row["validation_score"] is not None else None,
        evidence_strength=row["evidence_strength"],
        stop_loss=_decimal(row["stop_loss"]) if row["stop_loss"] is not None else None,
        take_profit=_decimal(row["take_profit"]) if row["take_profit"] is not None else None,
        timestamp=datetime.fromisoformat(row["snapshot_time"]),
        rank_position=int(row["rank_position"]),
        candidate_group=row["candidate_group"],
        regime_label=row["regime_label"],
        data_source=row["data_source"] if "data_source" in row.keys() else None,
    )


def _scanner_validation_outcome_from_row(row: sqlite3.Row) -> ScannerValidationOutcomeRecord:
    """Convert a SQLite row into a scanner-validation outcome record."""

    return ScannerValidationOutcomeRecord(
        id=int(row["id"]),
        snapshot_id=int(row["snapshot_id"]),
        horizon=row["horizon"],
        future_price=_decimal(row["future_price"]) if row["future_price"] is not None else None,
        gross_return_pct=(
            _decimal(row["gross_return_pct"]) if row["gross_return_pct"] is not None else None
        ),
        estimated_fee_pct=_decimal(row["estimated_fee_pct"]),
        estimated_slippage_pct=_decimal(row["estimated_slippage_pct"]),
        net_return_pct=_decimal(row["net_return_pct"]) if row["net_return_pct"] is not None else None,
        direction_correct=bool(row["direction_correct"]) if row["direction_correct"] is not None else None,
        max_favorable_move_pct=(
            _decimal(row["max_favorable_move_pct"])
            if row["max_favorable_move_pct"] is not None
            else None
        ),
        max_adverse_move_pct=(
            _decimal(row["max_adverse_move_pct"]) if row["max_adverse_move_pct"] is not None else None
        ),
        take_profit_hit=bool(row["take_profit_hit"]),
        stop_loss_hit=bool(row["stop_loss_hit"]),
        first_exit=row["first_exit"],
        outcome_state=row["outcome_state"],
        evaluated_at=datetime.fromisoformat(row["evaluated_at"]),
    )


def _scanner_run_from_row(row: sqlite3.Row) -> ScannerRunRecord:
    """Convert a SQLite row into scanner-run metadata."""

    return ScannerRunRecord(
        id=row["id"],
        generated_at=datetime.fromisoformat(row["generated_at"]),
        quote_asset=row["quote_asset"],
        horizon=row["horizon"],
        max_symbols=int(row["max_symbols"]),
        min_opportunity_score=int(row["min_opportunity_score"]),
        scan_state=row["scan_state"],
        scanned_count=int(row["scanned_count"]),
        failed_symbols_json=row["failed_symbols_json"],
        warnings_json=row["warnings_json"],
        result_json=row["result_json"] if "result_json" in row.keys() else None,
        candidate_count=int(row["candidate_count"]) if "candidate_count" in row.keys() else 0,
    )


def _scanner_candidate_from_row(row: sqlite3.Row) -> ScannerCandidateRecord:
    """Convert a SQLite row into a scanner candidate record."""

    return ScannerCandidateRecord(
        id=row["id"],
        scanner_run_id=row["scanner_run_id"],
        symbol=row["symbol"],
        direction=row["direction"],
        opportunity_score=int(row["opportunity_score"]),
        confidence=int(row["confidence"]),
        evidence_strength=row["evidence_strength"],
        current_price=_decimal(row["current_price"]) if row["current_price"] is not None else None,
        entry_zone=row["entry_zone"],
        stop_loss=_decimal(row["stop_loss"]) if row["stop_loss"] is not None else None,
        take_profit=_decimal(row["take_profit"]) if row["take_profit"] is not None else None,
        risk_grade=row["risk_grade"],
        regime=row["regime"],
        reason=row["reason"],
        warnings_json=row["warnings_json"],
        timestamp=datetime.fromisoformat(row["timestamp"]),
    )


def _signal_outcome_snapshot_from_row(row: sqlite3.Row) -> SignalOutcomeSnapshotRecord:
    """Convert a SQLite row into a post-signal snapshot record."""

    return SignalOutcomeSnapshotRecord(
        id=row["id"],
        symbol=row["symbol"],
        timestamp=datetime.fromisoformat(row["snapshot_time"]),
        source=row["source"],
        signal_type=row["signal_type"],
        confidence=int(row["confidence"]),
        entry_price=_decimal(row["entry_price"]) if row["entry_price"] is not None else None,
        liquidity_bias=row["liquidity_bias"],
        sweep_risk=row["sweep_risk"],
        nearest_liquidity_above=(
            _decimal(row["nearest_liquidity_above"]) if row["nearest_liquidity_above"] is not None else None
        ),
        nearest_liquidity_below=(
            _decimal(row["nearest_liquidity_below"]) if row["nearest_liquidity_below"] is not None else None
        ),
        funding_rate=_decimal(row["funding_rate"]) if row["funding_rate"] is not None else None,
        open_interest=_decimal(row["open_interest"]) if row["open_interest"] is not None else None,
        notes=row["notes"],
        heatmap_liquidity_above=(
            _decimal(row["heatmap_liquidity_above"]) if row["heatmap_liquidity_above"] is not None else None
        ),
        heatmap_liquidity_below=(
            _decimal(row["heatmap_liquidity_below"]) if row["heatmap_liquidity_below"] is not None else None
        ),
        heatmap_intensity_score=(
            int(row["heatmap_intensity_score"]) if row["heatmap_intensity_score"] is not None else None
        ),
        heatmap_bias=row["heatmap_bias"],
        base_signal_type=row["base_signal_type"],
        heatmap_signal_type=row["heatmap_signal_type"],
        base_confidence=int(row["base_confidence"]) if row["base_confidence"] is not None else None,
        heatmap_confidence=int(row["heatmap_confidence"]) if row["heatmap_confidence"] is not None else None,
        heatmap_alignment=row["heatmap_alignment"],
        heatmap_explanation=row["heatmap_explanation"],
        heatmap_provider=row["heatmap_provider"],
        heatmap_data_quality=row["heatmap_data_quality"],
        heatmap_is_real_data=bool(row["heatmap_is_real_data"]) if row["heatmap_is_real_data"] is not None else None,
        heatmap_provider_status=row["heatmap_provider_status"],
        liquidation_pressure=row["liquidation_pressure"],
        liquidation_imbalance=(
            _decimal(row["liquidation_imbalance"]) if row["liquidation_imbalance"] is not None else None
        ),
    )


def _signal_outcome_from_row(row: sqlite3.Row) -> SignalOutcomeRecord:
    """Convert a SQLite row into a post-signal outcome record."""

    return SignalOutcomeRecord(
        id=int(row["id"]),
        signal_id=row["signal_id"],
        horizon=row["horizon"],
        future_price=_decimal(row["future_price"]) if row["future_price"] is not None else None,
        price_change_percent=(
            _decimal(row["price_change_percent"]) if row["price_change_percent"] is not None else None
        ),
        max_upside_percent=_decimal(row["max_upside_percent"]) if row["max_upside_percent"] is not None else None,
        max_downside_percent=(
            _decimal(row["max_downside_percent"]) if row["max_downside_percent"] is not None else None
        ),
        did_price_hit_tp=bool(row["did_price_hit_tp"]),
        did_price_hit_sl=bool(row["did_price_hit_sl"]),
        direction_correct=bool(row["direction_correct"]) if row["direction_correct"] is not None else None,
        volatility_range=_decimal(row["volatility_range"]) if row["volatility_range"] is not None else None,
        first_hit=row["first_hit"],
        time_to_hit_seconds=int(row["time_to_hit_seconds"]) if row["time_to_hit_seconds"] is not None else None,
        sweep_direction_actual=row["sweep_direction_actual"],
        sweep_prediction_correct=(
            bool(row["sweep_prediction_correct"]) if row["sweep_prediction_correct"] is not None else None
        ),
        outcome_state=row["outcome_state"],
        evaluated_at=datetime.fromisoformat(row["evaluated_at"]),
        base_signal_correct=bool(row["base_signal_correct"]) if row["base_signal_correct"] is not None else None,
        heatmap_signal_correct=(
            bool(row["heatmap_signal_correct"]) if row["heatmap_signal_correct"] is not None else None
        ),
        did_heatmap_improve_result=(
            bool(row["did_heatmap_improve_result"]) if row["did_heatmap_improve_result"] is not None else None
        ),
        did_heatmap_reduce_loss=(
            bool(row["did_heatmap_reduce_loss"]) if row["did_heatmap_reduce_loss"] is not None else None
        ),
        predicted_sweep_direction=row["predicted_sweep_direction"],
        actual_sweep_direction=row["actual_sweep_direction"],
    )


def _signal_timing_baseline_from_row(row: sqlite3.Row) -> SignalTimingBaselineRecord:
    """Convert a SQLite row into a signal timing baseline record."""

    def optional_decimal(column: str) -> Decimal | None:
        return _decimal(row[column]) if row[column] is not None else None

    return SignalTimingBaselineRecord(
        id=int(row["id"]),
        signal_id=row["signal_id"],
        horizon=row["horizon"],
        symbol=row["symbol"],
        source=row["source"],
        direction=row["direction"],
        signal_time=datetime.fromisoformat(row["signal_time"]),
        setup_start_time=_safe_datetime(row["setup_start_time"]),
        setup_start_price=optional_decimal("setup_start_price"),
        activation_price=optional_decimal("activation_price"),
        recent_swing_low=optional_decimal("recent_swing_low"),
        recent_swing_high=optional_decimal("recent_swing_high"),
        horizon_end_price=optional_decimal("horizon_end_price"),
        max_favorable_price=optional_decimal("max_favorable_price"),
        max_adverse_price=optional_decimal("max_adverse_price"),
        move_before_signal_pct=optional_decimal("move_before_signal_pct"),
        move_after_signal_pct=optional_decimal("move_after_signal_pct"),
        max_favorable_excursion_pct=optional_decimal("max_favorable_excursion_pct"),
        max_adverse_excursion_pct=optional_decimal("max_adverse_excursion_pct"),
        full_move_pct=optional_decimal("full_move_pct"),
        move_already_consumed_pct=optional_decimal("move_already_consumed_pct"),
        move_capture_ratio_pct=optional_decimal("move_capture_ratio_pct"),
        entry_efficiency_pct=optional_decimal("entry_efficiency_pct"),
        pre_move_lead_time_seconds=(
            int(row["pre_move_lead_time_seconds"])
            if row["pre_move_lead_time_seconds"] is not None
            else None
        ),
        signal_to_entry_latency_seconds=(
            int(row["signal_to_entry_latency_seconds"])
            if row["signal_to_entry_latency_seconds"] is not None
            else None
        ),
        time_to_target_seconds=(
            int(row["time_to_target_seconds"]) if row["time_to_target_seconds"] is not None else None
        ),
        time_to_stop_seconds=(
            int(row["time_to_stop_seconds"]) if row["time_to_stop_seconds"] is not None else None
        ),
        expiry_seconds=int(row["expiry_seconds"]),
        net_return_after_costs_pct=optional_decimal("net_return_after_costs_pct"),
        estimated_round_trip_cost_pct=_decimal(row["estimated_round_trip_cost_pct"]),
        realized_volatility_pct=optional_decimal("realized_volatility_pct"),
        regime_label=row["regime_label"],
        liquidity_context=row["liquidity_context"],
        classification=row["classification"],
        classification_reasons=_parse_json_tuple(row["classification_reasons_json"]),
        outcome_state=row["outcome_state"],
        evaluated_at=datetime.fromisoformat(row["evaluated_at"]),
    )


def _continuous_intelligence_state_from_row(
    row: sqlite3.Row,
) -> ContinuousIntelligenceStateRecord:
    return ContinuousIntelligenceStateRecord(
        enabled=bool(row["enabled"]),
        status=row["status"],
        cycle_id=row["cycle_id"],
        started_at=_safe_datetime(row["started_at"]),
        last_cycle_started_at=_safe_datetime(row["last_cycle_started_at"]),
        last_cycle_completed_at=_safe_datetime(row["last_cycle_completed_at"]),
        last_full_universe_pass_at=_safe_datetime(row["last_full_universe_pass_at"]),
        last_universe_refresh_at=_safe_datetime(row["last_universe_refresh_at"]),
        last_websocket_event_at=_safe_datetime(row["last_websocket_event_at"]),
        next_cycle_at=_safe_datetime(row["next_cycle_at"]),
        last_error=row["last_error"],
        universe_source=row["universe_source"],
        total_symbols=int(row["total_symbols"]),
        fast_screened_symbols=int(row["fast_screened_symbols"]),
        deep_analyzed_symbols=int(row["deep_analyzed_symbols"]),
        deep_queue_depth=int(row["deep_queue_depth"]),
        successful_cycles=int(row["successful_cycles"]),
        failed_cycles=int(row["failed_cycles"]),
        consecutive_failures=int(row["consecutive_failures"]),
        config_json=row["config_json"],
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def _continuous_intelligence_candidate_from_row(
    row: sqlite3.Row,
) -> ContinuousIntelligenceCandidateRecord:
    return ContinuousIntelligenceCandidateRecord(
        market=row["market"],
        symbol=row["symbol"],
        stage=row["stage"],
        fast_score=int(row["fast_score"]),
        deep_score=int(row["deep_score"]) if row["deep_score"] is not None else None,
        direction_hint=row["direction_hint"],
        current_price=_decimal(row["current_price"]) if row["current_price"] is not None else None,
        triggers=_parse_json_tuple(row["triggers_json"]),
        metrics_json=row["metrics_json"],
        reasons=_parse_json_tuple(row["reasons_json"]),
        warnings=_parse_json_tuple(row["warnings_json"]),
        screened_at=datetime.fromisoformat(row["screened_at"]),
        deep_analyzed_at=_safe_datetime(row["deep_analyzed_at"]),
        data_source=row["data_source"],
    )


def _continuous_intelligence_cycle_from_row(
    row: sqlite3.Row,
) -> ContinuousIntelligenceCycleRecord:
    return ContinuousIntelligenceCycleRecord(
        cycle_id=row["cycle_id"],
        started_at=datetime.fromisoformat(row["started_at"]),
        completed_at=_safe_datetime(row["completed_at"]),
        status=row["status"],
        universe_source=row["universe_source"],
        total_symbols=int(row["total_symbols"]),
        fast_screened_symbols=int(row["fast_screened_symbols"]),
        deep_analyzed_symbols=int(row["deep_analyzed_symbols"]),
        candidate_count=int(row["candidate_count"]),
        failed_symbols=_parse_json_tuple(row["failed_symbols_json"]),
        error_message=row["error_message"],
        duration_ms=int(row["duration_ms"]) if row["duration_ms"] is not None else None,
    )


def _serialize_ai_feature_summary(snapshot: AISignalSnapshot) -> str:
    """Serialize the persisted AI feature summary."""

    feature_vector = snapshot.feature_vector
    payload = {
        "candle_count": feature_vector.candle_count,
        "close_price": str(feature_vector.close_price),
        "volatility_pct": (
            str(feature_vector.volatility_pct) if feature_vector.volatility_pct is not None else None
        ),
        "momentum": str(feature_vector.momentum) if feature_vector.momentum is not None else None,
        "volume_change_pct": (
            str(feature_vector.volume_change_pct) if feature_vector.volume_change_pct is not None else None
        ),
        "volume_spike_ratio": (
            str(feature_vector.volume_spike_ratio) if feature_vector.volume_spike_ratio is not None else None
        ),
        "spread_ratio": str(feature_vector.spread_ratio) if feature_vector.spread_ratio is not None else None,
        "microstructure_healthy": feature_vector.microstructure_healthy,
        "regime": snapshot.regime,
        "noise_level": snapshot.noise_level,
        "abstain": snapshot.abstain,
        "low_confidence": snapshot.low_confidence,
        "confirmation_needed": snapshot.confirmation_needed,
        "preferred_horizon": snapshot.preferred_horizon,
        "momentum_persistence": (
            str(feature_vector.momentum_persistence) if feature_vector.momentum_persistence is not None else None
        ),
        "direction_flip_rate": (
            str(feature_vector.direction_flip_rate) if feature_vector.direction_flip_rate is not None else None
        ),
        "structure_quality": (
            str(feature_vector.structure_quality) if feature_vector.structure_quality is not None else None
        ),
        "recent_false_positive_rate_5m": (
            str(feature_vector.recent_false_positive_rate_5m)
            if feature_vector.recent_false_positive_rate_5m is not None
            else None
        ),
        "weakening_factors": list(snapshot.weakening_factors),
        "horizons": {
            item.horizon: {
                "bias": item.bias,
                "confidence": item.confidence,
                "suggested_action": item.suggested_action,
                "abstain": item.abstain,
                "confirmation_needed": item.confirmation_needed,
                "explanation": item.explanation,
            }
            for item in snapshot.horizon_signals
        },
    }
    return json.dumps(payload, sort_keys=True)


def _ai_signal_materially_changed(
    latest_snapshot: AISignalSnapshotRecord,
    next_snapshot: AISignalSnapshotRecord,
) -> bool:
    """Return whether an AI advisory snapshot materially changed."""

    return (
        latest_snapshot.bias != next_snapshot.bias
        or latest_snapshot.confidence != next_snapshot.confidence
        or latest_snapshot.entry_signal != next_snapshot.entry_signal
        or latest_snapshot.exit_signal != next_snapshot.exit_signal
        or latest_snapshot.suggested_action != next_snapshot.suggested_action
        or latest_snapshot.explanation != next_snapshot.explanation
        or latest_snapshot.feature_summary != next_snapshot.feature_summary
    )


def _start_of_day(value: date) -> datetime:
    """Return the UTC start datetime for a date."""

    return datetime.combine(value, time.min, tzinfo=UTC)


def _next_day(value: date) -> datetime:
    """Return the UTC start datetime for the following date."""

    return _start_of_day(value) + timedelta(days=1)


def _drawdown_pct(drawdown: Decimal, peak_equity: Decimal) -> Decimal:
    """Return drawdown as a fraction of the running peak."""

    if peak_equity <= Decimal("0"):
        return Decimal("0")
    return drawdown / peak_equity


def _is_optional_schema_error(error: sqlite3.Error) -> bool:
    """Return whether a SQLite error points to missing optional AI/evaluation schema."""

    message = str(error).lower()
    return (
        "no such table" in message
        or "no such column" in message
        or "has no column named" in message
    )


class StorageRepository:
    """Paper-mode SQLite repository."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._connection = create_db_connection(database_url)
        self._optional_storage_degraded = False
        self._optional_storage_message: str | None = None

    def close(self) -> None:
        """Close the underlying SQLite connection."""

        self._connection.close()

    def _open_connection(self) -> sqlite3.Connection:
        """Open a fresh SQLite connection for an isolated operation."""

        return create_db_connection(self._database_url)

    @contextmanager
    def _connection_scope(self) -> Iterator[sqlite3.Connection]:
        """Yield a fresh SQLite connection for one repository operation."""

        connection = self._open_connection()
        try:
            yield connection
        finally:
            connection.close()

    @property
    def optional_storage_degraded(self) -> bool:
        """Return whether optional AI/evaluation storage access has degraded."""

        return self._optional_storage_degraded

    @property
    def optional_storage_message(self) -> str | None:
        """Return the latest optional storage degradation message, if any."""

        return self._optional_storage_message

    def _mark_optional_storage_degraded(self, message: str) -> None:
        """Record that optional AI/evaluation storage access degraded."""

        self._optional_storage_degraded = True
        self._optional_storage_message = message

    def record_persistence_warning(self, message: str) -> None:
        """Expose a friendly persistence warning to runtime and API callers."""

        self._mark_optional_storage_degraded(message)

    def clear_all(self) -> None:
        """Delete all persisted paper-session rows."""

        connection = self._open_connection()
        try:
            with connection:
                for table_name in (
                    "trades",
                    "fills",
                    "positions_snapshots",
                    "pnl_snapshots",
                    "runner_events",
                    "futures_paper_events",
                    "futures_paper_fills",
                    "futures_paper_positions",
                    "futures_paper_pnl_snapshots",
                    "ai_signal_snapshots",
                    "market_candle_snapshots",
                    "signal_validation_snapshots",
                    "historical_candles",
                    "futures_historical_candles",
                    "scanner_runs",
                    "scanner_candidates",
                    "scanner_candidate_prices",
                    "symbol_candle_cache",
                    "symbol_analysis_cache",
                    "symbol_backfill_jobs",
                    "scanner_validation_snapshots",
                    "scanner_validation_outcomes",
                    "signal_snapshots",
                    "signal_outcomes",
                    "runtime_session_state",
                    "paper_broker_state",
                    "paper_broker_positions",
                    "profile_tuning_sets",
                    "paper_session_runs",
                ):
                    try:
                        connection.execute(f"DELETE FROM {table_name}")
                    except sqlite3.OperationalError as exc:
                        if not _is_optional_schema_error(exc):
                            raise
                        self._mark_optional_storage_degraded(f"Optional storage table {table_name} is unavailable.")
                        LOGGER.warning("Skipping clear for missing table %s: %s", table_name, exc)
        finally:
            connection.close()

    def upsert_runtime_session_state(
        self,
        *,
        state: str,
        mode: str,
        symbol: str | None,
        session_id: str | None,
        started_at: datetime | None,
        last_event_time: datetime | None,
        last_error: str | None,
        trading_profile: str = "balanced",
        tuning_version_id: str | None = None,
        baseline_tuning_version_id: str | None = None,
    ) -> None:
        """Persist the backend-owned runtime session state."""

        connection = self._open_connection()
        try:
            with connection:
                connection.execute(
                """
                INSERT INTO runtime_session_state (
                    singleton_id, state, mode, trading_profile, symbol, session_id, started_at, last_event_time, last_error,
                    tuning_version_id, baseline_tuning_version_id
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(singleton_id) DO UPDATE SET
                    state = excluded.state,
                    mode = excluded.mode,
                    trading_profile = excluded.trading_profile,
                    symbol = excluded.symbol,
                    session_id = excluded.session_id,
                    started_at = excluded.started_at,
                    last_event_time = excluded.last_event_time,
                    last_error = excluded.last_error,
                    tuning_version_id = excluded.tuning_version_id,
                    baseline_tuning_version_id = excluded.baseline_tuning_version_id
                """,
                (
                    state,
                    mode,
                    trading_profile,
                    symbol,
                    session_id,
                    started_at.isoformat() if started_at is not None else None,
                    last_event_time.isoformat() if last_event_time is not None else None,
                    last_error,
                    tuning_version_id,
                    baseline_tuning_version_id,
                ),
            )
        finally:
            connection.close()

    def get_runtime_session_state(self) -> RuntimeSessionRecord | None:
        """Return the persisted backend-owned runtime session state."""

        with self._connection_scope() as connection:
            row = connection.execute(
                """
                SELECT state, mode, trading_profile, symbol, session_id, started_at, last_event_time, last_error,
                       tuning_version_id, baseline_tuning_version_id
                FROM runtime_session_state
                WHERE singleton_id = 1
                """
            ).fetchone()
        if row is None:
            return None
        return RuntimeSessionRecord(
            state=row["state"],
            mode=row["mode"],
            trading_profile=row["trading_profile"] or "balanced",
            symbol=row["symbol"],
            session_id=row["session_id"],
            started_at=_safe_datetime(row["started_at"]),
            last_event_time=_safe_datetime(row["last_event_time"]),
            last_error=row["last_error"],
            tuning_version_id=row["tuning_version_id"],
            baseline_tuning_version_id=row["baseline_tuning_version_id"],
        )

    def clear_runtime_session_state(self) -> None:
        """Clear any persisted runtime recovery state."""

        connection = self._open_connection()
        try:
            with connection:
                connection.execute("DELETE FROM runtime_session_state")
        finally:
            connection.close()

    def create_profile_tuning_set(
        self,
        *,
        symbol: str | None,
        profile: str,
        config_json: str,
        baseline_config_json: str,
        baseline_version_id: str | None,
        reason: str,
    ) -> ProfileTuningSetRecord:
        """Persist a paper-only tuning set for explicit later application."""

        version_id = f"tune_{uuid4().hex[:12]}"
        created_at = datetime.now(tz=UTC)
        connection = self._open_connection()
        try:
            with connection:
                connection.execute(
                    """
                    UPDATE profile_tuning_sets
                    SET status = 'superseded'
                    WHERE status = 'pending' AND profile = ? AND (
                        (symbol IS NULL AND ? IS NULL) OR symbol = ?
                    )
                    """,
                    (profile, symbol, symbol),
                )
                connection.execute(
                    """
                    INSERT INTO profile_tuning_sets (
                        version_id, symbol, profile, status, config_json, baseline_config_json,
                        created_at, applied_at, baseline_version_id, reason
                    ) VALUES (?, ?, ?, 'pending', ?, ?, ?, NULL, ?, ?)
                    """,
                    (
                        version_id,
                        symbol,
                        profile,
                        config_json,
                        baseline_config_json,
                        created_at.isoformat(),
                        baseline_version_id,
                        reason,
                    ),
                )
        finally:
            connection.close()
        return ProfileTuningSetRecord(
            version_id=version_id,
            symbol=symbol,
            profile=profile,
            status="pending",
            config_json=config_json,
            baseline_config_json=baseline_config_json,
            created_at=created_at,
            applied_at=None,
            baseline_version_id=baseline_version_id,
            reason=reason,
        )

    def get_latest_profile_tuning_set(
        self,
        *,
        symbol: str | None,
        profile: str,
        status: str | None = None,
    ) -> ProfileTuningSetRecord | None:
        """Return the latest persisted tuning set for one symbol/profile scope."""

        query = """
            SELECT version_id, symbol, profile, status, config_json, baseline_config_json,
                   created_at, applied_at, baseline_version_id, reason
            FROM profile_tuning_sets
            WHERE profile = ? AND ((symbol IS NULL AND ? IS NULL) OR symbol = ?)
        """
        params: list[Any] = [profile, symbol, symbol]
        if status is not None:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT 1"
        with self._connection_scope() as connection:
            row = connection.execute(query, tuple(params)).fetchone()
        if row is None:
            return None
        return ProfileTuningSetRecord(
            version_id=row["version_id"],
            symbol=row["symbol"],
            profile=row["profile"],
            status=row["status"],
            config_json=row["config_json"],
            baseline_config_json=row["baseline_config_json"],
            created_at=datetime.fromisoformat(row["created_at"]),
            applied_at=_safe_datetime(row["applied_at"]),
            baseline_version_id=row["baseline_version_id"],
            reason=row["reason"],
        )

    def get_profile_tuning_set_by_version(self, version_id: str) -> ProfileTuningSetRecord | None:
        """Return one persisted tuning set by version id."""

        with self._connection_scope() as connection:
            row = connection.execute(
                """
                SELECT version_id, symbol, profile, status, config_json, baseline_config_json,
                       created_at, applied_at, baseline_version_id, reason
                FROM profile_tuning_sets
                WHERE version_id = ?
                """,
                (version_id,),
            ).fetchone()
        if row is None:
            return None
        return ProfileTuningSetRecord(
            version_id=row["version_id"],
            symbol=row["symbol"],
            profile=row["profile"],
            status=row["status"],
            config_json=row["config_json"],
            baseline_config_json=row["baseline_config_json"],
            created_at=datetime.fromisoformat(row["created_at"]),
            applied_at=_safe_datetime(row["applied_at"]),
            baseline_version_id=row["baseline_version_id"],
            reason=row["reason"],
        )

    def mark_profile_tuning_applied(self, version_id: str, *, applied_at: datetime) -> None:
        """Mark a pending tuning set as applied."""

        connection = self._open_connection()
        try:
            with connection:
                connection.execute(
                    """
                    UPDATE profile_tuning_sets
                    SET status = 'applied', applied_at = ?
                    WHERE version_id = ?
                    """,
                    (applied_at.isoformat(), version_id),
                )
        finally:
            connection.close()

    def start_paper_session_run(
        self,
        *,
        session_id: str,
        symbol: str,
        trading_profile: str,
        tuning_version_id: str | None,
        baseline_tuning_version_id: str | None,
        started_at: datetime,
    ) -> None:
        """Persist one paper session run for later before/after comparison."""

        connection = self._open_connection()
        try:
            with connection:
                connection.execute(
                    """
                    INSERT INTO paper_session_runs (
                        session_id, symbol, trading_profile, tuning_version_id,
                        baseline_tuning_version_id, started_at, ended_at
                    ) VALUES (?, ?, ?, ?, ?, ?, NULL)
                    ON CONFLICT(session_id) DO UPDATE SET
                        symbol = excluded.symbol,
                        trading_profile = excluded.trading_profile,
                        tuning_version_id = excluded.tuning_version_id,
                        baseline_tuning_version_id = excluded.baseline_tuning_version_id,
                        started_at = excluded.started_at
                    """,
                    (
                        session_id,
                        symbol,
                        trading_profile,
                        tuning_version_id,
                        baseline_tuning_version_id,
                        started_at.isoformat(),
                    ),
                )
        finally:
            connection.close()

    def finish_paper_session_run(self, *, session_id: str, ended_at: datetime) -> None:
        """Mark a persisted paper session as finished."""

        connection = self._open_connection()
        try:
            with connection:
                connection.execute(
                    "UPDATE paper_session_runs SET ended_at = ? WHERE session_id = ?",
                    (ended_at.isoformat(), session_id),
                )
        finally:
            connection.close()

    def get_paper_session_runs(
        self,
        *,
        symbol: str | None = None,
        trading_profile: str | None = None,
        tuning_version_id: str | None = None,
        baseline_tuning_version_id: str | None = None,
        session_id: str | None = None,
    ) -> list[PaperSessionRunRecord]:
        """Return persisted paper session runs with optional filters."""

        query = """
            SELECT session_id, symbol, trading_profile, tuning_version_id, baseline_tuning_version_id,
                   started_at, ended_at
            FROM paper_session_runs
            WHERE 1 = 1
        """
        params: list[Any] = []
        if symbol is not None:
            query += " AND symbol = ?"
            params.append(symbol)
        if trading_profile is not None:
            query += " AND trading_profile = ?"
            params.append(trading_profile)
        if tuning_version_id is not None:
            query += " AND tuning_version_id = ?"
            params.append(tuning_version_id)
        if baseline_tuning_version_id is not None:
            query += " AND baseline_tuning_version_id = ?"
            params.append(baseline_tuning_version_id)
        if session_id is not None:
            query += " AND session_id = ?"
            params.append(session_id)
        query += " ORDER BY started_at ASC"
        with self._connection_scope() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [
            PaperSessionRunRecord(
                session_id=row["session_id"],
                symbol=row["symbol"],
                trading_profile=row["trading_profile"],
                tuning_version_id=row["tuning_version_id"],
                baseline_tuning_version_id=row["baseline_tuning_version_id"],
                started_at=datetime.fromisoformat(row["started_at"]),
                ended_at=_safe_datetime(row["ended_at"]),
            )
            for row in rows
        ]

    def upsert_paper_broker_state(
        self,
        *,
        balances: dict[str, Decimal],
        positions: dict[str, Position],
        realized_pnl: Decimal,
        snapshot_time: datetime,
    ) -> None:
        """Persist paper broker balances and open positions for restart recovery."""

        balances_json = json.dumps(
            {asset.upper(): str(balance) for asset, balance in balances.items()},
            sort_keys=True,
        )
        connection = self._open_connection()
        try:
            with connection:
                connection.execute(
                """
                INSERT INTO paper_broker_state (
                    singleton_id, balances_json, realized_pnl, snapshot_time
                ) VALUES (1, ?, ?, ?)
                ON CONFLICT(singleton_id) DO UPDATE SET
                    balances_json = excluded.balances_json,
                    realized_pnl = excluded.realized_pnl,
                    snapshot_time = excluded.snapshot_time
                """,
                (
                    balances_json,
                    str(realized_pnl),
                    snapshot_time.isoformat(),
                ),
            )
                connection.execute("DELETE FROM paper_broker_positions")
                for symbol, position in positions.items():
                    connection.execute(
                    """
                    INSERT INTO paper_broker_positions (
                        symbol, quantity, avg_entry_price, realized_pnl, quote_asset, snapshot_time
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        symbol.upper(),
                        str(position.quantity),
                        str(position.avg_entry_price),
                        str(position.realized_pnl),
                        position.quote_asset,
                        snapshot_time.isoformat(),
                    ),
                )
        finally:
            connection.close()

    def get_paper_broker_state(self) -> PaperBrokerStateRecord | None:
        """Return persisted paper broker recovery state."""

        with self._connection_scope() as connection:
            row = connection.execute(
                """
                SELECT balances_json, realized_pnl, snapshot_time
                FROM paper_broker_state
                WHERE singleton_id = 1
                """
            ).fetchone()
            if row is None:
                return None
            try:
                raw_balances = json.loads(row["balances_json"])
                balances = {
                    str(asset).upper(): _decimal(value)
                    for asset, value in dict(raw_balances).items()
                }
            except (TypeError, ValueError, json.JSONDecodeError):
                LOGGER.warning("Ignoring corrupt persisted paper broker balances during recovery.")
                return None

            snapshot_time = _safe_datetime(row["snapshot_time"])
            if snapshot_time is None:
                LOGGER.warning("Ignoring corrupt persisted paper broker snapshot time during recovery.")
                return None

            position_rows = connection.execute(
                """
                SELECT symbol, quantity, avg_entry_price, realized_pnl, quote_asset, snapshot_time
                FROM paper_broker_positions
                ORDER BY symbol ASC
                """
            ).fetchall()
        positions: list[PositionSnapshotRecord] = []
        for position_row in position_rows:
            position_snapshot_time = _safe_datetime(position_row["snapshot_time"])
            if position_snapshot_time is None:
                LOGGER.warning(
                    "Skipping corrupt persisted paper broker position timestamp for %s.",
                    position_row["symbol"],
                )
                continue
            positions.append(
                PositionSnapshotRecord(
                    symbol=position_row["symbol"],
                    quantity=_decimal(position_row["quantity"]),
                    avg_entry_price=_decimal(position_row["avg_entry_price"]),
                    realized_pnl=_decimal(position_row["realized_pnl"]),
                    quote_asset=position_row["quote_asset"],
                    snapshot_time=position_snapshot_time,
                )
            )
        return PaperBrokerStateRecord(
            balances=balances,
            positions=positions,
            realized_pnl=_decimal(row["realized_pnl"]),
            snapshot_time=snapshot_time,
        )

    def clear_paper_broker_state(self) -> None:
        """Clear persisted paper broker recovery state."""

        connection = self._open_connection()
        try:
            with connection:
                connection.execute("DELETE FROM paper_broker_state")
                connection.execute("DELETE FROM paper_broker_positions")
        finally:
            connection.close()

    def insert_market_candle_snapshot(self, candle: Candle) -> None:
        """Persist a closed candle for later AI outcome validation."""

        if not candle.is_closed:
            return
        try:
            connection = self._open_connection()
            with connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO market_candle_snapshots (
                        symbol, timeframe, open_time, close_time, close_price, event_time
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        candle.symbol.upper(),
                        candle.timeframe,
                        candle.open_time.isoformat(),
                        candle.close_time.isoformat(),
                        str(candle.close),
                        candle.event_time.isoformat(),
                    ),
                )
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Closed-candle outcome storage is unavailable.")
            LOGGER.warning("Skipping market candle snapshot persistence due to schema issue: %s", exc)
        finally:
            if "connection" in locals():
                connection.close()

    def insert_signal_validation_snapshot(self, snapshot: SignalValidationSnapshotRecord) -> int | None:
        """Persist a final fusion/trading-assistant snapshot for later outcome validation."""

        try:
            connection = self._open_connection()
            with connection:
                cursor = connection.execute(
                    """
                    INSERT INTO signal_validation_snapshots (
                        symbol, snapshot_time, price, final_action, fusion_final_signal,
                        confidence, expected_edge_pct, estimated_cost_pct, risk_grade, preferred_horizon,
                        technical_score, technical_context_json, sentiment_score, sentiment_context_json,
                        pattern_score, pattern_context_json, ai_context_json, top_reasons_json, warnings_json,
                        invalidation_hint, trade_opened, signal_ignored_or_blocked, blocker_reasons_json, regime_label
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot.symbol.upper(),
                        snapshot.timestamp.isoformat(),
                        str(snapshot.price),
                        snapshot.final_action,
                        snapshot.fusion_final_signal,
                        snapshot.confidence,
                        str(snapshot.expected_edge_pct) if snapshot.expected_edge_pct is not None else None,
                        str(snapshot.estimated_cost_pct) if snapshot.estimated_cost_pct is not None else None,
                        snapshot.risk_grade,
                        snapshot.preferred_horizon,
                        str(snapshot.technical_score) if snapshot.technical_score is not None else None,
                        snapshot.technical_context_json,
                        str(snapshot.sentiment_score) if snapshot.sentiment_score is not None else None,
                        snapshot.sentiment_context_json,
                        str(snapshot.pattern_score) if snapshot.pattern_score is not None else None,
                        snapshot.pattern_context_json,
                        snapshot.ai_context_json,
                        json.dumps(list(snapshot.top_reasons)),
                        json.dumps(list(snapshot.warnings)),
                        snapshot.invalidation_hint,
                        int(snapshot.trade_opened),
                        int(snapshot.signal_ignored_or_blocked),
                        json.dumps(list(snapshot.blocker_reasons)),
                        snapshot.regime_label,
                    ),
                )
                return int(cursor.lastrowid) if cursor.lastrowid is not None else None
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Signal-validation snapshot storage is unavailable.")
            LOGGER.warning("Skipping signal-validation snapshot persistence due to schema issue: %s", exc)
            return None
        finally:
            if "connection" in locals():
                connection.close()

    def get_signal_validation_snapshots(
        self,
        *,
        symbol: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        action: str | None = None,
        risk_grade: str | None = None,
        confidence_bucket: str | None = None,
    ) -> list[SignalValidationSnapshotRecord]:
        """Return persisted signal snapshots for validation analytics."""

        query = """
            SELECT id, symbol, snapshot_time, price, final_action, fusion_final_signal,
                   confidence, expected_edge_pct, estimated_cost_pct, risk_grade, preferred_horizon,
                   technical_score, technical_context_json, sentiment_score, sentiment_context_json,
                   pattern_score, pattern_context_json, ai_context_json, top_reasons_json, warnings_json,
                   invalidation_hint, trade_opened, signal_ignored_or_blocked, blocker_reasons_json, regime_label
            FROM signal_validation_snapshots
            WHERE 1 = 1
        """
        params: list[Any] = []
        query, params = self._apply_history_filters(
            query=query,
            params=params,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timestamp_column="snapshot_time",
        )
        if action is not None:
            query += " AND final_action = ?"
            params.append(action)
        if risk_grade is not None:
            query += " AND risk_grade = ?"
            params.append(risk_grade)
        if confidence_bucket is not None:
            if confidence_bucket == "low":
                query += " AND confidence < 45"
            elif confidence_bucket == "medium":
                query += " AND confidence >= 45 AND confidence < 70"
            elif confidence_bucket == "high":
                query += " AND confidence >= 70"
        query += " ORDER BY snapshot_time ASC, id ASC"
        try:
            with self._connection_scope() as connection:
                rows = connection.execute(query, tuple(params)).fetchall()
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Signal-validation snapshot storage is unavailable.")
            LOGGER.warning("Failed to read signal-validation snapshots due to schema issue: %s", exc)
            return []
        return [_signal_validation_snapshot_from_row(row) for row in rows]

    def insert_scanner_validation_snapshots(
        self,
        snapshots: list[ScannerValidationSnapshotRecord],
    ) -> int:
        """Persist futures-paper scanner snapshots for later outcome validation."""

        if not snapshots:
            return 0
        try:
            connection = self._open_connection()
            with connection:
                cursor = connection.executemany(
                    """
                    INSERT OR IGNORE INTO scanner_validation_snapshots (
                        scan_id, symbol, direction, price_at_scan, opportunity_score, confidence,
                        horizon, risk_grade, trend_score, momentum_score, volatility_quality_score,
                        liquidity_score, risk_score, direction_score, validation_score, evidence_strength,
                        stop_loss, take_profit, snapshot_time, rank_position, candidate_group, regime_label,
                        data_source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            snapshot.scan_id,
                            snapshot.symbol.upper(),
                            snapshot.direction,
                            str(snapshot.price_at_scan) if snapshot.price_at_scan is not None else None,
                            snapshot.opportunity_score,
                            snapshot.confidence,
                            snapshot.horizon,
                            snapshot.risk_grade,
                            snapshot.trend_score,
                            snapshot.momentum_score,
                            snapshot.volatility_quality_score,
                            snapshot.liquidity_score,
                            snapshot.risk_score,
                            snapshot.direction_score,
                            snapshot.validation_score,
                            snapshot.evidence_strength,
                            str(snapshot.stop_loss) if snapshot.stop_loss is not None else None,
                            str(snapshot.take_profit) if snapshot.take_profit is not None else None,
                            snapshot.timestamp.isoformat(),
                            snapshot.rank_position,
                            snapshot.candidate_group,
                            snapshot.regime_label,
                            snapshot.data_source,
                        )
                        for snapshot in snapshots
                    ],
                )
            return int(cursor.rowcount)
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Scanner-validation snapshot storage is unavailable.")
            LOGGER.warning("Skipping scanner-validation snapshot persistence due to schema issue: %s", exc)
            return 0
        finally:
            if "connection" in locals():
                connection.close()

    def get_scanner_validation_snapshots(
        self,
        *,
        symbol: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        direction: str | None = None,
        min_opportunity_score: int | None = None,
    ) -> list[ScannerValidationSnapshotRecord]:
        """Return persisted futures-paper scanner snapshots."""

        query = """
            SELECT id, scan_id, symbol, direction, price_at_scan, opportunity_score, confidence,
                   horizon, risk_grade, trend_score, momentum_score, volatility_quality_score,
                   liquidity_score, risk_score, direction_score, validation_score, evidence_strength,
                   stop_loss, take_profit, snapshot_time, rank_position, candidate_group, regime_label,
                   data_source
            FROM scanner_validation_snapshots
            WHERE 1 = 1
        """
        params: list[Any] = []
        query, params = self._apply_history_filters(
            query=query,
            params=params,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timestamp_column="snapshot_time",
        )
        if direction is not None:
            query += " AND direction = ?"
            params.append(direction.lower())
        if min_opportunity_score is not None:
            query += " AND opportunity_score >= ?"
            params.append(min_opportunity_score)
        query += " ORDER BY snapshot_time ASC, id ASC"
        try:
            with self._connection_scope() as connection:
                rows = connection.execute(query, tuple(params)).fetchall()
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Scanner-validation snapshot storage is unavailable.")
            LOGGER.warning("Failed to read scanner-validation snapshots due to schema issue: %s", exc)
            return []
        return [_scanner_validation_snapshot_from_row(row) for row in rows]

    def upsert_scanner_validation_outcome(self, outcome: ScannerValidationOutcomeRecord) -> None:
        """Persist or replace a scanner-validation horizon outcome."""

        try:
            connection = self._open_connection()
            with connection:
                connection.execute(
                    """
                    INSERT INTO scanner_validation_outcomes (
                        snapshot_id, horizon, future_price, gross_return_pct, estimated_fee_pct,
                        estimated_slippage_pct, net_return_pct, direction_correct,
                        max_favorable_move_pct, max_adverse_move_pct, take_profit_hit, stop_loss_hit,
                        first_exit, outcome_state, evaluated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(snapshot_id, horizon) DO UPDATE SET
                        future_price = excluded.future_price,
                        gross_return_pct = excluded.gross_return_pct,
                        estimated_fee_pct = excluded.estimated_fee_pct,
                        estimated_slippage_pct = excluded.estimated_slippage_pct,
                        net_return_pct = excluded.net_return_pct,
                        direction_correct = excluded.direction_correct,
                        max_favorable_move_pct = excluded.max_favorable_move_pct,
                        max_adverse_move_pct = excluded.max_adverse_move_pct,
                        take_profit_hit = excluded.take_profit_hit,
                        stop_loss_hit = excluded.stop_loss_hit,
                        first_exit = excluded.first_exit,
                        outcome_state = excluded.outcome_state,
                        evaluated_at = excluded.evaluated_at
                    """,
                    (
                        outcome.snapshot_id,
                        outcome.horizon,
                        str(outcome.future_price) if outcome.future_price is not None else None,
                        str(outcome.gross_return_pct) if outcome.gross_return_pct is not None else None,
                        str(outcome.estimated_fee_pct),
                        str(outcome.estimated_slippage_pct),
                        str(outcome.net_return_pct) if outcome.net_return_pct is not None else None,
                        int(outcome.direction_correct) if outcome.direction_correct is not None else None,
                        (
                            str(outcome.max_favorable_move_pct)
                            if outcome.max_favorable_move_pct is not None
                            else None
                        ),
                        (
                            str(outcome.max_adverse_move_pct)
                            if outcome.max_adverse_move_pct is not None
                            else None
                        ),
                        int(outcome.take_profit_hit),
                        int(outcome.stop_loss_hit),
                        outcome.first_exit,
                        outcome.outcome_state,
                        outcome.evaluated_at.isoformat(),
                    ),
                )
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Scanner-validation outcome storage is unavailable.")
            LOGGER.warning("Skipping scanner-validation outcome persistence due to schema issue: %s", exc)
        finally:
            if "connection" in locals():
                connection.close()

    def get_scanner_validation_outcomes(
        self,
        *,
        snapshot_ids: list[int] | None = None,
        horizon: str | None = None,
    ) -> list[ScannerValidationOutcomeRecord]:
        """Return persisted futures-paper scanner outcomes."""

        if snapshot_ids == []:
            return []

        query = """
            SELECT id, snapshot_id, horizon, future_price, gross_return_pct, estimated_fee_pct,
                   estimated_slippage_pct, net_return_pct, direction_correct, max_favorable_move_pct,
                   max_adverse_move_pct, take_profit_hit, stop_loss_hit, first_exit, outcome_state,
                   evaluated_at
            FROM scanner_validation_outcomes
            WHERE 1 = 1
        """
        params: list[Any] = []
        if snapshot_ids:
            placeholders = ",".join("?" for _ in snapshot_ids)
            query += f" AND snapshot_id IN ({placeholders})"
            params.extend(snapshot_ids)
        if horizon is not None:
            query += " AND horizon = ?"
            params.append(horizon)
        query += " ORDER BY evaluated_at ASC, id ASC"
        try:
            with self._connection_scope() as connection:
                rows = connection.execute(query, tuple(params)).fetchall()
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Scanner-validation outcome storage is unavailable.")
            LOGGER.warning("Failed to read scanner-validation outcomes due to schema issue: %s", exc)
            return []
        return [_scanner_validation_outcome_from_row(row) for row in rows]

    def upsert_scanner_run(self, run: ScannerRunRecord) -> None:
        """Persist scanner run metadata with stable idempotency by run id."""

        try:
            with self._connection_scope() as connection:
                with connection:
                    connection.execute(
                        """
                        INSERT INTO scanner_runs (
                            id, generated_at, quote_asset, horizon, max_symbols,
                            min_opportunity_score, scan_state, scanned_count,
                            failed_symbols_json, warnings_json, result_json, candidate_count
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            generated_at = excluded.generated_at,
                            quote_asset = excluded.quote_asset,
                            horizon = excluded.horizon,
                            max_symbols = excluded.max_symbols,
                            min_opportunity_score = excluded.min_opportunity_score,
                            scan_state = excluded.scan_state,
                            scanned_count = excluded.scanned_count,
                            failed_symbols_json = excluded.failed_symbols_json,
                            warnings_json = excluded.warnings_json,
                            result_json = excluded.result_json,
                            candidate_count = excluded.candidate_count
                        """,
                        (
                            run.id,
                            run.generated_at.isoformat(),
                            run.quote_asset,
                            run.horizon,
                            run.max_symbols,
                            run.min_opportunity_score,
                            run.scan_state,
                            run.scanned_count,
                            run.failed_symbols_json,
                            run.warnings_json,
                            run.result_json,
                            run.candidate_count,
                        ),
                    )
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Scanner run storage is unavailable.")
            LOGGER.warning("Skipping scanner run persistence due to schema issue: %s", exc)

    def get_scanner_runs(self, *, limit: int = 20) -> list[ScannerRunRecord]:
        """Return recent scanner runs."""

        try:
            with self._connection_scope() as connection:
                rows = connection.execute(
                    """
                    SELECT id, generated_at, quote_asset, horizon, max_symbols,
                           min_opportunity_score, scan_state, scanned_count,
                           failed_symbols_json, warnings_json, result_json, candidate_count
                    FROM scanner_runs
                    ORDER BY generated_at DESC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Scanner run storage is unavailable.")
            LOGGER.warning("Failed to read scanner runs due to schema issue: %s", exc)
            return []
        return [_scanner_run_from_row(row) for row in rows]

    def get_latest_successful_scanner_run(
        self,
        *,
        quote_asset: str = "USDT",
        horizon: str | None = None,
    ) -> ScannerRunRecord | None:
        """Return the latest persisted scanner result with usable candidates."""

        query = """
            SELECT id, generated_at, quote_asset, horizon, max_symbols,
                   min_opportunity_score, scan_state, scanned_count,
                   failed_symbols_json, warnings_json, result_json, candidate_count
            FROM scanner_runs
            WHERE quote_asset = ?
              AND result_json IS NOT NULL
              AND candidate_count > 0
              AND scan_state IN ('ready', 'partial', 'insufficient_data')
        """
        params: list[Any] = [quote_asset.upper()]
        if horizon is not None:
            query += " AND horizon = ?"
            params.append(horizon)
        query += " ORDER BY generated_at DESC LIMIT 1"
        try:
            with self._connection_scope() as connection:
                row = connection.execute(query, tuple(params)).fetchone()
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Scanner run storage is unavailable.")
            LOGGER.warning("Failed to read latest scanner run due to schema issue: %s", exc)
            return None
        if row is None:
            return None
        return _scanner_run_from_row(row)

    def upsert_scanner_candidates(self, candidates: list[ScannerCandidateRecord]) -> int:
        """Persist scanner candidates for later review and validation."""

        if not candidates:
            return 0
        try:
            with self._connection_scope() as connection:
                with connection:
                    cursor = connection.executemany(
                        """
                        INSERT INTO scanner_candidates (
                            id, scanner_run_id, symbol, direction, opportunity_score,
                            confidence, evidence_strength, current_price, entry_zone,
                            stop_loss, take_profit, risk_grade, regime, reason,
                            warnings_json, timestamp
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(scanner_run_id, symbol, direction) DO UPDATE SET
                            opportunity_score = excluded.opportunity_score,
                            confidence = excluded.confidence,
                            evidence_strength = excluded.evidence_strength,
                            current_price = excluded.current_price,
                            entry_zone = excluded.entry_zone,
                            stop_loss = excluded.stop_loss,
                            take_profit = excluded.take_profit,
                            risk_grade = excluded.risk_grade,
                            regime = excluded.regime,
                            reason = excluded.reason,
                            warnings_json = excluded.warnings_json,
                            timestamp = excluded.timestamp
                        """,
                        [
                            (
                                candidate.id,
                                candidate.scanner_run_id,
                                candidate.symbol.upper(),
                                candidate.direction,
                                candidate.opportunity_score,
                                candidate.confidence,
                                candidate.evidence_strength,
                                str(candidate.current_price) if candidate.current_price is not None else None,
                                candidate.entry_zone,
                                str(candidate.stop_loss) if candidate.stop_loss is not None else None,
                                str(candidate.take_profit) if candidate.take_profit is not None else None,
                                candidate.risk_grade,
                                candidate.regime,
                                candidate.reason,
                                candidate.warnings_json,
                                candidate.timestamp.isoformat(),
                            )
                            for candidate in candidates
                        ],
                    )
            return int(cursor.rowcount)
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Scanner candidate storage is unavailable.")
            LOGGER.warning("Skipping scanner candidate persistence due to schema issue: %s", exc)
            return 0

    def get_scanner_candidates(
        self,
        *,
        scanner_run_id: str | None = None,
        symbol: str | None = None,
        limit: int = 100,
    ) -> list[ScannerCandidateRecord]:
        """Return persisted scanner candidates."""

        query = """
            SELECT id, scanner_run_id, symbol, direction, opportunity_score, confidence,
                   evidence_strength, current_price, entry_zone, stop_loss, take_profit,
                   risk_grade, regime, reason, warnings_json, timestamp
            FROM scanner_candidates
            WHERE 1 = 1
        """
        params: list[Any] = []
        if scanner_run_id is not None:
            query += " AND scanner_run_id = ?"
            params.append(scanner_run_id)
        if symbol is not None:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        query += " ORDER BY timestamp DESC, opportunity_score DESC LIMIT ?"
        params.append(limit)
        try:
            with self._connection_scope() as connection:
                rows = connection.execute(query, tuple(params)).fetchall()
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Scanner candidate storage is unavailable.")
            LOGGER.warning("Failed to read scanner candidates due to schema issue: %s", exc)
            return []
        return [_scanner_candidate_from_row(row) for row in rows]

    def upsert_scanner_candidate_prices(self, prices: list[ScannerCandidatePriceRecord]) -> int:
        """Persist price observations tied to scanner candidates."""

        if not prices:
            return 0
        try:
            with self._connection_scope() as connection:
                with connection:
                    cursor = connection.executemany(
                        """
                        INSERT OR IGNORE INTO scanner_candidate_prices (
                            scanner_candidate_id, symbol, price, price_type, source, recorded_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        [
                            (
                                item.scanner_candidate_id,
                                item.symbol.upper(),
                                str(item.price) if item.price is not None else None,
                                item.price_type,
                                item.source,
                                item.recorded_at.isoformat(),
                            )
                            for item in prices
                        ],
                    )
            return int(cursor.rowcount)
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Scanner candidate price storage is unavailable.")
            LOGGER.warning("Skipping scanner candidate price persistence due to schema issue: %s", exc)
            return 0

    def upsert_symbol_candle_cache(self, candles: list[Candle], *, source: str) -> int:
        """Persist symbol candle cache rows for fast selected-symbol reads."""

        closed_candles = [candle for candle in candles if candle.is_closed]
        if not closed_candles:
            return 0
        now = datetime.now(tz=UTC).isoformat()
        try:
            with self._connection_scope() as connection:
                with connection:
                    connection.executemany(
                        """
                        INSERT INTO symbol_candle_cache (
                            symbol, interval, open_time, open, high, low, close,
                            volume, source, inserted_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(symbol, interval, open_time) DO UPDATE SET
                            open = excluded.open,
                            high = excluded.high,
                            low = excluded.low,
                            close = excluded.close,
                            volume = excluded.volume,
                            source = excluded.source,
                            updated_at = excluded.updated_at
                        """,
                        [
                            (
                                candle.symbol.upper(),
                                candle.timeframe,
                                candle.open_time.isoformat(),
                                str(candle.open),
                                str(candle.high),
                                str(candle.low),
                                str(candle.close),
                                str(candle.volume),
                                source,
                                now,
                                now,
                            )
                            for candle in closed_candles
                        ],
                    )
            return len(closed_candles)
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Symbol candle cache storage is unavailable.")
            LOGGER.warning("Skipping symbol candle cache persistence due to schema issue: %s", exc)
            return 0

    def upsert_symbol_analysis_cache(self, record: SymbolAnalysisCacheRecord) -> None:
        """Persist symbol analysis cache payloads for stale-while-revalidate reads."""

        try:
            with self._connection_scope() as connection:
                with connection:
                    connection.execute(
                        """
                        INSERT INTO symbol_analysis_cache (
                            symbol, analysis_type, horizon, payload_json, generated_at, expires_at, data_state
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(symbol, analysis_type, horizon) DO UPDATE SET
                            payload_json = excluded.payload_json,
                            generated_at = excluded.generated_at,
                            expires_at = excluded.expires_at,
                            data_state = excluded.data_state
                        """,
                        (
                            record.symbol.upper(),
                            record.analysis_type,
                            record.horizon,
                            record.payload_json,
                            record.generated_at.isoformat(),
                            record.expires_at.isoformat(),
                            record.data_state,
                        ),
                    )
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Symbol analysis cache storage is unavailable.")
            LOGGER.warning("Skipping symbol analysis cache persistence due to schema issue: %s", exc)

    def get_symbol_analysis_cache(
        self,
        *,
        symbol: str,
        analysis_type: str,
        horizon: str,
    ) -> SymbolAnalysisCacheRecord | None:
        """Return one persisted symbol analysis cache entry."""

        try:
            with self._connection_scope() as connection:
                row = connection.execute(
                    """
                    SELECT symbol, analysis_type, horizon, payload_json, generated_at, expires_at, data_state
                    FROM symbol_analysis_cache
                    WHERE symbol = ? AND analysis_type = ? AND horizon = ?
                    """,
                    (symbol.upper(), analysis_type, horizon),
                ).fetchone()
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Symbol analysis cache storage is unavailable.")
            LOGGER.warning("Failed to read symbol analysis cache due to schema issue: %s", exc)
            return None
        if row is None:
            return None
        return SymbolAnalysisCacheRecord(
            symbol=row["symbol"],
            analysis_type=row["analysis_type"],
            horizon=row["horizon"],
            payload_json=row["payload_json"],
            generated_at=datetime.fromisoformat(row["generated_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            data_state=row["data_state"],
        )

    def upsert_symbol_backfill_job(self, job: SymbolBackfillJobRecord) -> None:
        """Persist the latest state of a symbol backfill job."""

        try:
            with self._connection_scope() as connection:
                with connection:
                    connection.execute(
                        """
                        INSERT INTO symbol_backfill_jobs (
                            id, symbol, interval, lookback_days, status, started_at,
                            completed_at, error_message, candles_inserted
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            status = excluded.status,
                            completed_at = excluded.completed_at,
                            error_message = excluded.error_message,
                            candles_inserted = excluded.candles_inserted
                        """,
                        (
                            job.id,
                            job.symbol.upper(),
                            job.interval,
                            job.lookback_days,
                            job.status,
                            job.started_at.isoformat(),
                            job.completed_at.isoformat() if job.completed_at is not None else None,
                            job.error_message,
                            job.candles_inserted,
                        ),
                    )
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Symbol backfill job storage is unavailable.")
            LOGGER.warning("Skipping symbol backfill job persistence due to schema issue: %s", exc)

    def get_active_symbol_backfill_job(
        self,
        *,
        symbol: str,
        interval: str,
        lookback_days: int,
    ) -> SymbolBackfillJobRecord | None:
        """Return an active backfill job to prevent duplicate selected-symbol backfills."""

        try:
            with self._connection_scope() as connection:
                row = connection.execute(
                    """
                    SELECT id, symbol, interval, lookback_days, status, started_at,
                           completed_at, error_message, candles_inserted
                    FROM symbol_backfill_jobs
                    WHERE symbol = ? AND interval = ? AND lookback_days = ? AND status IN ('queued', 'loading')
                    ORDER BY started_at DESC
                    LIMIT 1
                    """,
                    (symbol.upper(), interval, lookback_days),
                ).fetchone()
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Symbol backfill job storage is unavailable.")
            LOGGER.warning("Failed to read active symbol backfill job due to schema issue: %s", exc)
            return None
        if row is None:
            return None
        return SymbolBackfillJobRecord(
            id=row["id"],
            symbol=row["symbol"],
            interval=row["interval"],
            lookback_days=int(row["lookback_days"]),
            status=row["status"],
            started_at=datetime.fromisoformat(row["started_at"]),
            completed_at=_safe_datetime(row["completed_at"]),
            error_message=row["error_message"],
            candles_inserted=int(row["candles_inserted"]),
        )

    def upsert_historical_candles(
        self,
        candles: list[Candle],
        *,
        source: str,
    ) -> int:
        """Persist full OHLCV candle history with deduplication by symbol/interval/open_time."""

        if not candles:
            return 0
        connection = self._open_connection()
        try:
            with connection:
                connection.executemany(
                    """
                    INSERT INTO historical_candles (
                        symbol, interval, open_time, close_time, open_price, high_price, low_price,
                        close_price, volume, quote_volume, trade_count, source, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol, interval, open_time) DO UPDATE SET
                        close_time = excluded.close_time,
                        open_price = excluded.open_price,
                        high_price = excluded.high_price,
                        low_price = excluded.low_price,
                        close_price = excluded.close_price,
                        volume = excluded.volume,
                        quote_volume = excluded.quote_volume,
                        trade_count = excluded.trade_count,
                        source = excluded.source,
                        created_at = excluded.created_at
                    """,
                    [
                        (
                            candle.symbol.upper(),
                            candle.timeframe,
                            candle.open_time.isoformat(),
                            candle.close_time.isoformat(),
                            str(candle.open),
                            str(candle.high),
                            str(candle.low),
                            str(candle.close),
                            str(candle.volume),
                            str(candle.quote_volume),
                            candle.trade_count,
                            source,
                            candle.event_time.isoformat(),
                        )
                        for candle in candles
                        if candle.is_closed
                    ],
                )
            return len(candles)
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Historical candle storage is unavailable.")
            LOGGER.warning("Skipping historical candle persistence due to schema issue: %s", exc)
            return 0
        finally:
            connection.close()

    def get_historical_candles(
        self,
        *,
        symbol: str,
        interval: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int | None = None,
    ) -> list[HistoricalCandleRecord]:
        """Return persisted OHLCV candle history for one symbol and interval."""

        query = """
            SELECT symbol, interval, open_time, close_time, open_price, high_price, low_price,
                   close_price, volume, quote_volume, trade_count, source, created_at
            FROM historical_candles
            WHERE symbol = ? AND interval = ?
        """
        params: list[Any] = [symbol.upper(), interval]
        if start_time is not None:
            query += " AND open_time >= ?"
            params.append(start_time.isoformat())
        if end_time is not None:
            query += " AND open_time <= ?"
            params.append(end_time.isoformat())
        query += " ORDER BY open_time ASC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        try:
            with self._connection_scope() as connection:
                rows = connection.execute(query, tuple(params)).fetchall()
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Historical candle storage is unavailable.")
            LOGGER.warning("Failed to read historical candles due to schema issue: %s", exc)
            return []
        return [
            HistoricalCandleRecord(
                symbol=row["symbol"],
                interval=row["interval"],
                open_time=datetime.fromisoformat(row["open_time"]),
                close_time=datetime.fromisoformat(row["close_time"]),
                open_price=_decimal(row["open_price"]),
                high_price=_decimal(row["high_price"]),
                low_price=_decimal(row["low_price"]),
                close_price=_decimal(row["close_price"]),
                volume=_decimal(row["volume"]),
                quote_volume=_decimal(row["quote_volume"]),
                trade_count=int(row["trade_count"]),
                source=row["source"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def upsert_futures_historical_candles(
        self,
        candles: list[Candle],
        *,
        source: str,
    ) -> int:
        """Persist USD-M Futures OHLCV candle history separately from Spot history."""

        if not candles:
            return 0
        connection = self._open_connection()
        try:
            with connection:
                connection.executemany(
                    """
                    INSERT INTO futures_historical_candles (
                        symbol, interval, open_time, close_time, open_price, high_price, low_price,
                        close_price, volume, quote_volume, trade_count, source, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol, interval, open_time) DO UPDATE SET
                        close_time = excluded.close_time,
                        open_price = excluded.open_price,
                        high_price = excluded.high_price,
                        low_price = excluded.low_price,
                        close_price = excluded.close_price,
                        volume = excluded.volume,
                        quote_volume = excluded.quote_volume,
                        trade_count = excluded.trade_count,
                        source = excluded.source,
                        created_at = excluded.created_at
                    """,
                    [
                        (
                            candle.symbol.upper(),
                            candle.timeframe,
                            candle.open_time.isoformat(),
                            candle.close_time.isoformat(),
                            str(candle.open),
                            str(candle.high),
                            str(candle.low),
                            str(candle.close),
                            str(candle.volume),
                            str(candle.quote_volume),
                            candle.trade_count,
                            source,
                            candle.event_time.isoformat(),
                        )
                        for candle in candles
                        if candle.is_closed
                    ],
                )
            self.upsert_symbol_candle_cache(candles, source=source)
            return len(candles)
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("USD-M Futures candle storage is unavailable.")
            LOGGER.warning("Skipping USD-M Futures candle persistence due to schema issue: %s", exc)
            return 0
        finally:
            connection.close()

    def get_futures_historical_candles(
        self,
        *,
        symbol: str,
        interval: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int | None = None,
    ) -> list[HistoricalCandleRecord]:
        """Return persisted USD-M Futures OHLCV candle history for one symbol and interval."""

        query = """
            SELECT symbol, interval, open_time, close_time, open_price, high_price, low_price,
                   close_price, volume, quote_volume, trade_count, source, created_at
            FROM futures_historical_candles
            WHERE symbol = ? AND interval = ?
        """
        params: list[Any] = [symbol.upper(), interval]
        if start_time is not None:
            query += " AND open_time >= ?"
            params.append(start_time.isoformat())
        if end_time is not None:
            query += " AND open_time <= ?"
            params.append(end_time.isoformat())
        query += " ORDER BY open_time ASC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        try:
            with self._connection_scope() as connection:
                rows = connection.execute(query, tuple(params)).fetchall()
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("USD-M Futures candle storage is unavailable.")
            LOGGER.warning("Failed to read USD-M Futures candles due to schema issue: %s", exc)
            return []
        return [
            HistoricalCandleRecord(
                symbol=row["symbol"],
                interval=row["interval"],
                open_time=datetime.fromisoformat(row["open_time"]),
                close_time=datetime.fromisoformat(row["close_time"]),
                open_price=_decimal(row["open_price"]),
                high_price=_decimal(row["high_price"]),
                low_price=_decimal(row["low_price"]),
                close_price=_decimal(row["close_price"]),
                volume=_decimal(row["volume"]),
                quote_volume=_decimal(row["quote_volume"]),
                trade_count=int(row["trade_count"]),
                source=row["source"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def insert_signal_outcome_snapshot(self, snapshot: SignalOutcomeSnapshotRecord) -> str | None:
        """Persist one generated signal snapshot for post-signal outcome tracking."""

        try:
            connection = self._open_connection()
            with connection:
                connection.execute(
                    """
                    INSERT INTO signal_snapshots (
                        id, symbol, snapshot_time, source, signal_type, confidence, entry_price,
                        liquidity_bias, sweep_risk, nearest_liquidity_above, nearest_liquidity_below,
                        funding_rate, open_interest, notes, heatmap_liquidity_above, heatmap_liquidity_below,
                        heatmap_intensity_score, heatmap_bias, base_signal_type, heatmap_signal_type,
                        base_confidence, heatmap_confidence, heatmap_alignment, heatmap_explanation,
                        heatmap_provider, heatmap_data_quality, heatmap_is_real_data, heatmap_provider_status,
                        liquidation_pressure, liquidation_imbalance
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot.id,
                        snapshot.symbol.upper(),
                        snapshot.timestamp.isoformat(),
                        snapshot.source,
                        snapshot.signal_type.upper(),
                        snapshot.confidence,
                        str(snapshot.entry_price) if snapshot.entry_price is not None else None,
                        snapshot.liquidity_bias,
                        snapshot.sweep_risk,
                        (
                            str(snapshot.nearest_liquidity_above)
                            if snapshot.nearest_liquidity_above is not None
                            else None
                        ),
                        (
                            str(snapshot.nearest_liquidity_below)
                            if snapshot.nearest_liquidity_below is not None
                            else None
                        ),
                        str(snapshot.funding_rate) if snapshot.funding_rate is not None else None,
                        str(snapshot.open_interest) if snapshot.open_interest is not None else None,
                        snapshot.notes,
                        (
                            str(snapshot.heatmap_liquidity_above)
                            if snapshot.heatmap_liquidity_above is not None
                            else None
                        ),
                        (
                            str(snapshot.heatmap_liquidity_below)
                            if snapshot.heatmap_liquidity_below is not None
                            else None
                        ),
                        snapshot.heatmap_intensity_score,
                        snapshot.heatmap_bias,
                        snapshot.base_signal_type,
                        snapshot.heatmap_signal_type,
                        snapshot.base_confidence,
                        snapshot.heatmap_confidence,
                        snapshot.heatmap_alignment,
                        snapshot.heatmap_explanation,
                        snapshot.heatmap_provider,
                        snapshot.heatmap_data_quality,
                        int(snapshot.heatmap_is_real_data) if snapshot.heatmap_is_real_data is not None else None,
                        snapshot.heatmap_provider_status,
                        snapshot.liquidation_pressure,
                        (
                            str(snapshot.liquidation_imbalance)
                            if snapshot.liquidation_imbalance is not None
                            else None
                        ),
                    ),
                )
            return snapshot.id
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Post-signal snapshot storage is unavailable.")
            LOGGER.warning("Skipping post-signal snapshot persistence due to schema issue: %s", exc)
            return None
        finally:
            if "connection" in locals():
                connection.close()

    def get_signal_outcome_snapshots(
        self,
        *,
        symbol: str | None = None,
        source: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[SignalOutcomeSnapshotRecord]:
        """Return generated signal snapshots for post-signal outcome tracking."""

        query = """
            SELECT id, symbol, snapshot_time, source, signal_type, confidence, entry_price,
                   liquidity_bias, sweep_risk, nearest_liquidity_above, nearest_liquidity_below,
                   funding_rate, open_interest, notes, heatmap_liquidity_above, heatmap_liquidity_below,
                   heatmap_intensity_score, heatmap_bias, base_signal_type, heatmap_signal_type,
                   base_confidence, heatmap_confidence, heatmap_alignment, heatmap_explanation,
                   heatmap_provider, heatmap_data_quality, heatmap_is_real_data, heatmap_provider_status,
                   liquidation_pressure, liquidation_imbalance
            FROM signal_snapshots
            WHERE 1 = 1
        """
        params: list[Any] = []
        query, params = self._apply_history_filters(
            query=query,
            params=params,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timestamp_column="snapshot_time",
        )
        if source is not None:
            query += " AND source = ?"
            params.append(source)
        query += " ORDER BY snapshot_time DESC, id DESC"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        try:
            with self._connection_scope() as connection:
                rows = connection.execute(query, tuple(params)).fetchall()
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Post-signal snapshot storage is unavailable.")
            LOGGER.warning("Failed to read post-signal snapshots due to schema issue: %s", exc)
            return []
        return [_signal_outcome_snapshot_from_row(row) for row in rows]

    def get_signal_outcome_snapshot(self, signal_id: str) -> SignalOutcomeSnapshotRecord | None:
        """Return one generated signal snapshot by UUID."""

        try:
            with self._connection_scope() as connection:
                row = connection.execute(
                    """
                    SELECT id, symbol, snapshot_time, source, signal_type, confidence, entry_price,
                           liquidity_bias, sweep_risk, nearest_liquidity_above, nearest_liquidity_below,
                           funding_rate, open_interest, notes, heatmap_liquidity_above, heatmap_liquidity_below,
                           heatmap_intensity_score, heatmap_bias, base_signal_type, heatmap_signal_type,
                           base_confidence, heatmap_confidence, heatmap_alignment, heatmap_explanation,
                           heatmap_provider, heatmap_data_quality, heatmap_is_real_data, heatmap_provider_status,
                           liquidation_pressure, liquidation_imbalance
                    FROM signal_snapshots
                    WHERE id = ?
                    """,
                    (signal_id,),
                ).fetchone()
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Post-signal snapshot storage is unavailable.")
            LOGGER.warning("Failed to read post-signal snapshot due to schema issue: %s", exc)
            return None
        return _signal_outcome_snapshot_from_row(row) if row is not None else None

    def upsert_signal_outcome(self, outcome: SignalOutcomeRecord) -> None:
        """Persist or replace a fixed-horizon post-signal outcome."""

        try:
            connection = self._open_connection()
            with connection:
                connection.execute(
                    """
                    INSERT INTO signal_outcomes (
                        signal_id, horizon, future_price, price_change_percent, max_upside_percent,
                        max_downside_percent, did_price_hit_tp, did_price_hit_sl, direction_correct,
                        volatility_range, first_hit, time_to_hit_seconds, sweep_direction_actual,
                        sweep_prediction_correct, outcome_state, evaluated_at, base_signal_correct,
                        heatmap_signal_correct, did_heatmap_improve_result, did_heatmap_reduce_loss,
                        predicted_sweep_direction, actual_sweep_direction
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(signal_id, horizon) DO UPDATE SET
                        future_price = excluded.future_price,
                        price_change_percent = excluded.price_change_percent,
                        max_upside_percent = excluded.max_upside_percent,
                        max_downside_percent = excluded.max_downside_percent,
                        did_price_hit_tp = excluded.did_price_hit_tp,
                        did_price_hit_sl = excluded.did_price_hit_sl,
                        direction_correct = excluded.direction_correct,
                        volatility_range = excluded.volatility_range,
                        first_hit = excluded.first_hit,
                        time_to_hit_seconds = excluded.time_to_hit_seconds,
                        sweep_direction_actual = excluded.sweep_direction_actual,
                        sweep_prediction_correct = excluded.sweep_prediction_correct,
                        outcome_state = excluded.outcome_state,
                        evaluated_at = excluded.evaluated_at,
                        base_signal_correct = excluded.base_signal_correct,
                        heatmap_signal_correct = excluded.heatmap_signal_correct,
                        did_heatmap_improve_result = excluded.did_heatmap_improve_result,
                        did_heatmap_reduce_loss = excluded.did_heatmap_reduce_loss,
                        predicted_sweep_direction = excluded.predicted_sweep_direction,
                        actual_sweep_direction = excluded.actual_sweep_direction
                    """,
                    (
                        outcome.signal_id,
                        outcome.horizon,
                        str(outcome.future_price) if outcome.future_price is not None else None,
                        (
                            str(outcome.price_change_percent)
                            if outcome.price_change_percent is not None
                            else None
                        ),
                        str(outcome.max_upside_percent) if outcome.max_upside_percent is not None else None,
                        str(outcome.max_downside_percent) if outcome.max_downside_percent is not None else None,
                        int(outcome.did_price_hit_tp),
                        int(outcome.did_price_hit_sl),
                        int(outcome.direction_correct) if outcome.direction_correct is not None else None,
                        str(outcome.volatility_range) if outcome.volatility_range is not None else None,
                        outcome.first_hit,
                        outcome.time_to_hit_seconds,
                        outcome.sweep_direction_actual,
                        (
                            int(outcome.sweep_prediction_correct)
                            if outcome.sweep_prediction_correct is not None
                            else None
                        ),
                        outcome.outcome_state,
                        outcome.evaluated_at.isoformat(),
                        int(outcome.base_signal_correct) if outcome.base_signal_correct is not None else None,
                        int(outcome.heatmap_signal_correct) if outcome.heatmap_signal_correct is not None else None,
                        (
                            int(outcome.did_heatmap_improve_result)
                            if outcome.did_heatmap_improve_result is not None
                            else None
                        ),
                        (
                            int(outcome.did_heatmap_reduce_loss)
                            if outcome.did_heatmap_reduce_loss is not None
                            else None
                        ),
                        outcome.predicted_sweep_direction,
                        outcome.actual_sweep_direction,
                    ),
                )
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Post-signal outcome storage is unavailable.")
            LOGGER.warning("Skipping post-signal outcome persistence due to schema issue: %s", exc)
        finally:
            if "connection" in locals():
                connection.close()

    def get_signal_outcomes(
        self,
        *,
        signal_ids: list[str] | None = None,
        horizon: str | None = None,
    ) -> list[SignalOutcomeRecord]:
        """Return post-signal outcomes."""

        if signal_ids == []:
            return []
        query = """
            SELECT id, signal_id, horizon, future_price, price_change_percent, max_upside_percent,
                   max_downside_percent, did_price_hit_tp, did_price_hit_sl, direction_correct,
                   volatility_range, first_hit, time_to_hit_seconds, sweep_direction_actual,
                   sweep_prediction_correct, outcome_state, evaluated_at, base_signal_correct,
                   heatmap_signal_correct, did_heatmap_improve_result, did_heatmap_reduce_loss,
                   predicted_sweep_direction, actual_sweep_direction
            FROM signal_outcomes
            WHERE 1 = 1
        """
        params: list[Any] = []
        if signal_ids:
            placeholders = ",".join("?" for _ in signal_ids)
            query += f" AND signal_id IN ({placeholders})"
            params.extend(signal_ids)
        if horizon is not None:
            query += " AND horizon = ?"
            params.append(horizon)
        query += " ORDER BY evaluated_at DESC, id DESC"
        try:
            with self._connection_scope() as connection:
                rows = connection.execute(query, tuple(params)).fetchall()
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Post-signal outcome storage is unavailable.")
            LOGGER.warning("Failed to read post-signal outcomes due to schema issue: %s", exc)
            return []
        return [_signal_outcome_from_row(row) for row in rows]

    def upsert_signal_timing_baseline(self, baseline: SignalTimingBaselineRecord) -> None:
        """Persist or replace one signal timing-quality baseline."""

        values = (
            baseline.signal_id,
            baseline.horizon,
            baseline.symbol.upper(),
            baseline.source,
            baseline.direction,
            baseline.signal_time.isoformat(),
            baseline.setup_start_time.isoformat() if baseline.setup_start_time is not None else None,
            str(baseline.setup_start_price) if baseline.setup_start_price is not None else None,
            str(baseline.activation_price) if baseline.activation_price is not None else None,
            str(baseline.recent_swing_low) if baseline.recent_swing_low is not None else None,
            str(baseline.recent_swing_high) if baseline.recent_swing_high is not None else None,
            str(baseline.horizon_end_price) if baseline.horizon_end_price is not None else None,
            str(baseline.max_favorable_price) if baseline.max_favorable_price is not None else None,
            str(baseline.max_adverse_price) if baseline.max_adverse_price is not None else None,
            str(baseline.move_before_signal_pct) if baseline.move_before_signal_pct is not None else None,
            str(baseline.move_after_signal_pct) if baseline.move_after_signal_pct is not None else None,
            (
                str(baseline.max_favorable_excursion_pct)
                if baseline.max_favorable_excursion_pct is not None
                else None
            ),
            (
                str(baseline.max_adverse_excursion_pct)
                if baseline.max_adverse_excursion_pct is not None
                else None
            ),
            str(baseline.full_move_pct) if baseline.full_move_pct is not None else None,
            (
                str(baseline.move_already_consumed_pct)
                if baseline.move_already_consumed_pct is not None
                else None
            ),
            (
                str(baseline.move_capture_ratio_pct)
                if baseline.move_capture_ratio_pct is not None
                else None
            ),
            str(baseline.entry_efficiency_pct) if baseline.entry_efficiency_pct is not None else None,
            baseline.pre_move_lead_time_seconds,
            baseline.signal_to_entry_latency_seconds,
            baseline.time_to_target_seconds,
            baseline.time_to_stop_seconds,
            baseline.expiry_seconds,
            (
                str(baseline.net_return_after_costs_pct)
                if baseline.net_return_after_costs_pct is not None
                else None
            ),
            str(baseline.estimated_round_trip_cost_pct),
            str(baseline.realized_volatility_pct) if baseline.realized_volatility_pct is not None else None,
            baseline.regime_label,
            baseline.liquidity_context,
            baseline.classification,
            json.dumps(list(baseline.classification_reasons)),
            baseline.outcome_state,
            baseline.evaluated_at.isoformat(),
        )
        try:
            with self._connection_scope() as connection:
                with connection:
                    connection.execute(
                        """
                        INSERT INTO signal_timing_baselines (
                            signal_id, horizon, symbol, source, direction, signal_time,
                            setup_start_time, setup_start_price, activation_price,
                            recent_swing_low, recent_swing_high, horizon_end_price,
                            max_favorable_price, max_adverse_price, move_before_signal_pct,
                            move_after_signal_pct, max_favorable_excursion_pct,
                            max_adverse_excursion_pct, full_move_pct, move_already_consumed_pct,
                            move_capture_ratio_pct, entry_efficiency_pct, pre_move_lead_time_seconds,
                            signal_to_entry_latency_seconds, time_to_target_seconds,
                            time_to_stop_seconds, expiry_seconds, net_return_after_costs_pct,
                            estimated_round_trip_cost_pct, realized_volatility_pct, regime_label,
                            liquidity_context, classification, classification_reasons_json,
                            outcome_state, evaluated_at
                        ) VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                        )
                        ON CONFLICT(signal_id, horizon) DO UPDATE SET
                            setup_start_time = excluded.setup_start_time,
                            setup_start_price = excluded.setup_start_price,
                            activation_price = excluded.activation_price,
                            recent_swing_low = excluded.recent_swing_low,
                            recent_swing_high = excluded.recent_swing_high,
                            horizon_end_price = excluded.horizon_end_price,
                            max_favorable_price = excluded.max_favorable_price,
                            max_adverse_price = excluded.max_adverse_price,
                            move_before_signal_pct = excluded.move_before_signal_pct,
                            move_after_signal_pct = excluded.move_after_signal_pct,
                            max_favorable_excursion_pct = excluded.max_favorable_excursion_pct,
                            max_adverse_excursion_pct = excluded.max_adverse_excursion_pct,
                            full_move_pct = excluded.full_move_pct,
                            move_already_consumed_pct = excluded.move_already_consumed_pct,
                            move_capture_ratio_pct = excluded.move_capture_ratio_pct,
                            entry_efficiency_pct = excluded.entry_efficiency_pct,
                            pre_move_lead_time_seconds = excluded.pre_move_lead_time_seconds,
                            signal_to_entry_latency_seconds = excluded.signal_to_entry_latency_seconds,
                            time_to_target_seconds = excluded.time_to_target_seconds,
                            time_to_stop_seconds = excluded.time_to_stop_seconds,
                            expiry_seconds = excluded.expiry_seconds,
                            net_return_after_costs_pct = excluded.net_return_after_costs_pct,
                            estimated_round_trip_cost_pct = excluded.estimated_round_trip_cost_pct,
                            realized_volatility_pct = excluded.realized_volatility_pct,
                            regime_label = excluded.regime_label,
                            liquidity_context = excluded.liquidity_context,
                            classification = excluded.classification,
                            classification_reasons_json = excluded.classification_reasons_json,
                            outcome_state = excluded.outcome_state,
                            evaluated_at = excluded.evaluated_at
                        """,
                        values,
                    )
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Signal timing baseline storage is unavailable.")
            LOGGER.warning("Skipping signal timing baseline persistence due to schema issue: %s", exc)

    def get_signal_timing_baselines(
        self,
        *,
        symbol: str | None = None,
        source: str | None = None,
        horizon: str | None = None,
        classification: str | None = None,
        limit: int | None = None,
    ) -> list[SignalTimingBaselineRecord]:
        """Return persisted signal timing baselines with optional filters."""

        query = "SELECT * FROM signal_timing_baselines WHERE 1 = 1"
        params: list[Any] = []
        if symbol is not None:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        if source is not None:
            query += " AND source = ?"
            params.append(source)
        if horizon is not None:
            query += " AND horizon = ?"
            params.append(horizon)
        if classification is not None:
            query += " AND classification = ?"
            params.append(classification)
        query += " ORDER BY signal_time DESC, id DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        try:
            with self._connection_scope() as connection:
                rows = connection.execute(query, tuple(params)).fetchall()
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Signal timing baseline storage is unavailable.")
            LOGGER.warning("Failed to read signal timing baselines due to schema issue: %s", exc)
            return []
        return [_signal_timing_baseline_from_row(row) for row in rows]

    def upsert_continuous_intelligence_state(
        self,
        state: ContinuousIntelligenceStateRecord,
    ) -> None:
        """Persist the singleton continuous-intelligence service checkpoint."""

        with self._connection_scope() as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO continuous_intelligence_state (
                        singleton_id, enabled, status, cycle_id, started_at,
                        last_cycle_started_at, last_cycle_completed_at,
                        last_full_universe_pass_at, last_universe_refresh_at,
                        last_websocket_event_at, next_cycle_at, last_error,
                        universe_source, total_symbols, fast_screened_symbols,
                        deep_analyzed_symbols, deep_queue_depth, successful_cycles,
                        failed_cycles, consecutive_failures, config_json, updated_at
                    ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(singleton_id) DO UPDATE SET
                        enabled = excluded.enabled,
                        status = excluded.status,
                        cycle_id = excluded.cycle_id,
                        started_at = excluded.started_at,
                        last_cycle_started_at = excluded.last_cycle_started_at,
                        last_cycle_completed_at = excluded.last_cycle_completed_at,
                        last_full_universe_pass_at = excluded.last_full_universe_pass_at,
                        last_universe_refresh_at = excluded.last_universe_refresh_at,
                        last_websocket_event_at = excluded.last_websocket_event_at,
                        next_cycle_at = excluded.next_cycle_at,
                        last_error = excluded.last_error,
                        universe_source = excluded.universe_source,
                        total_symbols = excluded.total_symbols,
                        fast_screened_symbols = excluded.fast_screened_symbols,
                        deep_analyzed_symbols = excluded.deep_analyzed_symbols,
                        deep_queue_depth = excluded.deep_queue_depth,
                        successful_cycles = excluded.successful_cycles,
                        failed_cycles = excluded.failed_cycles,
                        consecutive_failures = excluded.consecutive_failures,
                        config_json = excluded.config_json,
                        updated_at = excluded.updated_at
                    """,
                    (
                        int(state.enabled),
                        state.status,
                        state.cycle_id,
                        state.started_at.isoformat() if state.started_at else None,
                        state.last_cycle_started_at.isoformat() if state.last_cycle_started_at else None,
                        state.last_cycle_completed_at.isoformat() if state.last_cycle_completed_at else None,
                        state.last_full_universe_pass_at.isoformat() if state.last_full_universe_pass_at else None,
                        state.last_universe_refresh_at.isoformat() if state.last_universe_refresh_at else None,
                        state.last_websocket_event_at.isoformat() if state.last_websocket_event_at else None,
                        state.next_cycle_at.isoformat() if state.next_cycle_at else None,
                        state.last_error,
                        state.universe_source,
                        state.total_symbols,
                        state.fast_screened_symbols,
                        state.deep_analyzed_symbols,
                        state.deep_queue_depth,
                        state.successful_cycles,
                        state.failed_cycles,
                        state.consecutive_failures,
                        state.config_json,
                        state.updated_at.isoformat(),
                    ),
                )

    def get_continuous_intelligence_state(self) -> ContinuousIntelligenceStateRecord | None:
        """Return the persisted continuous-intelligence checkpoint."""

        with self._connection_scope() as connection:
            row = connection.execute(
                "SELECT * FROM continuous_intelligence_state WHERE singleton_id = 1"
            ).fetchone()
        return _continuous_intelligence_state_from_row(row) if row is not None else None

    def upsert_continuous_intelligence_candidates(
        self,
        candidates: list[ContinuousIntelligenceCandidateRecord],
    ) -> int:
        """Persist the latest tiered screening result for each symbol."""

        if not candidates:
            return 0
        with self._connection_scope() as connection:
            with connection:
                cursor = connection.executemany(
                    """
                    INSERT INTO continuous_intelligence_candidates (
                        market, symbol, stage, fast_score, deep_score, direction_hint,
                        current_price, triggers_json, metrics_json, reasons_json,
                        warnings_json, screened_at, deep_analyzed_at, data_source
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(market, symbol) DO UPDATE SET
                        stage = excluded.stage,
                        fast_score = excluded.fast_score,
                        deep_score = excluded.deep_score,
                        direction_hint = excluded.direction_hint,
                        current_price = excluded.current_price,
                        triggers_json = excluded.triggers_json,
                        metrics_json = excluded.metrics_json,
                        reasons_json = excluded.reasons_json,
                        warnings_json = excluded.warnings_json,
                        screened_at = excluded.screened_at,
                        deep_analyzed_at = excluded.deep_analyzed_at,
                        data_source = excluded.data_source
                    """,
                    [
                        (
                            item.market,
                            item.symbol.upper(),
                            item.stage,
                            item.fast_score,
                            item.deep_score,
                            item.direction_hint,
                            str(item.current_price) if item.current_price is not None else None,
                            json.dumps(list(item.triggers)),
                            item.metrics_json,
                            json.dumps(list(item.reasons)),
                            json.dumps(list(item.warnings)),
                            item.screened_at.isoformat(),
                            item.deep_analyzed_at.isoformat() if item.deep_analyzed_at else None,
                            item.data_source,
                        )
                        for item in candidates
                    ],
                )
        return int(cursor.rowcount)

    def get_continuous_intelligence_candidates(
        self,
        *,
        market: str | None = None,
        stage: str | None = None,
        limit: int = 100,
    ) -> list[ContinuousIntelligenceCandidateRecord]:
        """Return latest continuous candidates ordered by deep then fast score."""

        query = "SELECT * FROM continuous_intelligence_candidates WHERE 1 = 1"
        params: list[Any] = []
        if market is not None:
            query += " AND market = ?"
            params.append(market)
        if stage is not None:
            query += " AND stage = ?"
            params.append(stage)
        query += " ORDER BY COALESCE(deep_score, -1) DESC, fast_score DESC, symbol ASC LIMIT ?"
        params.append(limit)
        with self._connection_scope() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [_continuous_intelligence_candidate_from_row(row) for row in rows]

    def delete_stale_continuous_intelligence_candidates(
        self,
        *,
        market: str,
        active_symbols: list[str],
    ) -> int:
        """Remove candidates no longer present in the active configured universe."""

        normalized = [symbol.upper() for symbol in active_symbols]
        with self._connection_scope() as connection:
            with connection:
                if not normalized:
                    cursor = connection.execute(
                        "DELETE FROM continuous_intelligence_candidates WHERE market = ?",
                        (market,),
                    )
                else:
                    placeholders = ",".join("?" for _ in normalized)
                    cursor = connection.execute(
                        f"DELETE FROM continuous_intelligence_candidates WHERE market = ? AND symbol NOT IN ({placeholders})",
                        (market, *normalized),
                    )
        return int(cursor.rowcount)

    def upsert_continuous_intelligence_cycle(
        self,
        cycle: ContinuousIntelligenceCycleRecord,
    ) -> None:
        """Persist one continuous-intelligence cycle summary."""

        with self._connection_scope() as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO continuous_intelligence_cycles (
                        cycle_id, started_at, completed_at, status, universe_source,
                        total_symbols, fast_screened_symbols, deep_analyzed_symbols,
                        candidate_count, failed_symbols_json, error_message, duration_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(cycle_id) DO UPDATE SET
                        completed_at = excluded.completed_at,
                        status = excluded.status,
                        universe_source = excluded.universe_source,
                        total_symbols = excluded.total_symbols,
                        fast_screened_symbols = excluded.fast_screened_symbols,
                        deep_analyzed_symbols = excluded.deep_analyzed_symbols,
                        candidate_count = excluded.candidate_count,
                        failed_symbols_json = excluded.failed_symbols_json,
                        error_message = excluded.error_message,
                        duration_ms = excluded.duration_ms
                    """,
                    (
                        cycle.cycle_id,
                        cycle.started_at.isoformat(),
                        cycle.completed_at.isoformat() if cycle.completed_at else None,
                        cycle.status,
                        cycle.universe_source,
                        cycle.total_symbols,
                        cycle.fast_screened_symbols,
                        cycle.deep_analyzed_symbols,
                        cycle.candidate_count,
                        json.dumps(list(cycle.failed_symbols)),
                        cycle.error_message,
                        cycle.duration_ms,
                    ),
                )

    def get_continuous_intelligence_cycles(
        self,
        *,
        limit: int = 20,
    ) -> list[ContinuousIntelligenceCycleRecord]:
        """Return recent continuous-intelligence cycle summaries."""

        with self._connection_scope() as connection:
            rows = connection.execute(
                "SELECT * FROM continuous_intelligence_cycles ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_continuous_intelligence_cycle_from_row(row) for row in rows]

    def latest_historical_candle(
        self,
        *,
        symbol: str,
        interval: str,
    ) -> HistoricalCandleRecord | None:
        """Return the latest persisted candle for one symbol and interval."""

        query = """
            SELECT symbol, interval, open_time, close_time, open_price, high_price, low_price,
                   close_price, volume, quote_volume, trade_count, source, created_at
            FROM historical_candles
            WHERE symbol = ? AND interval = ?
            ORDER BY open_time DESC
            LIMIT 1
        """
        try:
            with self._connection_scope() as connection:
                row = connection.execute(query, (symbol.upper(), interval)).fetchone()
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Historical candle storage is unavailable.")
            LOGGER.warning("Failed to read latest historical candle due to schema issue: %s", exc)
            return None
        if row is None:
            return None
        return HistoricalCandleRecord(
            symbol=row["symbol"],
            interval=row["interval"],
            open_time=datetime.fromisoformat(row["open_time"]),
            close_time=datetime.fromisoformat(row["close_time"]),
            open_price=_decimal(row["open_price"]),
            high_price=_decimal(row["high_price"]),
            low_price=_decimal(row["low_price"]),
            close_price=_decimal(row["close_price"]),
            volume=_decimal(row["volume"]),
            quote_volume=_decimal(row["quote_volume"]),
            trade_count=int(row["trade_count"]),
            source=row["source"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def insert_ai_signal_snapshot(self, snapshot: AISignalSnapshot) -> bool:
        """Persist an AI advisory snapshot when it materially changed."""

        connection = self._open_connection()
        try:
            with connection:
                try:
                    row = connection.execute(
                        """
                        SELECT symbol, snapshot_time, bias, confidence, entry_signal, exit_signal,
                               suggested_action, explanation, feature_summary_json
                        FROM ai_signal_snapshots
                        WHERE symbol = ?
                        ORDER BY snapshot_time DESC
                        LIMIT 1
                        """,
                        (snapshot.symbol.upper(),),
                    ).fetchone()
                    latest_snapshot = (
                        AISignalSnapshotRecord(
                            symbol=row["symbol"],
                            timestamp=datetime.fromisoformat(row["snapshot_time"]),
                            bias=row["bias"],
                            confidence=int(row["confidence"]),
                            entry_signal=bool(row["entry_signal"]),
                            exit_signal=bool(row["exit_signal"]),
                            suggested_action=row["suggested_action"],
                            explanation=row["explanation"],
                            feature_summary=_parse_ai_feature_summary(row["feature_summary_json"]),
                        )
                        if row is not None
                        else None
                    )
                    next_feature_summary = _parse_ai_feature_summary(_serialize_ai_feature_summary(snapshot))
                    next_snapshot = AISignalSnapshotRecord(
                        symbol=snapshot.symbol.upper(),
                        timestamp=snapshot.feature_vector.timestamp,
                        bias=snapshot.bias,
                        confidence=snapshot.confidence,
                        entry_signal=snapshot.entry_signal,
                        exit_signal=snapshot.exit_signal,
                        suggested_action=snapshot.suggested_action,
                        explanation=snapshot.explanation,
                        feature_summary=next_feature_summary,
                    )
                    if latest_snapshot is not None and not _ai_signal_materially_changed(latest_snapshot, next_snapshot):
                        return False

                    connection.execute(
                        """
                        INSERT INTO ai_signal_snapshots (
                            symbol, snapshot_time, bias, confidence, entry_signal, exit_signal,
                            suggested_action, explanation, feature_summary_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            next_snapshot.symbol,
                            next_snapshot.timestamp.isoformat(),
                            next_snapshot.bias,
                            next_snapshot.confidence,
                            int(next_snapshot.entry_signal),
                            int(next_snapshot.exit_signal),
                            next_snapshot.suggested_action,
                            next_snapshot.explanation,
                            _serialize_ai_feature_summary(snapshot),
                        ),
                    )
                except sqlite3.OperationalError as exc:
                    if not _is_optional_schema_error(exc):
                        raise
                    self._mark_optional_storage_degraded("AI advisory snapshot storage is unavailable.")
                    LOGGER.warning("Skipping AI signal snapshot persistence due to schema issue: %s", exc)
                    return False
        finally:
            connection.close()
        return True

    def get_latest_ai_signal(self, symbol: str) -> AISignalSnapshotRecord | None:
        """Return the latest persisted AI advisory snapshot for a symbol."""

        try:
            with self._connection_scope() as connection:
                row = connection.execute(
                    """
                    SELECT symbol, snapshot_time, bias, confidence, entry_signal, exit_signal,
                           suggested_action, explanation, feature_summary_json
                    FROM ai_signal_snapshots
                    WHERE symbol = ?
                    ORDER BY snapshot_time DESC
                    LIMIT 1
                    """,
                    (symbol.upper(),),
                ).fetchone()
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("AI advisory snapshot storage is unavailable.")
            LOGGER.warning("Failed to read latest AI signal due to schema issue: %s", exc)
            return None
        if row is None:
            return None
        return AISignalSnapshotRecord(
            symbol=row["symbol"],
            timestamp=datetime.fromisoformat(row["snapshot_time"]),
            bias=row["bias"],
            confidence=int(row["confidence"]),
            entry_signal=bool(row["entry_signal"]),
            exit_signal=bool(row["exit_signal"]),
            suggested_action=row["suggested_action"],
            explanation=row["explanation"],
            feature_summary=_parse_ai_feature_summary(row["feature_summary_json"]),
        )

    def get_ai_signal_history(
        self,
        *,
        symbol: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[AISignalSnapshotRecord]:
        """Return persisted AI advisory history for one symbol."""

        query = """
            SELECT symbol, snapshot_time, bias, confidence, entry_signal, exit_signal,
                   suggested_action, explanation, feature_summary_json
            FROM ai_signal_snapshots
            WHERE symbol = ?
        """
        params: list[Any] = [symbol.upper()]
        query, params = self._apply_date_filters(
            query=query,
            params=params,
            start_date=start_date,
            end_date=end_date,
            timestamp_column="snapshot_time",
        )
        query += " ORDER BY snapshot_time DESC"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend((limit, offset))
        try:
            with self._connection_scope() as connection:
                rows = connection.execute(query, tuple(params)).fetchall()
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("AI advisory history storage is unavailable.")
            LOGGER.warning("Failed to read AI signal history due to schema issue: %s", exc)
            return []
        return [
            AISignalSnapshotRecord(
                symbol=row["symbol"],
                timestamp=datetime.fromisoformat(row["snapshot_time"]),
                bias=row["bias"],
                confidence=int(row["confidence"]),
                entry_signal=bool(row["entry_signal"]),
                exit_signal=bool(row["exit_signal"]),
                suggested_action=row["suggested_action"],
                explanation=row["explanation"],
                feature_summary=_parse_ai_feature_summary(row["feature_summary_json"]),
            )
            for row in rows
        ]

    def count_ai_signal_history(
        self,
        *,
        symbol: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> int:
        """Return the number of persisted AI advisory snapshots for one symbol."""

        query = """
            SELECT COUNT(*) AS row_count
            FROM ai_signal_snapshots
            WHERE symbol = ?
        """
        params: list[Any] = [symbol.upper()]
        query, params = self._apply_date_filters(
            query=query,
            params=params,
            start_date=start_date,
            end_date=end_date,
            timestamp_column="snapshot_time",
        )
        try:
            with self._connection_scope() as connection:
                row = connection.execute(query, tuple(params)).fetchone()
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("AI advisory history storage is unavailable.")
            LOGGER.warning("Failed to count AI signal history due to schema issue: %s", exc)
            return 0
        return int(row["row_count"]) if row is not None else 0

    def get_market_candle_history(
        self,
        *,
        symbol: str,
        timeframe: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[MarketCandleSnapshotRecord]:
        """Return persisted closed-candle history for one symbol."""

        query = """
            SELECT symbol, timeframe, open_time, close_time, close_price, event_time
            FROM market_candle_snapshots
            WHERE symbol = ?
        """
        params: list[Any] = [symbol.upper()]
        if timeframe is not None:
            query += " AND timeframe = ?"
            params.append(timeframe)
        query, params = self._apply_date_filters(
            query=query,
            params=params,
            start_date=start_date,
            end_date=end_date,
            timestamp_column="close_time",
        )
        query += " ORDER BY close_time ASC"
        try:
            with self._connection_scope() as connection:
                rows = connection.execute(query, tuple(params)).fetchall()
        except sqlite3.OperationalError as exc:
            if not _is_optional_schema_error(exc):
                raise
            self._mark_optional_storage_degraded("Closed-candle outcome storage is unavailable.")
            LOGGER.warning("Failed to read market candle history due to schema issue: %s", exc)
            return []
        return [
            MarketCandleSnapshotRecord(
                symbol=row["symbol"],
                timeframe=row["timeframe"],
                open_time=datetime.fromisoformat(row["open_time"]),
                close_time=datetime.fromisoformat(row["close_time"]),
                close_price=_decimal(row["close_price"]),
                event_time=datetime.fromisoformat(row["event_time"]),
            )
            for row in rows
        ]

    def insert_trade(
        self,
        *,
        fill_result: FillResult,
        risk_decision: RiskDecision,
        approved_quantity: Decimal,
        event_time: datetime,
        execution_source: str = "auto",
        trading_profile: str = "balanced",
        session_id: str | None = None,
        tuning_version_id: str | None = None,
    ) -> None:
        """Persist a trade record."""

        connection = self._open_connection()
        try:
            with connection:
                connection.execute(
                """
                INSERT INTO trades (
                    order_id, symbol, side, requested_quantity, approved_quantity, filled_quantity,
                    status, risk_decision, reason_codes, fill_price, realized_pnl, quote_balance, event_time,
                    execution_source, trading_profile, session_id, tuning_version_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fill_result.order_id,
                    fill_result.symbol,
                    fill_result.side,
                    str(fill_result.requested_quantity),
                    str(approved_quantity),
                    str(fill_result.filled_quantity),
                    fill_result.status,
                    risk_decision.decision,
                    json.dumps(risk_decision.reason_codes),
                    str(fill_result.fill_price),
                    str(fill_result.realized_pnl),
                    str(fill_result.quote_balance),
                    event_time.isoformat(),
                    execution_source,
                    trading_profile,
                    session_id,
                    tuning_version_id,
                ),
            )
        finally:
            connection.close()

    def insert_fill(
        self,
        fill_result: FillResult,
        event_time: datetime,
        *,
        execution_source: str = "auto",
        trading_profile: str = "balanced",
        session_id: str | None = None,
        tuning_version_id: str | None = None,
    ) -> None:
        """Persist a fill row for executed orders."""

        connection = self._open_connection()
        try:
            with connection:
                connection.execute(
                """
                INSERT INTO fills (
                    order_id, symbol, side, filled_quantity, fill_price, fee_paid,
                    realized_pnl, quote_balance, event_time, execution_source, trading_profile, session_id, tuning_version_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fill_result.order_id,
                    fill_result.symbol,
                    fill_result.side,
                    str(fill_result.filled_quantity),
                    str(fill_result.fill_price),
                    str(fill_result.fee_paid),
                    str(fill_result.realized_pnl),
                    str(fill_result.quote_balance),
                    event_time.isoformat(),
                    execution_source,
                    trading_profile,
                    session_id,
                    tuning_version_id,
                ),
            )
        finally:
            connection.close()

    def insert_position_snapshot(self, position: Position | None, event_time: datetime, symbol: str) -> None:
        """Persist a position snapshot for the current cycle."""

        quantity = Decimal("0")
        avg_entry_price = Decimal("0")
        realized_pnl = Decimal("0")
        quote_asset = "USDT"
        if position is not None:
            quantity = position.quantity
            avg_entry_price = position.avg_entry_price
            realized_pnl = position.realized_pnl
            quote_asset = position.quote_asset

        connection = self._open_connection()
        try:
            with connection:
                connection.execute(
                """
                INSERT INTO positions_snapshots (
                    symbol, quantity, avg_entry_price, realized_pnl, quote_asset, snapshot_time
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    str(quantity),
                    str(avg_entry_price),
                    str(realized_pnl),
                    quote_asset,
                    event_time.isoformat(),
                ),
            )
        finally:
            connection.close()

    def insert_pnl_snapshot(
        self,
        *,
        snapshot_time: datetime,
        equity: Decimal,
        total_pnl: Decimal,
        realized_pnl: Decimal,
        cash_balance: Decimal,
    ) -> None:
        """Persist a PnL snapshot."""

        connection = self._open_connection()
        try:
            with connection:
                connection.execute(
                """
                INSERT INTO pnl_snapshots (
                    snapshot_time, equity, total_pnl, realized_pnl, cash_balance
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    snapshot_time.isoformat(),
                    str(equity),
                    str(total_pnl),
                    str(realized_pnl),
                    str(cash_balance),
                ),
            )
        finally:
            connection.close()

    def insert_event(
        self,
        *,
        event_type: str,
        symbol: str,
        message: str,
        payload: dict[str, Any],
        event_time: datetime,
    ) -> None:
        """Persist a runner event."""

        connection = self._open_connection()
        try:
            with connection:
                connection.execute(
                """
                INSERT INTO runner_events (
                    event_type, symbol, message, payload_json, event_time
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event_type,
                    symbol,
                    message,
                    json.dumps(payload, default=str, sort_keys=True),
                    event_time.isoformat(),
                ),
            )
        finally:
            connection.close()

    def insert_futures_paper_event(
        self,
        *,
        event_type: str,
        symbol: str,
        payload: dict[str, Any],
        event_time: datetime,
    ) -> None:
        """Persist a paper Futures event separately from Spot runner events."""

        with self._connection_scope() as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO futures_paper_events (
                        event_type, symbol, payload_json, event_time
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        event_type,
                        symbol.upper(),
                        json.dumps(payload, default=str, sort_keys=True),
                        event_time.isoformat(),
                    ),
                )

    def insert_futures_paper_fill(
        self,
        *,
        order_id: str,
        status: str,
        symbol: str,
        side: str,
        filled_quantity: Decimal,
        fill_price: Decimal,
        fee_paid: Decimal,
        realized_pnl: Decimal,
        reason_codes: tuple[str, ...],
        event_time: datetime,
    ) -> None:
        """Persist a paper Futures fill/result row."""

        with self._connection_scope() as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO futures_paper_fills (
                        order_id, status, symbol, side, filled_quantity, fill_price,
                        fee_paid, realized_pnl, reason_codes, event_time
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        status,
                        symbol.upper(),
                        side,
                        str(filled_quantity),
                        str(fill_price),
                        str(fee_paid),
                        str(realized_pnl),
                        json.dumps(reason_codes),
                        event_time.isoformat(),
                    ),
                )

    def upsert_futures_paper_position(self, position: FuturesPaperPositionRecord) -> None:
        """Persist the current paper Futures position for one symbol."""

        with self._connection_scope() as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO futures_paper_positions (
                        symbol, side, quantity, entry_price, mark_price, leverage, margin_mode,
                        margin_used, unrealized_pnl, realized_pnl, liquidation_price_estimate,
                        opened_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol) DO UPDATE SET
                        side = excluded.side,
                        quantity = excluded.quantity,
                        entry_price = excluded.entry_price,
                        mark_price = excluded.mark_price,
                        leverage = excluded.leverage,
                        margin_mode = excluded.margin_mode,
                        margin_used = excluded.margin_used,
                        unrealized_pnl = excluded.unrealized_pnl,
                        realized_pnl = excluded.realized_pnl,
                        liquidation_price_estimate = excluded.liquidation_price_estimate,
                        opened_at = excluded.opened_at,
                        updated_at = excluded.updated_at
                    """,
                    (
                        position.symbol.upper(),
                        position.side,
                        str(position.quantity),
                        str(position.entry_price),
                        str(position.mark_price),
                        position.leverage,
                        position.margin_mode,
                        str(position.margin_used),
                        str(position.unrealized_pnl),
                        str(position.realized_pnl),
                        str(position.liquidation_price_estimate),
                        position.opened_at.isoformat(),
                        position.updated_at.isoformat(),
                    ),
                )

    def delete_futures_paper_position(self, symbol: str) -> None:
        """Delete the current paper Futures position for one symbol."""

        with self._connection_scope() as connection:
            with connection:
                connection.execute(
                    "DELETE FROM futures_paper_positions WHERE symbol = ?",
                    (symbol.upper(),),
                )

    def insert_futures_paper_pnl_snapshot(
        self,
        *,
        symbol: str,
        snapshot_time: datetime,
        unrealized_pnl: Decimal,
        realized_pnl: Decimal,
    ) -> None:
        """Persist a paper Futures PnL snapshot."""

        with self._connection_scope() as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO futures_paper_pnl_snapshots (
                        symbol, snapshot_time, unrealized_pnl, realized_pnl
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        symbol.upper(),
                        snapshot_time.isoformat(),
                        str(unrealized_pnl),
                        str(realized_pnl),
                    ),
                )

    def get_futures_paper_position(self, symbol: str) -> FuturesPaperPositionRecord | None:
        """Return the current paper Futures position for one symbol."""

        with self._connection_scope() as connection:
            row = connection.execute(
                """
                SELECT symbol, side, quantity, entry_price, mark_price, leverage, margin_mode,
                       margin_used, unrealized_pnl, realized_pnl, liquidation_price_estimate,
                       opened_at, updated_at
                FROM futures_paper_positions
                WHERE symbol = ?
                """,
                (symbol.upper(),),
            ).fetchone()
        if row is None:
            return None
        return FuturesPaperPositionRecord(
            symbol=row["symbol"],
            side=row["side"],
            quantity=_decimal(row["quantity"]),
            entry_price=_decimal(row["entry_price"]),
            mark_price=_decimal(row["mark_price"]),
            leverage=int(row["leverage"]),
            margin_mode=row["margin_mode"],
            margin_used=_decimal(row["margin_used"]),
            unrealized_pnl=_decimal(row["unrealized_pnl"]),
            realized_pnl=_decimal(row["realized_pnl"]),
            liquidation_price_estimate=_decimal(row["liquidation_price_estimate"]),
            opened_at=datetime.fromisoformat(row["opened_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def get_futures_paper_positions(self) -> list[FuturesPaperPositionRecord]:
        """Return all current paper Futures positions."""

        with self._connection_scope() as connection:
            rows = connection.execute(
                """
                SELECT symbol, side, quantity, entry_price, mark_price, leverage, margin_mode,
                       margin_used, unrealized_pnl, realized_pnl, liquidation_price_estimate,
                       opened_at, updated_at
                FROM futures_paper_positions
                ORDER BY symbol ASC
                """
            ).fetchall()
        return [
            FuturesPaperPositionRecord(
                symbol=row["symbol"],
                side=row["side"],
                quantity=_decimal(row["quantity"]),
                entry_price=_decimal(row["entry_price"]),
                mark_price=_decimal(row["mark_price"]),
                leverage=int(row["leverage"]),
                margin_mode=row["margin_mode"],
                margin_used=_decimal(row["margin_used"]),
                unrealized_pnl=_decimal(row["unrealized_pnl"]),
                realized_pnl=_decimal(row["realized_pnl"]),
                liquidation_price_estimate=_decimal(row["liquidation_price_estimate"]),
                opened_at=datetime.fromisoformat(row["opened_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            for row in rows
        ]

    def get_futures_paper_fills(
        self,
        *,
        symbol: str | None = None,
        limit: int | None = None,
    ) -> list[FuturesPaperFillRecord]:
        """Return recent paper Futures fills."""

        query = """
            SELECT order_id, status, symbol, side, filled_quantity, fill_price,
                   fee_paid, realized_pnl, reason_codes, event_time
            FROM futures_paper_fills
            WHERE 1 = 1
        """
        params: list[Any] = []
        if symbol is not None:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        query += " ORDER BY id DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        with self._connection_scope() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [
            FuturesPaperFillRecord(
                order_id=row["order_id"],
                status=row["status"],
                symbol=row["symbol"],
                side=row["side"],
                filled_quantity=_decimal(row["filled_quantity"]),
                fill_price=_decimal(row["fill_price"]),
                fee_paid=_decimal(row["fee_paid"]),
                realized_pnl=_decimal(row["realized_pnl"]),
                reason_codes=_parse_reason_codes(row["reason_codes"]),
                event_time=datetime.fromisoformat(row["event_time"]),
            )
            for row in rows
        ]

    def _apply_history_filters(
        self,
        *,
        query: str,
        params: list[Any],
        symbol: str | None,
        start_date: date | None,
        end_date: date | None,
        timestamp_column: str,
    ) -> tuple[str, list[Any]]:
        """Apply common symbol and date filters to a history query."""

        if symbol is not None:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        return self._apply_date_filters(
            query=query,
            params=params,
            start_date=start_date,
            end_date=end_date,
            timestamp_column=timestamp_column,
        )

    def _apply_date_filters(
        self,
        *,
        query: str,
        params: list[Any],
        start_date: date | None,
        end_date: date | None,
        timestamp_column: str,
    ) -> tuple[str, list[Any]]:
        """Apply common date filters to a history query."""

        if start_date is not None:
            query += f" AND {timestamp_column} >= ?"
            params.append(_start_of_day(start_date).isoformat())
        if end_date is not None:
            query += f" AND {timestamp_column} < ?"
            params.append(_next_day(end_date).isoformat())
        return query, params

    def get_trade_history(
        self,
        *,
        symbol: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[TradeRecord]:
        """Return persisted trade history, optionally filtered by symbol."""

        query = """
            SELECT order_id, symbol, side, requested_quantity, approved_quantity, filled_quantity,
                   status, risk_decision, reason_codes, fill_price, realized_pnl, quote_balance, event_time,
                   execution_source, trading_profile, session_id, tuning_version_id
            FROM trades
            WHERE 1 = 1
        """
        params: list[Any] = []
        query, params = self._apply_history_filters(
            query=query,
            params=params,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timestamp_column="event_time",
        )
        query += " ORDER BY id ASC"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend((limit, offset))
        with self._connection_scope() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [
            TradeRecord(
                order_id=row["order_id"],
                symbol=row["symbol"],
                side=row["side"],
                requested_quantity=_decimal(row["requested_quantity"]),
                approved_quantity=_decimal(row["approved_quantity"]),
                filled_quantity=_decimal(row["filled_quantity"]),
                status=row["status"],
                risk_decision=row["risk_decision"],
                reason_codes=_parse_reason_codes(row["reason_codes"]),
                fill_price=_decimal(row["fill_price"]),
                realized_pnl=_decimal(row["realized_pnl"]),
                quote_balance=_decimal(row["quote_balance"]),
                event_time=datetime.fromisoformat(row["event_time"]),
                execution_source=row["execution_source"] or "auto",
                trading_profile=row["trading_profile"] or "balanced",
                session_id=row["session_id"],
                tuning_version_id=row["tuning_version_id"],
            )
            for row in rows
        ]

    def count_trades(
        self,
        *,
        symbol: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> int:
        """Return the total number of trades matching the requested filters."""

        query = """
            SELECT COUNT(*) AS row_count
            FROM trades
            WHERE 1 = 1
        """
        params: list[Any] = []
        query, params = self._apply_history_filters(
            query=query,
            params=params,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timestamp_column="event_time",
        )
        with self._connection_scope() as connection:
            row = connection.execute(query, tuple(params)).fetchone()
        return int(row["row_count"]) if row is not None else 0

    def get_daily_pnl(self, day: date | None = None) -> Decimal:
        """Return the latest persisted total PnL for a UTC day."""

        target_day = day or datetime.now(tz=UTC).date()
        with self._connection_scope() as connection:
            rows = connection.execute(
                """
                SELECT total_pnl
                FROM pnl_snapshots
                WHERE date(snapshot_time) = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (target_day.isoformat(),),
            ).fetchall()
        if not rows:
            return Decimal("0")
        return _decimal(rows[0]["total_pnl"])

    def get_pnl_snapshots(self) -> list[PnlSnapshotRecord]:
        """Return persisted PnL snapshots."""

        return self.get_pnl_history_snapshots()

    def get_pnl_history_snapshots(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[PnlSnapshotRecord]:
        """Return persisted PnL snapshots with optional date filtering."""

        query = """
            SELECT snapshot_time, equity, total_pnl, realized_pnl, cash_balance
            FROM pnl_snapshots
            WHERE 1 = 1
        """
        params: list[Any] = []
        query, params = self._apply_date_filters(
            query=query,
            params=params,
            start_date=start_date,
            end_date=end_date,
            timestamp_column="snapshot_time",
        )
        query += " ORDER BY id ASC"
        with self._connection_scope() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [
            PnlSnapshotRecord(
                snapshot_time=datetime.fromisoformat(row["snapshot_time"]),
                equity=_decimal(row["equity"]),
                total_pnl=_decimal(row["total_pnl"]),
                realized_pnl=_decimal(row["realized_pnl"]),
                cash_balance=_decimal(row["cash_balance"]),
            )
            for row in rows
        ]

    def get_equity_history(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[EquityHistoryPoint]:
        """Return persisted equity history points."""

        return [
            EquityHistoryPoint(
                snapshot_time=snapshot.snapshot_time,
                equity=snapshot.equity,
            )
            for snapshot in self.get_pnl_history_snapshots(
                start_date=start_date,
                end_date=end_date,
            )
        ]

    def get_pnl_history(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[PnlHistoryPoint]:
        """Return persisted total and realized PnL history points."""

        return [
            PnlHistoryPoint(
                snapshot_time=snapshot.snapshot_time,
                total_pnl=snapshot.total_pnl,
                realized_pnl=snapshot.realized_pnl,
            )
            for snapshot in self.get_pnl_history_snapshots(
                start_date=start_date,
                end_date=end_date,
            )
        ]

    def get_daily_pnl_history(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[DailyPnlRecord]:
        """Return the latest persisted PnL point for each UTC day."""

        latest_by_day: dict[date, PnlSnapshotRecord] = {}
        for snapshot in self.get_pnl_history_snapshots(
            start_date=start_date,
            end_date=end_date,
        ):
            latest_by_day[snapshot.snapshot_time.date()] = snapshot

        return [
            DailyPnlRecord(
                day=day,
                total_pnl=latest_by_day[day].total_pnl,
                realized_pnl=latest_by_day[day].realized_pnl,
            )
            for day in sorted(latest_by_day)
        ]

    def get_drawdown_summary(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> DrawdownSummary:
        """Return derived drawdown summary and time series from equity history."""

        points: list[DrawdownPoint] = []
        max_drawdown = Decimal("0")
        max_drawdown_pct = Decimal("0")
        running_peak = Decimal("0")

        for snapshot in self.get_pnl_history_snapshots(
            start_date=start_date,
            end_date=end_date,
        ):
            running_peak = max(running_peak, snapshot.equity)
            drawdown = max(running_peak - snapshot.equity, Decimal("0"))
            drawdown_pct = _drawdown_pct(drawdown, running_peak)
            max_drawdown = max(max_drawdown, drawdown)
            max_drawdown_pct = max(max_drawdown_pct, drawdown_pct)
            points.append(
                DrawdownPoint(
                    snapshot_time=snapshot.snapshot_time,
                    equity=snapshot.equity,
                    peak_equity=running_peak,
                    drawdown=drawdown,
                    drawdown_pct=drawdown_pct,
                )
            )

        if not points:
            return DrawdownSummary(
                current_drawdown=Decimal("0"),
                current_drawdown_pct=Decimal("0"),
                max_drawdown=Decimal("0"),
                max_drawdown_pct=Decimal("0"),
                points=[],
            )

        latest_point = points[-1]
        return DrawdownSummary(
            current_drawdown=latest_point.drawdown,
            current_drawdown_pct=latest_point.drawdown_pct,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            points=points,
        )

    def get_latest_pnl_snapshot(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> PnlSnapshotRecord | None:
        """Return the latest persisted PnL snapshot within an optional date range."""

        query = """
            SELECT snapshot_time, equity, total_pnl, realized_pnl, cash_balance
            FROM pnl_snapshots
            WHERE 1 = 1
        """
        params: list[Any] = []
        query, params = self._apply_date_filters(
            query=query,
            params=params,
            start_date=start_date,
            end_date=end_date,
            timestamp_column="snapshot_time",
        )
        query += " ORDER BY id DESC LIMIT 1"
        with self._connection_scope() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        if not rows:
            return None

        row = rows[0]
        return PnlSnapshotRecord(
            snapshot_time=datetime.fromisoformat(row["snapshot_time"]),
            equity=_decimal(row["equity"]),
            total_pnl=_decimal(row["total_pnl"]),
            realized_pnl=_decimal(row["realized_pnl"]),
            cash_balance=_decimal(row["cash_balance"]),
        )

    def get_current_positions(self) -> list[PositionSnapshotRecord]:
        """Return the latest non-zero position snapshot for each symbol."""

        with self._connection_scope() as connection:
            rows = connection.execute(
                """
                SELECT p.symbol, p.quantity, p.avg_entry_price, p.realized_pnl, p.quote_asset, p.snapshot_time
                FROM positions_snapshots AS p
                INNER JOIN (
                    SELECT symbol, MAX(id) AS max_id
                    FROM positions_snapshots
                    GROUP BY symbol
                ) AS latest
                    ON latest.max_id = p.id
                WHERE CAST(p.quantity AS REAL) != 0
                ORDER BY p.symbol ASC
                """
            ).fetchall()
        return [
            PositionSnapshotRecord(
                symbol=row["symbol"],
                quantity=_decimal(row["quantity"]),
                avg_entry_price=_decimal(row["avg_entry_price"]),
                realized_pnl=_decimal(row["realized_pnl"]),
                quote_asset=row["quote_asset"],
                snapshot_time=datetime.fromisoformat(row["snapshot_time"]),
            )
            for row in rows
        ]

    def get_fill_history(
        self,
        *,
        symbol: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[FillRecord]:
        """Return persisted fills."""

        with self._connection_scope() as connection:
            rows = connection.execute(
                *self._build_fill_query(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date,
                    limit=limit,
                    offset=offset,
                )
            ).fetchall()
        return [
            FillRecord(
                order_id=row["order_id"],
                symbol=row["symbol"],
                side=row["side"],
                filled_quantity=_decimal(row["filled_quantity"]),
                fill_price=_decimal(row["fill_price"]),
                fee_paid=_decimal(row["fee_paid"]),
                realized_pnl=_decimal(row["realized_pnl"]),
                quote_balance=_decimal(row["quote_balance"]),
                event_time=datetime.fromisoformat(row["event_time"]),
                execution_source=row["execution_source"] or "auto",
                trading_profile=row["trading_profile"] or "balanced",
                session_id=row["session_id"],
                tuning_version_id=row["tuning_version_id"],
            )
            for row in rows
        ]

    def _build_fill_query(
        self,
        *,
        symbol: str | None,
        start_date: date | None,
        end_date: date | None,
        limit: int | None,
        offset: int,
    ) -> tuple[str, tuple[Any, ...]]:
        """Build a filtered fills query."""

        query = """
            SELECT order_id, symbol, side, filled_quantity, fill_price, fee_paid,
                   realized_pnl, quote_balance, event_time, execution_source, trading_profile, session_id, tuning_version_id
            FROM fills
            WHERE 1 = 1
        """
        params: list[Any] = []
        query, params = self._apply_history_filters(
            query=query,
            params=params,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timestamp_column="event_time",
        )
        query += " ORDER BY id ASC"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend((limit, offset))
        return query, tuple(params)

    def count_fills(
        self,
        *,
        symbol: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> int:
        """Return the total number of fills matching the requested filters."""

        query = """
            SELECT COUNT(*) AS row_count
            FROM fills
            WHERE 1 = 1
        """
        params: list[Any] = []
        query, params = self._apply_history_filters(
            query=query,
            params=params,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timestamp_column="event_time",
        )
        with self._connection_scope() as connection:
            row = connection.execute(query, tuple(params)).fetchone()
        return int(row["row_count"]) if row is not None else 0

    def get_runner_events(
        self,
        *,
        symbol: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[RunnerEventRecord]:
        """Return persisted runner events."""

        query = """
            SELECT event_type, symbol, message, payload_json, event_time
            FROM runner_events
            WHERE 1 = 1
        """
        params: list[Any] = []
        query, params = self._apply_history_filters(
            query=query,
            params=params,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timestamp_column="event_time",
        )
        query += " ORDER BY id ASC"
        if limit is not None:
            query += " LIMIT ? OFFSET ?"
            params.extend((limit, offset))
        with self._connection_scope() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [
            RunnerEventRecord(
                event_type=row["event_type"],
                symbol=row["symbol"],
                message=row["message"],
                payload_json=row["payload_json"],
                event_time=datetime.fromisoformat(row["event_time"]),
            )
            for row in rows
        ]

    def count_runner_events(
        self,
        *,
        symbol: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> int:
        """Return the total number of runner events matching the requested filters."""

        query = """
            SELECT COUNT(*) AS row_count
            FROM runner_events
            WHERE 1 = 1
        """
        params: list[Any] = []
        query, params = self._apply_history_filters(
            query=query,
            params=params,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            timestamp_column="event_time",
        )
        with self._connection_scope() as connection:
            row = connection.execute(query, tuple(params)).fetchone()
        return int(row["row_count"]) if row is not None else 0
