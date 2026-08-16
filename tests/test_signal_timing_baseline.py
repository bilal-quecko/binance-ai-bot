from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.bot_api import get_settings_dependency
from app.config import Settings
from app.main import app
from app.market_data.candles import Candle
from app.monitoring.signal_outcomes import SignalSnapshotInput, snapshot_record_from_signal
from app.monitoring.signal_timing_baseline import (
    build_signal_timing_baseline_report,
    evaluate_pending_signal_timing_baselines,
    evaluate_signal_timing_baseline,
)
from app.storage import StorageRepository


def _db_path() -> Path:
    base = Path("tests/.tmp_storage")
    base.mkdir(parents=True, exist_ok=True)
    return (base / f"signal_timing_{uuid4().hex}.sqlite").resolve()


def _candle(
    *,
    symbol: str,
    open_time: datetime,
    open_price: str,
    high: str,
    low: str,
    close: str,
) -> Candle:
    return Candle(
        symbol=symbol,
        timeframe="1m",
        open=Decimal(open_price),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal("100"),
        quote_volume=Decimal("10000"),
        open_time=open_time,
        close_time=open_time + timedelta(minutes=1),
        event_time=open_time + timedelta(minutes=1),
        trade_count=100,
        is_closed=True,
    )


def _early_candles(base: datetime) -> list[Candle]:
    values = [
        ("100", "100.10", "100.00", "100.05"),
        ("100.05", "100.15", "100.02", "100.10"),
        ("100.10", "100.25", "100.08", "100.20"),
        ("100.20", "100.40", "100.15", "100.30"),
        ("100.30", "101.00", "100.25", "100.90"),
        ("100.90", "102.20", "100.80", "102.00"),
        ("102.00", "102.30", "101.80", "102.10"),
        ("102.10", "102.20", "101.90", "102.00"),
    ]
    return [
        _candle(
            symbol="BTCUSDT",
            open_time=base + timedelta(minutes=index),
            open_price=item[0],
            high=item[1],
            low=item[2],
            close=item[3],
        )
        for index, item in enumerate(values)
    ]


def test_early_signal_baseline_measures_lead_capture_and_costs() -> None:
    repository = StorageRepository(f"sqlite:///{_db_path()}")
    base = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    signal_time = base + timedelta(minutes=3)
    try:
        repository.upsert_historical_candles(_early_candles(base), source="test")
        snapshot = snapshot_record_from_signal(
            SignalSnapshotInput(
                symbol="BTCUSDT",
                source="spot_scanner",
                signal_type="BUY",
                confidence=80,
                entry_price=Decimal("100.20"),
                timestamp=signal_time,
            )
        )
        repository.insert_signal_outcome_snapshot(snapshot)
        baseline = evaluate_signal_timing_baseline(
            repository=repository,
            snapshot=snapshot,
            horizon="5m",
            as_of=signal_time + timedelta(minutes=6),
        )
    finally:
        repository.close()

    assert baseline.outcome_state == "evaluated"
    assert baseline.classification == "early"
    assert baseline.pre_move_lead_time_seconds is not None
    assert baseline.pre_move_lead_time_seconds > 0
    assert baseline.move_already_consumed_pct is not None
    assert baseline.move_already_consumed_pct < Decimal("35")
    assert baseline.max_favorable_excursion_pct == Decimal("2.0958")
    assert baseline.max_adverse_excursion_pct == Decimal("0.0499")
    assert baseline.net_return_after_costs_pct == Decimal("1.6764")
    assert baseline.time_to_target_seconds == 180


def test_chased_signal_classification_detects_consumed_move() -> None:
    repository = StorageRepository(f"sqlite:///{_db_path()}")
    base = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    signal_time = base + timedelta(minutes=3)
    candles = [
        _candle(symbol="ETHUSDT", open_time=base, open_price="100", high="100.2", low="100", close="100.1"),
        _candle(symbol="ETHUSDT", open_time=base + timedelta(minutes=1), open_price="100.1", high="102", low="100.1", close="101.9"),
        _candle(symbol="ETHUSDT", open_time=base + timedelta(minutes=2), open_price="101.9", high="103.1", low="101.8", close="103"),
        _candle(symbol="ETHUSDT", open_time=base + timedelta(minutes=3), open_price="103", high="103.2", low="102.9", close="103.1"),
        _candle(symbol="ETHUSDT", open_time=base + timedelta(minutes=4), open_price="103.1", high="103.7", low="103", close="103.5"),
        _candle(symbol="ETHUSDT", open_time=base + timedelta(minutes=5), open_price="103.5", high="103.7", low="103.2", close="103.4"),
        _candle(symbol="ETHUSDT", open_time=base + timedelta(minutes=6), open_price="103.4", high="103.6", low="103.1", close="103.3"),
        _candle(symbol="ETHUSDT", open_time=base + timedelta(minutes=7), open_price="103.3", high="103.5", low="103", close="103.2"),
    ]
    try:
        repository.upsert_historical_candles(candles, source="test")
        snapshot = snapshot_record_from_signal(
            SignalSnapshotInput(
                symbol="ETHUSDT",
                source="spot_scanner",
                signal_type="BUY",
                confidence=85,
                entry_price=Decimal("103"),
                timestamp=signal_time,
            )
        )
        baseline = evaluate_signal_timing_baseline(
            repository=repository,
            snapshot=snapshot,
            horizon="5m",
            as_of=signal_time + timedelta(minutes=6),
        )
    finally:
        repository.close()

    assert baseline.classification == "chased"
    assert baseline.move_already_consumed_pct is not None
    assert baseline.move_already_consumed_pct >= Decimal("70")


