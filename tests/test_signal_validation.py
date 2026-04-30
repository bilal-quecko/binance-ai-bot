from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dashboard_api import get_dashboard_data_access
from app.api.dependencies import DashboardDataAccess
from app.main import app
from app.market_data.candles import Candle
from app.monitoring.signal_validation import (
    build_edge_report,
    build_signal_validation_report,
)
from app.storage import StorageRepository
from app.storage.models import SignalValidationSnapshotRecord


def _db_path() -> Path:
    base = Path("tests/.tmp_storage")
    base.mkdir(parents=True, exist_ok=True)
    return (base / f"signal_validation_{uuid4().hex}.sqlite").resolve()


def _snapshot(
    *,
    symbol: str = "BTCUSDT",
    timestamp: datetime,
    action: str = "buy",
    price: Decimal = Decimal("100"),
    confidence: int = 75,
    risk_grade: str = "medium",
    ignored: bool = False,
    blockers: tuple[str, ...] = (),
    reasons: tuple[str, ...] = ("Technical trend is bullish.",),
    regime_label: str | None = "trending_up",
) -> SignalValidationSnapshotRecord:
    return SignalValidationSnapshotRecord(
        id=None,
        symbol=symbol,
        timestamp=timestamp,
        price=price,
        final_action=action,
        fusion_final_signal="long" if action in {"buy", "wait"} else "wait",
        confidence=confidence,
        expected_edge_pct=Decimal("0.60"),
        estimated_cost_pct=Decimal("0.20"),
        risk_grade=risk_grade,
        preferred_horizon="15m",
        technical_score=Decimal("70"),
        technical_context_json='{"trend_direction":"bullish"}',
        sentiment_score=Decimal("55"),
        sentiment_context_json='{"label":"bullish"}',
        pattern_score=Decimal("1.5"),
        pattern_context_json='{"overall_direction":"bullish"}',
        ai_context_json='{"bias":"bullish"}',
        top_reasons=reasons,
        warnings=(),
        invalidation_hint="Invalidate the long idea if price loses support near 98.",
        trade_opened=action == "buy" and not ignored,
        signal_ignored_or_blocked=ignored,
        blocker_reasons=blockers,
        regime_label=regime_label,
    )


def _candle(
    *,
    symbol: str,
    open_time: datetime,
    close: Decimal,
    high: Decimal | None = None,
    low: Decimal | None = None,
) -> Candle:
    return Candle(
        symbol=symbol,
        timeframe="1m",
        open=close,
        high=high or close,
        low=low or close,
        close=close,
        volume=Decimal("1"),
        quote_volume=close,
        open_time=open_time,
        close_time=open_time + timedelta(minutes=1),
        event_time=open_time + timedelta(minutes=1),
        trade_count=1,
        is_closed=True,
    )


def _stored_candles(repository: StorageRepository, symbol: str):
    return repository.get_historical_candles(symbol=symbol, interval="1m")


def test_signal_snapshot_persistence_round_trip() -> None:
    db_path = _db_path()
    repository = StorageRepository(f"sqlite:///{db_path}")
    try:
        timestamp = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        snapshot_id = repository.insert_signal_validation_snapshot(
            _snapshot(timestamp=timestamp, blockers=("Expected edge below costs.",))
        )
        records = repository.get_signal_validation_snapshots(symbol="BTCUSDT")
    finally:
        repository.close()

    assert snapshot_id is not None
    assert len(records) == 1
    assert records[0].symbol == "BTCUSDT"
    assert records[0].final_action == "buy"
    assert records[0].confidence == 75
    assert records[0].blocker_reasons == ("Expected edge below costs.",)
    assert records[0].regime_label == "trending_up"


def test_forward_outcome_calculation_horizon_metrics_and_confidence_bucket() -> None:
    db_path = _db_path()
    repository = StorageRepository(f"sqlite:///{db_path}")
    try:
        base = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        snapshots = [
            _snapshot(timestamp=base, confidence=80),
            _snapshot(timestamp=base + timedelta(minutes=1), confidence=30, price=Decimal("100")),
        ]
        repository.upsert_historical_candles(
            [
                _candle(symbol="BTCUSDT", open_time=base + timedelta(minutes=4), close=Decimal("101"), high=Decimal("102"), low=Decimal("99")),
                _candle(symbol="BTCUSDT", open_time=base + timedelta(minutes=5), close=Decimal("102"), high=Decimal("103"), low=Decimal("99")),
                _candle(symbol="BTCUSDT", open_time=base + timedelta(minutes=16), close=Decimal("104"), high=Decimal("105"), low=Decimal("98")),
                _candle(symbol="BTCUSDT", open_time=base + timedelta(hours=1), close=Decimal("106"), high=Decimal("107"), low=Decimal("98")),
            ],
            source="test",
        )
        report = build_signal_validation_report(
            snapshots=snapshots,
            candles_by_symbol={"BTCUSDT": _stored_candles(repository, "BTCUSDT")},
            symbol="BTCUSDT",
            start_date=None,
            end_date=None,
        )
    finally:
        repository.close()

    five_minute = next(item for item in report.horizons if item.horizon == "5m")
    assert report.total_signals == 2
    assert five_minute.actionable_sample_size == 2
    assert five_minute.win_rate_pct == Decimal("100.0000")
    assert five_minute.average_favorable_move_pct == Decimal("2.5000")
    assert five_minute.average_adverse_move_pct == Decimal("-1.0000")
    buckets = {item.name: item for item in report.performance_by_confidence_bucket}
    assert buckets["high"].sample_size >= 1
    assert buckets["low"].sample_size >= 1


