"""Post-signal outcome tracking for generated advisory signals."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from app.data.heatmap_provider import HeatmapProvider, enrich_signal_with_heatmap
from app.storage.models import HistoricalCandleRecord, SignalOutcomeRecord, SignalOutcomeSnapshotRecord
from app.storage.repositories import StorageRepository

LOGGER = logging.getLogger(__name__)

SIGNAL_OUTCOME_HORIZONS: dict[str, timedelta] = {
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "24h": timedelta(hours=24),
}
TAKE_PROFIT_PCT = Decimal("1.5000")
STOP_LOSS_PCT = Decimal("1.0000")
SWEEP_THRESHOLD_PCT = Decimal("0.2500")


@dataclass(slots=True, frozen=True)
class SignalSnapshotInput:
    """Input payload for one generated advisory signal snapshot."""

    symbol: str
    source: str
    signal_type: str
    confidence: int
    entry_price: Decimal | None
    liquidity_bias: str | None = None
    sweep_risk: str | None = None
    nearest_liquidity_above: Decimal | None = None
    nearest_liquidity_below: Decimal | None = None
    funding_rate: Decimal | None = None
    open_interest: Decimal | None = None
    notes: str = ""
    timestamp: datetime | None = None
    heatmap_provider: HeatmapProvider | None = None


def snapshot_record_from_signal(payload: SignalSnapshotInput) -> SignalOutcomeSnapshotRecord:
    """Build a persisted snapshot record with a stable UUID."""

    enrichment = enrich_signal_with_heatmap(
        symbol=payload.symbol,
        price=payload.entry_price,
        base_signal_type=payload.signal_type,
        base_confidence=payload.confidence,
        provider=payload.heatmap_provider,
    )
    return SignalOutcomeSnapshotRecord(
        id=str(uuid4()),
        symbol=payload.symbol.upper(),
        timestamp=payload.timestamp or datetime.now(tz=UTC),
        source=payload.source,
        signal_type=_normalize_signal_type(payload.signal_type),
        confidence=max(0, min(100, payload.confidence)),
        entry_price=payload.entry_price,
        liquidity_bias=payload.liquidity_bias,
        sweep_risk=payload.sweep_risk,
        nearest_liquidity_above=payload.nearest_liquidity_above,
        nearest_liquidity_below=payload.nearest_liquidity_below,
        funding_rate=payload.funding_rate,
        open_interest=payload.open_interest,
        notes=payload.notes[:500],
        heatmap_liquidity_above=enrichment.heatmap_liquidity_above,
        heatmap_liquidity_below=enrichment.heatmap_liquidity_below,
        heatmap_intensity_score=enrichment.heatmap_intensity_score,
        heatmap_bias=enrichment.heatmap_bias,
        base_signal_type=enrichment.base_signal_type,
        heatmap_signal_type=enrichment.heatmap_signal_type,
        base_confidence=enrichment.base_confidence,
        heatmap_confidence=enrichment.heatmap_confidence,
        heatmap_alignment=enrichment.heatmap_alignment,
        heatmap_explanation=enrichment.heatmap_explanation,
        heatmap_provider=enrichment.heatmap_provider,
        heatmap_data_quality=enrichment.heatmap_data_quality,
        heatmap_is_real_data=enrichment.heatmap_is_real_data,
        heatmap_provider_status=enrichment.heatmap_provider_status,
        liquidation_pressure=enrichment.liquidation_pressure,
        liquidation_imbalance=enrichment.liquidation_imbalance,
    )


def persist_signal_snapshot(*, repository: StorageRepository, payload: SignalSnapshotInput) -> str | None:
    """Persist one generated signal snapshot without affecting execution."""

    return repository.insert_signal_outcome_snapshot(snapshot_record_from_signal(payload))


def evaluate_pending_signal_outcomes(
    *,
    repository: StorageRepository,
    as_of: datetime | None = None,
) -> int:
    """Evaluate matured post-signal snapshots for fixed horizons using stored candles."""

    evaluation_time = as_of or datetime.now(tz=UTC)
    snapshots = repository.get_signal_outcome_snapshots()
    existing = repository.get_signal_outcomes(signal_ids=[snapshot.id for snapshot in snapshots])
    completed = {
        (outcome.signal_id, outcome.horizon)
        for outcome in existing
        if outcome.outcome_state in {"win", "loss", "neutral", "insufficient_data"}
    }
    written = 0
    for snapshot in snapshots:
        for horizon in SIGNAL_OUTCOME_HORIZONS:
            if (snapshot.id, horizon) in completed:
                continue
            outcome = evaluate_signal_outcome(snapshot=snapshot, repository=repository, horizon=horizon, as_of=evaluation_time)
            repository.upsert_signal_outcome(outcome)
            written += 1
    return written


def evaluate_signal_outcome(
    *,
    snapshot: SignalOutcomeSnapshotRecord,
    repository: StorageRepository,
    horizon: str,
    as_of: datetime | None = None,
) -> SignalOutcomeRecord:
    """Calculate one deterministic fixed-horizon outcome for a stored signal."""

    if horizon not in SIGNAL_OUTCOME_HORIZONS:
        raise ValueError(f"Unsupported signal outcome horizon: {horizon}")
    evaluation_time = as_of or datetime.now(tz=UTC)
    target_time = snapshot.timestamp + SIGNAL_OUTCOME_HORIZONS[horizon]
    if evaluation_time < target_time:
        return _empty_outcome(snapshot=snapshot, horizon=horizon, state="pending", evaluated_at=evaluation_time)

    candles = _load_candles(repository=repository, symbol=snapshot.symbol, start=snapshot.timestamp, end=target_time)
    future = next((candle for candle in candles if candle.close_time >= target_time), None)
    if snapshot.entry_price is None or snapshot.entry_price <= Decimal("0") or future is None or not candles:
        return _empty_outcome(snapshot=snapshot, horizon=horizon, state="insufficient_data", evaluated_at=evaluation_time)

    entry = snapshot.entry_price
    raw_change = _pct_change(entry=entry, price=future.close_price)
    max_upside = max((_pct_change(entry=entry, price=candle.high_price) for candle in candles), default=Decimal("0"))
    max_downside = min((_pct_change(entry=entry, price=candle.low_price) for candle in candles), default=Decimal("0"))
    first_hit, time_to_hit = _tp_sl_first_hit(snapshot=snapshot, candles=candles)
    sweep_actual = _actual_sweep_direction(entry=entry, candles=candles)
    predicted_sweep = _predicted_sweep_direction(snapshot)
    sweep_correct = _sweep_prediction_correct(snapshot=snapshot, actual=sweep_actual)
    base_correct = _direction_correct(snapshot.base_signal_type or snapshot.signal_type, raw_change)
    heatmap_correct = _direction_correct(snapshot.heatmap_signal_type or snapshot.signal_type, raw_change)
    direction_correct = base_correct
    did_improve = _heatmap_improved(base_correct=base_correct, heatmap_correct=heatmap_correct)
    did_reduce_loss = _heatmap_reduced_loss(snapshot=snapshot, raw_change=raw_change, base_correct=base_correct, heatmap_correct=heatmap_correct)
    state = _outcome_state(direction_correct)
    return SignalOutcomeRecord(
        id=None,
        signal_id=snapshot.id,
        horizon=horizon,
        future_price=future.close_price,
        price_change_percent=_quantize(raw_change),
        max_upside_percent=_quantize(max_upside),
        max_downside_percent=_quantize(max_downside),
        did_price_hit_tp=first_hit == "take_profit",
        did_price_hit_sl=first_hit == "stop_loss",
        direction_correct=direction_correct,
        volatility_range=_quantize(max_upside - max_downside),
        first_hit=first_hit,
        time_to_hit_seconds=time_to_hit,
        sweep_direction_actual=sweep_actual,
        sweep_prediction_correct=sweep_correct,
        outcome_state=state,
        evaluated_at=evaluation_time,
        base_signal_correct=base_correct,
        heatmap_signal_correct=heatmap_correct,
        did_heatmap_improve_result=did_improve,
        did_heatmap_reduce_loss=did_reduce_loss,
        predicted_sweep_direction=predicted_sweep,
        actual_sweep_direction=sweep_actual,
    )


class SignalOutcomeBackgroundService:
    """Small scheduled evaluator for post-signal outcomes."""

    def __init__(self, *, database_url: str, interval_seconds: int = 60) -> None:
        self._database_url = database_url
        self._interval_seconds = interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._closed = asyncio.Event()

    def start(self) -> None:
        """Start the background outcome evaluator if it is not already running."""

        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="signal-outcome-evaluator")

    async def close(self) -> None:
        """Stop the background evaluator."""

        self._closed.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        while not self._closed.is_set():
            try:
                repository = StorageRepository(self._database_url)
                try:
                    evaluate_pending_signal_outcomes(repository=repository)
                    # Imported lazily to keep the existing outcome module independent
                    # while sharing its scheduled persistence lifecycle.
                    from app.monitoring.signal_timing_baseline import (
                        evaluate_pending_signal_timing_baselines,
                    )

                    evaluate_pending_signal_timing_baselines(repository=repository)
                finally:
                    repository.close()
            except Exception:
                LOGGER.exception("Post-signal outcome background evaluation failed.")
            try:
                await asyncio.wait_for(self._closed.wait(), timeout=self._interval_seconds)
            except asyncio.TimeoutError:
                continue


def _load_candles(
    *,
    repository: StorageRepository,
    symbol: str,
    start: datetime,
    end: datetime,
) -> list[HistoricalCandleRecord]:
    candles: list[HistoricalCandleRecord] = []
    for interval in ("1m", "5m", "15m", "1h"):
        candles.extend(
            repository.get_historical_candles(
                symbol=symbol,
                interval=interval,
                start_time=start,
                end_time=end,
            )
        )
    unique = {(candle.interval, candle.open_time): candle for candle in candles}
    return sorted(unique.values(), key=lambda candle: (candle.close_time, candle.interval))


def _tp_sl_first_hit(
    *,
    snapshot: SignalOutcomeSnapshotRecord,
    candles: Sequence[HistoricalCandleRecord],
) -> tuple[str | None, int | None]:
    if snapshot.entry_price is None or snapshot.entry_price <= Decimal("0"):
        return None, None
    signal_type = _normalize_signal_type(snapshot.signal_type)
    if signal_type not in {"BUY", "SELL"}:
        return None, None
    entry = snapshot.entry_price
    if signal_type == "BUY":
        tp_level = entry * Decimal("1.015")
        sl_level = entry * Decimal("0.990")
        for candle in candles:
            tp_hit = candle.high_price >= tp_level
            sl_hit = candle.low_price <= sl_level
            hit = _conservative_first_hit(tp_hit=tp_hit, sl_hit=sl_hit)
            if hit is not None:
                return hit, max(0, int((candle.close_time - snapshot.timestamp).total_seconds()))
        return None, None
    tp_level = entry * Decimal("0.985")
    sl_level = entry * Decimal("1.010")
    for candle in candles:
        tp_hit = candle.low_price <= tp_level
        sl_hit = candle.high_price >= sl_level
        hit = _conservative_first_hit(tp_hit=tp_hit, sl_hit=sl_hit)
        if hit is not None:
            return hit, max(0, int((candle.close_time - snapshot.timestamp).total_seconds()))
    return None, None


def _conservative_first_hit(*, tp_hit: bool, sl_hit: bool) -> str | None:
    if sl_hit:
        return "stop_loss"
    if tp_hit:
        return "take_profit"
    return None


def _actual_sweep_direction(*, entry: Decimal, candles: Sequence[HistoricalCandleRecord]) -> str:
    up_level = entry * (Decimal("1") + (SWEEP_THRESHOLD_PCT / Decimal("100")))
    down_level = entry * (Decimal("1") - (SWEEP_THRESHOLD_PCT / Decimal("100")))
    for candle in candles:
        up_hit = candle.high_price >= up_level
        down_hit = candle.low_price <= down_level
        if up_hit and down_hit:
            up_distance = abs(candle.high_price - entry)
            down_distance = abs(entry - candle.low_price)
            return "up" if up_distance >= down_distance else "down"
        if up_hit:
            return "up"
        if down_hit:
            return "down"
    return "none"


def _sweep_prediction_correct(snapshot: SignalOutcomeSnapshotRecord, *, actual: str) -> bool | None:
    predicted = _predicted_sweep_direction(snapshot)
    if predicted == "none":
        return None
    return actual == predicted


def _predicted_sweep_direction(snapshot: SignalOutcomeSnapshotRecord) -> str:
    heatmap_bias = (snapshot.heatmap_bias or "").lower()
    if heatmap_bias == "downside_sweep":
        return "down"
    if heatmap_bias == "upside_squeeze":
        return "up"
    sweep_risk = (snapshot.sweep_risk or "").lower()
    liquidity_bias = (snapshot.liquidity_bias or "").lower()
    if sweep_risk == "downside_sweep" or liquidity_bias == "downside_sweep_risk":
        return "down"
    if sweep_risk == "upside_sweep" or liquidity_bias == "upside_squeeze_risk":
        return "up"
    return "none"


def _direction_correct(signal_type: str, price_change: Decimal) -> bool | None:
    normalized = _normalize_signal_type(signal_type)
    if normalized == "BUY":
        return price_change > Decimal("0")
    if normalized == "SELL":
        return price_change < Decimal("0")
    return None


def _heatmap_improved(*, base_correct: bool | None, heatmap_correct: bool | None) -> bool | None:
    if base_correct is None or heatmap_correct is None:
        return None
    return heatmap_correct and not base_correct


def _heatmap_reduced_loss(
    *,
    snapshot: SignalOutcomeSnapshotRecord,
    raw_change: Decimal,
    base_correct: bool | None,
    heatmap_correct: bool | None,
) -> bool | None:
    if base_correct is not False:
        return False if base_correct is not None else None
    heatmap_signal = _normalize_signal_type(snapshot.heatmap_signal_type or snapshot.signal_type)
    if heatmap_correct is True:
        return True
    return heatmap_signal in {"WAIT", "AVOID"} and _normalize_signal_type(snapshot.base_signal_type or snapshot.signal_type) in {"BUY", "SELL"} and raw_change != Decimal("0")


def _outcome_state(direction_correct: bool | None) -> str:
    if direction_correct is True:
        return "win"
    if direction_correct is False:
        return "loss"
    return "neutral"


def _empty_outcome(
    *,
    snapshot: SignalOutcomeSnapshotRecord,
    horizon: str,
    state: str,
    evaluated_at: datetime,
) -> SignalOutcomeRecord:
    return SignalOutcomeRecord(
        id=None,
        signal_id=snapshot.id,
        horizon=horizon,
        future_price=None,
        price_change_percent=None,
        max_upside_percent=None,
        max_downside_percent=None,
        did_price_hit_tp=False,
        did_price_hit_sl=False,
        direction_correct=None,
        volatility_range=None,
        first_hit=None,
        time_to_hit_seconds=None,
        sweep_direction_actual="none",
        sweep_prediction_correct=None,
        outcome_state=state,
        evaluated_at=evaluated_at,
        base_signal_correct=None,
        heatmap_signal_correct=None,
        did_heatmap_improve_result=None,
        did_heatmap_reduce_loss=None,
        predicted_sweep_direction=_predicted_sweep_direction(snapshot),
        actual_sweep_direction="none",
    )


def _normalize_signal_type(value: str) -> str:
    normalized = value.strip().upper()
    if normalized in {"BUY", "LONG"}:
        return "BUY"
    if normalized in {"SELL", "SHORT", "SELL_EXIT", "EXIT"}:
        return "SELL"
    if normalized == "AVOID":
        return "AVOID"
    return "WAIT"


def _pct_change(*, entry: Decimal, price: Decimal) -> Decimal:
    if entry <= Decimal("0"):
        return Decimal("0")
    return ((price - entry) / entry) * Decimal("100")


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
