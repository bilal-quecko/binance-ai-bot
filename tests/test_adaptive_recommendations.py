from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dashboard_api import get_dashboard_data_access
from app.api.dependencies import DashboardDataAccess
from app.main import app
from app.market_data.candles import Candle
from app.monitoring.adaptive_recommendations import build_adaptive_recommendation_report
from app.storage import StorageRepository
from app.storage.models import HistoricalCandleRecord, SignalValidationSnapshotRecord


def _snapshot(
    *,
    snapshot_id: int,
    timestamp: datetime,
    symbol: str = "BTCUSDT",
    action: str = "buy",
    confidence: int = 75,
    risk_grade: str = "medium",
    regime_label: str = "trending_up",
) -> SignalValidationSnapshotRecord:
    return SignalValidationSnapshotRecord(
        id=snapshot_id,
        symbol=symbol,
        timestamp=timestamp,
        price=Decimal("100"),
        final_action=action,
        fusion_final_signal="long" if action in {"buy", "wait"} else "reduce_risk",
        confidence=confidence,
        expected_edge_pct=Decimal("1.0"),
        estimated_cost_pct=Decimal("0.20"),
        risk_grade=risk_grade,
        preferred_horizon="15m",
        technical_score=Decimal("70"),
        technical_context_json='{"trend_direction":"bullish"}',
        sentiment_score=Decimal("55"),
        sentiment_context_json='{"label":"bullish"}',
        pattern_score=Decimal("1.5"),
        pattern_context_json='{"trend_character":"persistent"}',
        ai_context_json='{"bias":"bullish"}',
        top_reasons=("Measured setup.",),
        warnings=(),
        invalidation_hint="Invalidate below support.",
        trade_opened=action == "buy",
        signal_ignored_or_blocked=False,
        blocker_reasons=(),
        regime_label=regime_label,
    )


def _candle(
    *,
    symbol: str = "BTCUSDT",
    open_time: datetime,
    close: Decimal,
) -> HistoricalCandleRecord:
    return HistoricalCandleRecord(
        symbol=symbol,
        interval="1m",
        open_time=open_time,
        close_time=open_time + timedelta(minutes=1),
        open_price=close,
        high_price=close + Decimal("0.1"),
        low_price=close - Decimal("0.1"),
        close_price=close,
        volume=Decimal("1"),
        quote_volume=close,
        trade_count=1,
        source="test",
        created_at=open_time,
    )


def _candles_for_snapshots(
    snapshots: list[SignalValidationSnapshotRecord],
    *,
    close_5m: Decimal,
    close_15m: Decimal | None = None,
) -> dict[str, list[HistoricalCandleRecord]]:
    candles: list[HistoricalCandleRecord] = []
    for snapshot in snapshots:
        candles.append(
            _candle(
                symbol=snapshot.symbol,
                open_time=snapshot.timestamp + timedelta(minutes=4),
                close=close_5m,
            )
        )
        if close_15m is not None:
            candles.append(
                _candle(
                    symbol=snapshot.symbol,
                    open_time=snapshot.timestamp + timedelta(minutes=14),
                    close=close_15m,
                )
            )
    return {"BTCUSDT": candles}


def _six_snapshots(**overrides) -> list[SignalValidationSnapshotRecord]:
    base = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
    return [
        _snapshot(snapshot_id=index + 1, timestamp=base + timedelta(hours=index), **overrides)
        for index in range(6)
    ]


def _recommendation_types(report):
    return {item.recommendation_type for item in report.recommendations}


def test_adaptive_recommendations_insufficient_data_behavior() -> None:
    snapshots = _six_snapshots()[:1]
    report = build_adaptive_recommendation_report(
        snapshots=snapshots,
        candles_by_symbol=_candles_for_snapshots(snapshots, close_5m=Decimal("102")),
        symbol="BTCUSDT",
        start_date=None,
        end_date=None,
        horizon="5m",
    )

    assert report.status == "insufficient_data"
    assert report.recommendations[0].recommendation_type == "insufficient_data"
    assert report.recommendations[0].do_not_auto_apply is True


def test_adaptive_recommendations_raise_confidence_for_losing_low_bucket() -> None:
    snapshots = _six_snapshots(confidence=30, risk_grade="low")
    report = build_adaptive_recommendation_report(
        snapshots=snapshots,
        candles_by_symbol=_candles_for_snapshots(snapshots, close_5m=Decimal("98")),
        symbol="BTCUSDT",
        start_date=None,
        end_date=None,
        horizon="5m",
    )

    assert "raise_min_confidence" in _recommendation_types(report)
    confidence_rec = next(item for item in report.recommendations if item.recommendation_type == "raise_min_confidence")
    assert confidence_rec.affected_scope == "confidence_bucket"
    assert confidence_rec.affected_value == "low"
    assert confidence_rec.do_not_auto_apply is True