def test_signal_validation_returns_insufficient_data_without_forward_candles() -> None:
    base = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    report = build_signal_validation_report(
        snapshots=[_snapshot(timestamp=base)],
        candles_by_symbol={"BTCUSDT": []},
        symbol="BTCUSDT",
        start_date=None,
        end_date=None,
    )

    assert report.status == "insufficient_data"
    assert report.horizons[0].sample_size == 0


def test_edge_report_generation_and_blocker_effectiveness() -> None:
    db_path = _db_path()
    repository = StorageRepository(f"sqlite:///{db_path}")
    try:
        base = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        snapshots = []
        candles = []
        for index in range(7):
            signal_time = base + timedelta(hours=index)
            snapshots.append(
                _snapshot(
                    timestamp=signal_time,
                    action="buy" if index < 5 else "wait",
                    confidence=78 if index < 5 else 35,
                    ignored=index >= 5,
                    blockers=("Mixed signal blocked entry.",) if index >= 5 else (),
                    reasons=("Breakout readiness is high to the upside.",),
                )
            )
            future_price = Decimal("103") if index < 5 else Decimal("96")
            candles.append(
                _candle(
                    symbol="BTCUSDT",
                    open_time=signal_time + timedelta(minutes=5),
                    close=future_price,
                    high=max(Decimal("100"), future_price),
                    low=min(Decimal("100"), future_price),
                )
            )
        repository.upsert_historical_candles(candles, source="test")
        report = build_edge_report(
            snapshots=snapshots,
            candles_by_symbol={"BTCUSDT": _stored_candles(repository, "BTCUSDT")},
            symbol="BTCUSDT",
            start_date=None,
            end_date=None,
            horizon="5m",
        )
    finally:
        repository.close()

    assert report.status == "ready"
    assert report.useful_reasons[0].reason == "Breakout readiness is high to the upside."
    assert any("Prioritize high-confidence signals" in item for item in report.suggestions)
    assert report.protective_blockers[0].reason == "Mixed signal blocked entry."


def test_edge_report_insufficient_data_behavior() -> None:
    base = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    report = build_edge_report(
        snapshots=[_snapshot(timestamp=base)],
        candles_by_symbol={"BTCUSDT": []},
        symbol="BTCUSDT",
        start_date=None,
        end_date=None,
    )

    assert report.status == "insufficient_data"
    assert report.suggestions == []


def test_signal_validation_api_response_shape() -> None:
    db_path = _db_path()
    repository = StorageRepository(f"sqlite:///{db_path}")
    try:
        base = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        repository.insert_signal_validation_snapshot(_snapshot(timestamp=base))
        repository.upsert_historical_candles(
            [_candle(symbol="BTCUSDT", open_time=base + timedelta(minutes=5), close=Decimal("102"))],
            source="test",
        )
    finally:
        repository.close()

    def override_data_access():
        repo = StorageRepository(f"sqlite:///{db_path}")
        try:
            yield DashboardDataAccess(repo)
        finally:
            repo.close()

    app.dependency_overrides[get_dashboard_data_access] = override_data_access
    client = TestClient(app)
    try:
        validation = client.get("/performance/signal-validation", params={"symbol": "BTCUSDT"})
        edge = client.get("/performance/edge-report", params={"symbol": "BTCUSDT"})
        attribution = client.get("/performance/module-attribution", params={"symbol": "BTCUSDT"})
    finally:
        app.dependency_overrides.clear()

    assert validation.status_code == 200
    assert edge.status_code == 200
    assert attribution.status_code == 200
    payload = validation.json()
    assert payload["symbol"] == "BTCUSDT"
    assert payload["total_signals"] == 1
    assert payload["horizons"][0]["horizon"] == "5m"
    assert "performance_by_confidence_bucket" in payload
