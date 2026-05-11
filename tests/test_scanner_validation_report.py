from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dashboard_api import get_dashboard_data_access
from app.api.dependencies import DashboardDataAccess
from app.main import app
from app.market_data.candles import Candle
from app.monitoring.futures_opportunity_scanner import FuturesOpportunityScanReport, FuturesPaperSignal
from app.monitoring.scanner_validation_report import (
    SCANNER_VALIDATION_HORIZONS,
    build_scanner_validation_report,
    evaluate_pending_scanner_snapshots,
    evaluate_scanner_snapshot_outcome,
    persist_scanner_validation_snapshots,
)
from app.storage import StorageRepository
from app.storage.models import ScannerValidationSnapshotRecord


def _db_path() -> Path:
    base = Path("tests/.tmp_storage")
    base.mkdir(parents=True, exist_ok=True)
    return (base / f"scanner_validation_{uuid4().hex}.sqlite").resolve()


def _signal(
    *,
    symbol: str,
    direction: str,
    score: int,
    price: Decimal = Decimal("100"),
    timestamp: datetime,
) -> FuturesPaperSignal:
    return FuturesPaperSignal(
        symbol=symbol,
        direction=direction,
        opportunity_score=score,
        direction_score=score,
        momentum_score=80,
        trend_score=82,
        volatility_quality_score=75,
        liquidity_score=90,
        risk_score=72,
        validation_score=None,
        confidence=score - 5,
        evidence_strength="unvalidated",
        trend="bullish" if direction == "long" else "bearish",
        momentum="positive" if direction == "long" else "negative",
        best_horizon="15m",
        risk_grade="medium",
        regime="trending_up" if direction == "long" else "trending_down",
        current_price=price,
        reason="Current market structure supports a paper scanner candidate.",
        invalidation_hint=None,
        suggested_entry_zone=None,
        suggested_stop_loss=price - Decimal("2") if direction == "long" else price + Decimal("2"),
        suggested_take_profit=price + Decimal("3") if direction == "long" else price - Decimal("3"),
        estimated_fee_impact=Decimal("0.08"),
        leverage_suggestion="1x paper-only",
        liquidation_safety_note="Paper futures only.",
        similar_setup_summary="No internal evidence yet.",
        eligibility_status="insufficient_data",
        warnings=(),
        timestamp=timestamp,
    )


def _snapshot(
    *,
    direction: str,
    price: Decimal,
    timestamp: datetime,
    score: int = 80,
    stop_loss: Decimal | None = None,
    take_profit: Decimal | None = None,
    group: str = "top_long",
) -> ScannerValidationSnapshotRecord:
    return ScannerValidationSnapshotRecord(
        id=None,
        scan_id=f"scan_{uuid4().hex}",
        symbol="BTCUSDT",
        direction=direction,
        price_at_scan=price,
        opportunity_score=score,
        confidence=75,
        horizon="15m",
        risk_grade="medium",
        trend_score=80,
        momentum_score=80,
        volatility_quality_score=80,
        liquidity_score=80,
        risk_score=80,
        direction_score=80,
        validation_score=None,
        evidence_strength="unvalidated",
        stop_loss=stop_loss,
        take_profit=take_profit,
        timestamp=timestamp,
        rank_position=1,
        candidate_group=group,
        regime_label="trending_up",
    )


def _candle(
    *,
    symbol: str = "BTCUSDT",
    open_time: datetime,
    close: Decimal,
    high: Decimal | None = None,
    low: Decimal | None = None,
    timeframe: str = "15m",
) -> Candle:
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        open=close,
        high=high or close,
        low=low or close,
        close=close,
        volume=Decimal("100"),
        quote_volume=Decimal("1000000"),
        open_time=open_time,
        close_time=open_time + timedelta(minutes=15),
        event_time=open_time + timedelta(minutes=15),
        trade_count=100,
        is_closed=True,
    )


def test_scanner_snapshot_persistence_and_random_baseline_creation() -> None:
    repository = StorageRepository(f"sqlite:///{_db_path()}")
    base = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    report = FuturesOpportunityScanReport(
        generated_at=base,
        scan_state="ready",
        long_candidates=[_signal(symbol="BTCUSDT", direction="long", score=86, timestamp=base)],
        short_candidates=[_signal(symbol="ETHUSDT", direction="short", score=83, timestamp=base)],
        neutral_candidates=[_signal(symbol="BNBUSDT", direction="wait", score=45, timestamp=base)],
        scanned_count=3,
    )
    try:
        scan_id, inserted = persist_scanner_validation_snapshots(
            repository=repository,
            report=report,
            random_baseline_size=2,
            scan_id="scan_test",
        )
        snapshots = repository.get_scanner_validation_snapshots()
    finally:
        repository.close()

    assert scan_id == "scan_test"
    assert inserted == 5
    assert {snapshot.candidate_group for snapshot in snapshots} == {
        "top_long",
        "top_short",
        "neutral",
        "random_baseline",
    }
    assert sum(1 for snapshot in snapshots if snapshot.candidate_group == "random_baseline") == 2