def test_pending_evaluator_is_idempotent_and_report_groups_results() -> None:
    repository = StorageRepository(f"sqlite:///{_db_path()}")
    base = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    signal_time = base + timedelta(minutes=3)
    try:
        repository.upsert_historical_candles(_early_candles(base), source="test")
        repository.insert_signal_outcome_snapshot(
            snapshot_record_from_signal(
                SignalSnapshotInput(
                    symbol="BTCUSDT",
                    source="spot_scanner",
                    signal_type="BUY",
                    confidence=80,
                    entry_price=Decimal("100.20"),
                    timestamp=signal_time,
                )
            )
        )
        first = evaluate_pending_signal_timing_baselines(
            repository=repository,
            as_of=signal_time + timedelta(minutes=6),
        )
        second = evaluate_pending_signal_timing_baselines(
            repository=repository,
            as_of=signal_time + timedelta(minutes=6),
        )
        report = build_signal_timing_baseline_report(repository=repository, symbol="BTCUSDT")
    finally:
        repository.close()

    assert first == 1
    assert second == 0
    assert report.evaluated_count == 1
    assert report.classification_counts == {"early": 1}
    assert report.overall.useful_rate_pct == Decimal("100.0000")
    assert report.by_horizon[0].label == "5m"
    assert report.by_source[0].label == "spot_scanner"


def test_signal_timing_baseline_api_exposes_measured_samples() -> None:
    db_path = _db_path()
    settings = Settings(DATABASE_URL=f"sqlite:///{db_path}")
    repository = StorageRepository(settings.database_url)
    base = datetime.now(tz=UTC) - timedelta(minutes=10)
    signal_time = base + timedelta(minutes=3)
    try:
        repository.upsert_historical_candles(_early_candles(base), source="test")
        repository.insert_signal_outcome_snapshot(
            snapshot_record_from_signal(
                SignalSnapshotInput(
                    symbol="BTCUSDT",
                    source="spot_scanner",
                    signal_type="BUY",
                    confidence=80,
                    entry_price=Decimal("100.20"),
                    timestamp=signal_time,
                )
            )
        )
    finally:
        repository.close()

    app.dependency_overrides[get_settings_dependency] = lambda: settings
    client = TestClient(app)
    try:
        response = client.get(
            "/bot/signal-timing-baseline",
            params={"symbol": "BTCUSDT", "horizon": "5m"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["data_state"] == "ready"
    assert payload["evaluated_count"] == 1
    assert payload["classification_counts"] == {"early": 1}
    assert payload["recent_samples"][0]["move_already_consumed_pct"] is not None
    assert "move_capture_ratio_pct" in payload["definitions"]


def test_futures_scanner_baseline_uses_separate_futures_candles() -> None:
    repository = StorageRepository(f"sqlite:///{_db_path()}")
    base = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    signal_time = base + timedelta(minutes=3)
    try:
        repository.upsert_futures_historical_candles(_early_candles(base), source="test_futures")
        snapshot = snapshot_record_from_signal(
            SignalSnapshotInput(
                symbol="BTCUSDT",
                source="scanner",
                signal_type="LONG",
                confidence=80,
                entry_price=Decimal("100.20"),
                timestamp=signal_time,
            )
        )
        repository.insert_futures_paper_fill(
            order_id="paper-futures-entry",
            status="executed",
            symbol="BTCUSDT",
            side="LONG",
            filled_quantity=Decimal("0.01"),
            fill_price=Decimal("100.30"),
            fee_paid=Decimal("0.01"),
            realized_pnl=Decimal("0"),
            reason_codes=("PAPER_ONLY",),
            event_time=signal_time + timedelta(minutes=1),
        )
        baseline = evaluate_signal_timing_baseline(
            repository=repository,
            snapshot=snapshot,
            horizon="5m",
            as_of=signal_time + timedelta(minutes=6),
        )
    finally:
        repository.close()

    assert baseline.outcome_state == "evaluated"
    assert baseline.source == "scanner"
    assert baseline.classification == "early"
    assert baseline.signal_to_entry_latency_seconds == 60
