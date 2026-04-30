from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dashboard_api import get_dashboard_data_access
from app.api.dependencies import DashboardDataAccess
from app.main import app
from app.market_data.candles import Candle
from app.monitoring.similar_setups import (
    SimilarSetupDescriptor,
    build_similar_setup_report,
    descriptor_from_snapshot,
)
from app.storage import StorageRepository
from app.storage.models import SignalValidationSnapshotRecord


def _db_path() -> Path:
    base = Path("tests/.tmp_storage")
    base.mkdir(parents=True, exist_ok=True)
    return (base / f"similar_setups_{uuid4().hex}.sqlite").resolve()


def _snapshot(
    *,
    snapshot_id: int | None = None,
    symbol: str = "BTCUSDT",
    timestamp: datetime,
    action: str = "buy",
    confidence: int = 78,
    risk_grade: str = "medium",
    regime_label: str = "trending_up",
    ignored: bool = False,
    blockers: tuple[str, ...] = (),
) -> SignalValidationSnapshotRecord:
    return SignalValidationSnapshotRecord(
        id=snapshot_id,
        symbol=symbol,
        timestamp=timestamp,
        price=Decimal("100"),
        final_action=action,
        fusion_final_signal="long" if action in {"buy", "wait"} else "reduce_risk",
        confidence=confidence,
        expected_edge_pct=Decimal("1.20"),
        estimated_cost_pct=Decimal("0.20"),
        risk_grade=risk_grade,
        preferred_horizon="15m",
        technical_score=Decimal("70"),
        technical_context_json='{"trend_direction":"bullish"}',
        sentiment_score=Decimal("55"),
        sentiment_context_json='{"label":"bullish"}',
        pattern_score=Decimal("1.5"),
        pattern_context_json='{"trend_character":"persistent","overall_direction":"bullish"}',
        ai_context_json='{"bias":"bullish"}',
        top_reasons=("Breakout readiness is high to the upside.",),
        warnings=(),
        invalidation_hint="Invalidate the long idea if price loses 98.",
        trade_opened=action == "buy" and not ignored,
        signal_ignored_or_blocked=ignored,
        blocker_reasons=blockers,
        regime_label=regime_label,
    )


def _candle(*, symbol: str, open_time: datetime, close: Decimal) -> Candle:
    return Candle(
        symbol=symbol,
        timeframe="1m",
        open=close,
        high=close,
        low=close,
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


def test_similar_setup_report_finds_promising_matching_outcomes() -> None:
    db_path = _db_path()
    repository = StorageRepository(f"sqlite:///{db_path}")
    try:
        base = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        snapshots = [
            _snapshot(snapshot_id=index + 1, timestamp=base + timedelta(hours=index))
            for index in range(6)
        ]
        repository.upsert_historical_candles(
            [
                _candle(
                    symbol="BTCUSDT",
                    open_time=snapshot.timestamp + timedelta(minutes=4),
                    close=Decimal("102"),
                )
                for snapshot in snapshots
            ],
            source="test",
        )
        report = build_similar_setup_report(
            current_setup=descriptor_from_snapshot(snapshots[0]),
            snapshots=snapshots[1:],
            candles_by_symbol={"BTCUSDT": _stored_candles(repository, "BTCUSDT")},
            horizon="5m",
        )
    finally:
        repository.close()

    assert report.status == "ready"
    assert report.reliability_label == "promising"
    assert report.matching_sample_size == 5
    assert report.best_horizon == "5m"
    assert report.horizons[0].win_rate_pct == Decimal("100.0000")
    assert "regime" in report.matched_attributes


def test_similar_setup_report_requires_enough_evaluated_matches() -> None:
    base = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    current = _snapshot(snapshot_id=1, timestamp=base)
    historical = _snapshot(snapshot_id=2, timestamp=base + timedelta(hours=1))

    report = build_similar_setup_report(
        current_setup=descriptor_from_snapshot(current),
        snapshots=[historical],
        candles_by_symbol={"BTCUSDT": []},
        horizon="5m",
    )

    assert report.status == "insufficient_data"
    assert report.reliability_label == "insufficient_data"
    assert report.matching_sample_size == 0


def test_similar_setup_matching_filters_dissimilar_setups() -> None:
    base = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    current = SimilarSetupDescriptor(
        symbol="BTCUSDT",
        action="buy",
        confidence_bucket="high",
        risk_grade="medium",
        regime_label="trending_up",
        preferred_horizon="15m",
        technical_direction="bullish",
        sentiment_direction="bullish",
        pattern_behavior="persistent",
        blocker_state="clear",
    )
    dissimilar = _snapshot(
        snapshot_id=2,
        symbol="ETHUSDT",
        timestamp=base + timedelta(hours=1),
        action="wait",
        confidence=20,
        risk_grade="high",
        regime_label="choppy",
        ignored=True,
        blockers=("Choppy regime blocked entry.",),
    )

    report = build_similar_setup_report(
        current_setup=current,
        snapshots=[dissimilar],
        candles_by_symbol={"ETHUSDT": []},
        horizon="5m",
    )

    assert report.matching_sample_size == 0
    assert report.matched_attributes == []


def test_similar_setups_api_response_shape_uses_latest_symbol_snapshot() -> None:
    db_path = _db_path()
    repository = StorageRepository(f"sqlite:///{db_path}")
    try:
        base = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        for index in range(6):
            snapshot = _snapshot(timestamp=base + timedelta(hours=index))
            snapshot.id = repository.insert_signal_validation_snapshot(snapshot)
            repository.upsert_historical_candles(
                [
                    _candle(
                        symbol="BTCUSDT",
                        open_time=snapshot.timestamp + timedelta(minutes=4),
                        close=Decimal("102"),
                    )
                ],
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
        response = client.get(
            "/performance/similar-setups",
            params={"symbol": "btcusdt", "horizon": "5m"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["reliability_label"] == "promising"
    assert payload["matching_sample_size"] == 5
    assert payload["best_horizon"] == "5m"
    assert payload["horizons"][0]["horizon"] == "5m"
    assert "matched_attributes" in payload
