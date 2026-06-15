from datetime import UTC, datetime
from decimal import Decimal

from app.monitoring.performance_summary import build_post_signal_performance_summary
from app.storage.models import SignalOutcomeRecord, SignalOutcomeSnapshotRecord


def _snapshot(
    signal_id: str,
    *,
    signal_type: str,
    confidence: int,
    source: str,
    liquidity_bias: str = "neutral",
) -> SignalOutcomeSnapshotRecord:
    return SignalOutcomeSnapshotRecord(
        id=signal_id,
        symbol="BTCUSDT",
        timestamp=datetime(2024, 3, 9, 10, 0, tzinfo=UTC),
        source=source,
        signal_type=signal_type,
        confidence=confidence,
        entry_price=Decimal("100"),
        liquidity_bias=liquidity_bias,
        sweep_risk="none",
        nearest_liquidity_above=None,
        nearest_liquidity_below=None,
        funding_rate=None,
        open_interest=None,
        notes="test",
        base_signal_type=signal_type,
        heatmap_signal_type=signal_type,
        base_confidence=confidence,
        heatmap_confidence=confidence,
        heatmap_data_quality="mock",
    )


def _outcome(
    signal_id: str,
    *,
    direction_correct: bool,
    return_pct: Decimal,
    tp: bool,
    sl: bool,
    base_signal_correct: bool | None = None,
    heatmap_signal_correct: bool | None = None,
    sweep_prediction_correct: bool | None = None,
) -> SignalOutcomeRecord:
    return SignalOutcomeRecord(
        id=None,
        signal_id=signal_id,
        horizon="15m",
        future_price=Decimal("101"),
        price_change_percent=return_pct,
        max_upside_percent=Decimal("2.0000"),
        max_downside_percent=Decimal("-0.5000"),
        did_price_hit_tp=tp,
        did_price_hit_sl=sl,
        direction_correct=direction_correct,
        volatility_range=Decimal("2.5000"),
        first_hit="take_profit" if tp else "stop_loss" if sl else None,
        time_to_hit_seconds=300 if tp or sl else None,
        sweep_direction_actual="none",
        sweep_prediction_correct=sweep_prediction_correct,
        outcome_state="win" if direction_correct else "loss",
        evaluated_at=datetime(2024, 3, 9, 10, 20, tzinfo=UTC),
        base_signal_correct=direction_correct if base_signal_correct is None else base_signal_correct,
        heatmap_signal_correct=direction_correct if heatmap_signal_correct is None else heatmap_signal_correct,
    )


def test_performance_summary_computes_core_metrics() -> None:
    snapshots = [
        _snapshot("a", signal_type="BUY", confidence=80, source="assistant", liquidity_bias="bullish"),
        _snapshot("b", signal_type="SELL", confidence=45, source="scanner", liquidity_bias="bearish"),
        _snapshot("c", signal_type="WAIT", confidence=35, source="eligibility"),
    ]
    outcomes = [
        _outcome("a", direction_correct=True, return_pct=Decimal("1.5000"), tp=True, sl=False),
        _outcome("b", direction_correct=False, return_pct=Decimal("0.7000"), tp=False, sl=True),
    ]

    summary = build_post_signal_performance_summary(snapshots=snapshots, outcomes=outcomes)

    assert summary.total_signals == 3
    assert summary.evaluated_signals == 2
    assert summary.win_rate == Decimal("50.0000")
    assert summary.avg_return == Decimal("1.1000")
    assert summary.tp_hit_rate == Decimal("50.0000")
    assert summary.sl_hit_rate == Decimal("50.0000")
    assert summary.base_win_rate == Decimal("50.0000")
    assert summary.heatmap_win_rate == Decimal("50.0000")
    assert summary.delta_win_rate == Decimal("0.0000")


def test_performance_summary_computes_heatmap_effectiveness_metrics() -> None:
    snapshots = [
        _snapshot("a", signal_type="BUY", confidence=80, source="assistant", liquidity_bias="bullish"),
        _snapshot("b", signal_type="BUY", confidence=75, source="scanner", liquidity_bias="neutral"),
    ]
    snapshots[1].heatmap_signal_type = "SELL"
    outcomes = [
        _outcome(
            "a",
            direction_correct=True,
            return_pct=Decimal("1.0000"),
            tp=True,
            sl=False,
            sweep_prediction_correct=True,
        ),
        _outcome(
            "b",
            direction_correct=False,
            return_pct=Decimal("-1.0000"),
            tp=False,
            sl=True,
            base_signal_correct=False,
            heatmap_signal_correct=True,
            sweep_prediction_correct=True,
        ),
    ]

    summary = build_post_signal_performance_summary(snapshots=snapshots, outcomes=outcomes)

    assert summary.base_win_rate == Decimal("50.0000")
    assert summary.heatmap_win_rate == Decimal("100.0000")
    assert summary.delta_win_rate == Decimal("50.0000")
    assert summary.heatmap_accuracy_on_sweep_prediction == Decimal("100.0000")
    assert summary.heatmap_false_signal_rate == Decimal("0.0000")


def test_performance_summary_segments_by_heatmap_data_quality() -> None:
    snapshots = [
        _snapshot("a", signal_type="BUY", confidence=80, source="assistant"),
        _snapshot("b", signal_type="SELL", confidence=80, source="scanner"),
    ]
    snapshots[0].heatmap_data_quality = "mock"
    snapshots[1].heatmap_data_quality = "event_based"
    outcomes = [
        _outcome("a", direction_correct=True, return_pct=Decimal("1.0000"), tp=True, sl=False),
        _outcome("b", direction_correct=False, return_pct=Decimal("-1.0000"), tp=False, sl=True),
    ]

    summary = build_post_signal_performance_summary(snapshots=snapshots, outcomes=outcomes)

    assert summary.heatmap_signal_count_by_data_quality == {"event_based": 1, "mock": 1}
    assert summary.win_rate_by_heatmap_data_quality["mock"] == Decimal("100.0000")
    assert summary.win_rate_by_heatmap_data_quality["event_based"] == Decimal("0.0000")
    assert summary.avg_return_by_data_quality["mock"] == Decimal("1.0000")


def test_performance_summary_segments_by_source_signal_type_confidence_and_liquidity() -> None:
    snapshots = [
        _snapshot("a", signal_type="BUY", confidence=80, source="assistant", liquidity_bias="bullish"),
        _snapshot("b", signal_type="SELL", confidence=45, source="scanner", liquidity_bias="bearish"),
    ]
    outcomes = [
        _outcome("a", direction_correct=True, return_pct=Decimal("1.5000"), tp=True, sl=False),
        _outcome("b", direction_correct=False, return_pct=Decimal("-0.5000"), tp=False, sl=True),
    ]

    summary = build_post_signal_performance_summary(snapshots=snapshots, outcomes=outcomes)

    assert {item.name for item in summary.by_source} == {"assistant", "scanner"}
    assert {item.name for item in summary.by_signal_type} == {"BUY", "SELL"}
    assert {item.name for item in summary.by_confidence_bucket} == {"70-84", "0-49"}
    assert {item.name for item in summary.by_liquidity_bias} == {"bullish", "bearish"}