def test_long_outcome_fee_slippage_and_tp_sl_analysis() -> None:
    repository = StorageRepository(f"sqlite:///{_db_path()}")
    base = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    try:
        repository.insert_scanner_validation_snapshots(
            [
                _snapshot(
                    direction="long",
                    price=Decimal("100"),
                    timestamp=base,
                    stop_loss=Decimal("98"),
                    take_profit=Decimal("103"),
                )
            ]
        )
        snapshot = repository.get_scanner_validation_snapshots()[0]
        repository.upsert_historical_candles(
            [
                _candle(open_time=base, close=Decimal("101"), high=Decimal("101"), low=Decimal("99")),
                _candle(open_time=base + timedelta(minutes=15), close=Decimal("104"), high=Decimal("104"), low=Decimal("99")),
            ],
            source="test",
        )
        outcome = evaluate_scanner_snapshot_outcome(
            repository=repository,
            snapshot=snapshot,
            horizon="15m",
            as_of=base + timedelta(hours=1),
        )
    finally:
        repository.close()

    assert outcome.outcome_state == "win"
    assert outcome.gross_return_pct == Decimal("1.0000")
    assert outcome.net_return_pct == Decimal("0.8800")
    assert outcome.take_profit_hit is True
    assert outcome.stop_loss_hit is False
    assert outcome.first_exit == "take_profit"


def test_short_outcome_calculation() -> None:
    repository = StorageRepository(f"sqlite:///{_db_path()}")
    base = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    try:
        repository.insert_scanner_validation_snapshots(
            [_snapshot(direction="short", price=Decimal("100"), timestamp=base, group="top_short")]
        )
        snapshot = repository.get_scanner_validation_snapshots()[0]
        repository.upsert_historical_candles(
            [_candle(open_time=base, close=Decimal("96"), high=Decimal("101"), low=Decimal("95"))],
            source="test",
        )
        outcome = evaluate_scanner_snapshot_outcome(
            repository=repository,
            snapshot=snapshot,
            horizon="15m",
            as_of=base + timedelta(hours=1),
        )
    finally:
        repository.close()

    assert outcome.outcome_state == "win"
    assert outcome.gross_return_pct == Decimal("4.0000")
    assert outcome.net_return_pct == Decimal("3.8800")
    assert outcome.direction_correct is True


def test_insufficient_data_behavior() -> None:
    repository = StorageRepository(f"sqlite:///{_db_path()}")
    base = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    try:
        repository.insert_scanner_validation_snapshots([_snapshot(direction="long", price=Decimal("100"), timestamp=base)])
        snapshot = repository.get_scanner_validation_snapshots()[0]
        outcome = evaluate_scanner_snapshot_outcome(
            repository=repository,
            snapshot=snapshot,
            horizon="15m",
            as_of=base + timedelta(hours=1),
        )
    finally:
        repository.close()

    assert outcome.outcome_state == "insufficient_data"
    assert outcome.net_return_pct is None


def test_idempotent_evaluation_and_report_buckets_baseline() -> None:
    repository = StorageRepository(f"sqlite:///{_db_path()}")
    base = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    try:
        snapshots = [
            _snapshot(direction="long", price=Decimal("100"), timestamp=base, score=85, group="top_long"),
            _snapshot(direction="short", price=Decimal("100"), timestamp=base, score=72, group="top_short"),
            _snapshot(direction="long", price=Decimal("100"), timestamp=base, score=62, group="random_baseline"),
        ]
        repository.insert_scanner_validation_snapshots(snapshots)
        repository.upsert_historical_candles(
            [
                _candle(open_time=base, close=Decimal("102")),
                _candle(open_time=base + timedelta(hours=1), close=Decimal("103"), timeframe="1h"),
                _candle(open_time=base + timedelta(hours=4), close=Decimal("104"), timeframe="1h"),
                _candle(open_time=base + timedelta(hours=24), close=Decimal("105"), timeframe="1h"),
            ],
            source="test",
        )
        first_count = evaluate_pending_scanner_snapshots(repository=repository, as_of=base + timedelta(days=2))
        second_count = evaluate_pending_scanner_snapshots(repository=repository, as_of=base + timedelta(days=2))
        persisted = repository.get_scanner_validation_snapshots()
        outcomes = repository.get_scanner_validation_outcomes(snapshot_ids=[snapshot.id for snapshot in persisted if snapshot.id is not None])
        report = build_scanner_validation_report(snapshots=persisted, outcomes=outcomes)
    finally:
        repository.close()

    assert first_count == len(SCANNER_VALIDATION_HORIZONS) * 3
    assert second_count == 0
    assert len(outcomes) == len(SCANNER_VALIDATION_HORIZONS) * 3
    buckets = {bucket.name: bucket for bucket in report.opportunity_score_bucket_performance}
    assert buckets["60-70"].sample_size >= 1
    assert buckets["70-80"].sample_size >= 1
    assert buckets["80-90"].sample_size >= 1
    assert report.scanner_vs_random_baseline.scanner_sample_size > 0
    assert report.scanner_vs_random_baseline.random_baseline_sample_size > 0


def test_scanner_validation_api_response_shape() -> None:
    repository = StorageRepository(f"sqlite:///{_db_path()}")
    base = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    repository.insert_scanner_validation_snapshots([_snapshot(direction="long", price=Decimal("100"), timestamp=base)])

    app.dependency_overrides[get_dashboard_data_access] = lambda: DashboardDataAccess(repository)
    client = TestClient(app)
    try:
        report_response = client.get("/performance/scanner-validation-report")
        evaluate_response = client.post("/performance/scanner-validation/evaluate")
    finally:
        app.dependency_overrides.clear()
        repository.close()

    assert report_response.status_code == 200
    body = report_response.json()
    assert {
        "total_snapshots",
        "evaluated_snapshots",
        "pending_snapshots",
        "win_rate",
        "expectancy",
        "scanner_vs_random_baseline",
        "opportunity_score_bucket_performance",
        "direction_performance",
        "horizon_performance",
        "stop_loss_take_profit_analysis",
        "conclusion",
        "warnings",
    } <= set(body)
    assert body["paper_validation"] is True
    assert body["real_futures_execution_enabled"] is False
    assert evaluate_response.status_code == 200
    assert evaluate_response.json()["idempotent"] is True