def test_adaptive_recommendations_avoid_bad_regime() -> None:
    snapshots = _six_snapshots(regime_label="choppy")
    report = build_adaptive_recommendation_report(
        snapshots=snapshots,
        candles_by_symbol=_candles_for_snapshots(snapshots, close_5m=Decimal("98")),
        symbol="BTCUSDT",
        start_date=None,
        end_date=None,
        horizon="5m",
    )

    assert "avoid_regime" in _recommendation_types(report)
    assert "require_confirmation" in _recommendation_types(report)
    regime_rec = next(item for item in report.recommendations if item.recommendation_type == "avoid_regime")
    assert regime_rec.affected_value == "choppy"


def test_adaptive_recommendations_prefer_best_horizon() -> None:
    snapshots = _six_snapshots()
    report = build_adaptive_recommendation_report(
        snapshots=snapshots,
        candles_by_symbol=_candles_for_snapshots(
            snapshots,
            close_5m=Decimal("99"),
            close_15m=Decimal("103"),
        ),
        symbol="BTCUSDT",
        start_date=None,
        end_date=None,
    )

    assert "prefer_horizon" in _recommendation_types(report)
    preferred = next(item for item in report.recommendations if item.recommendation_type == "prefer_horizon")
    assert preferred.affected_value == "15m"


def test_adaptive_recommendations_restrict_underperforming_action_type() -> None:
    snapshots = _six_snapshots(action="sell_exit")
    report = build_adaptive_recommendation_report(
        snapshots=snapshots,
        candles_by_symbol=_candles_for_snapshots(snapshots, close_5m=Decimal("102")),
        symbol="BTCUSDT",
        start_date=None,
        end_date=None,
        horizon="5m",
    )

    assert "restrict_action_type" in _recommendation_types(report)
    action_rec = next(item for item in report.recommendations if item.recommendation_type == "restrict_action_type")
    assert action_rec.affected_value == "sell_exit"


def test_adaptive_recommendations_keep_current_settings_when_no_change_is_justified() -> None:
    snapshots = _six_snapshots(risk_grade="low")
    report = build_adaptive_recommendation_report(
        snapshots=snapshots,
        candles_by_symbol=_candles_for_snapshots(snapshots, close_5m=Decimal("100.3")),
        symbol="BTCUSDT",
        start_date=None,
        end_date=None,
        horizon="5m",
    )

    assert report.status == "ready"
    assert [item.recommendation_type for item in report.recommendations] == ["keep_current_settings"]
    assert all(item.do_not_auto_apply for item in report.recommendations)


def _db_path() -> Path:
    base = Path("tests/.tmp_storage")
    base.mkdir(parents=True, exist_ok=True)
    return (base / f"adaptive_recommendations_{uuid4().hex}.sqlite").resolve()


def test_adaptive_recommendations_api_response_shape() -> None:
    db_path = _db_path()
    repository = StorageRepository(f"sqlite:///{db_path}")
    try:
        snapshots = _six_snapshots(confidence=30, risk_grade="low")
        for snapshot in snapshots:
            snapshot.id = repository.insert_signal_validation_snapshot(snapshot)
        candles = []
        for snapshot in snapshots:
            close = Decimal("98")
            candles.append(
                Candle(
                    symbol="BTCUSDT",
                    timeframe="1m",
                    open=close,
                    high=close + Decimal("0.1"),
                    low=close - Decimal("0.1"),
                    close=close,
                    volume=Decimal("1"),
                    quote_volume=close,
                    open_time=snapshot.timestamp + timedelta(minutes=4),
                    close_time=snapshot.timestamp + timedelta(minutes=5),
                    event_time=snapshot.timestamp + timedelta(minutes=5),
                    trade_count=1,
                    is_closed=True,
                )
            )
        repository.upsert_historical_candles(candles, source="test")
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
            "/performance/adaptive-recommendations",
            params={"symbol": "btcusdt", "horizon": "5m"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "BTCUSDT"
    assert payload["status"] == "ready"
    assert payload["recommendations"]
    assert payload["recommendations"][0]["do_not_auto_apply"] is True
    assert "recommendation_type" in payload["recommendations"][0]
