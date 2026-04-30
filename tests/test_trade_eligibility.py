from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.bot_api import (
    get_backfill_service,
    get_bot_runtime,
    get_settings_dependency,
    get_symbol_sentiment_service,
)
from app.config import Settings
from app.main import app
from app.market_data.candles import Candle
from app.monitoring.signal_validation import HorizonQualityMetric, SignalValidationReport
from app.monitoring.similar_setups import SimilarSetupHorizonMetric, SimilarSetupReport
from app.monitoring.trade_eligibility import TradeEligibilityInput, evaluate_trade_eligibility
from app.storage import StorageRepository
from app.storage.models import SignalValidationSnapshotRecord
from tests.test_bot_api import FakeBackfillService, FakeSymbolSentimentService, NeutralRuntime


def _validation_report(
    *,
    status: str = "ready",
    sample_size: int = 7,
    expectancy: Decimal | None = Decimal("0.8500"),
) -> SignalValidationReport:
    return SignalValidationReport(
        symbol="BTCUSDT",
        start_date=None,
        end_date=None,
        status=status,
        status_message=None if status == "ready" else "Not enough forward candle data exists.",
        total_signals=sample_size,
        actionable_signals=sample_size,
        ignored_or_blocked_signals=0,
        horizons=[
            HorizonQualityMetric(
                horizon="15m",
                sample_size=sample_size,
                actionable_sample_size=sample_size,
                win_rate_pct=Decimal("71.0000") if expectancy is not None else None,
                expectancy_pct=expectancy,
                average_favorable_move_pct=Decimal("1.5000"),
                average_adverse_move_pct=Decimal("-0.4000"),
                false_positive_rate_pct=Decimal("29.0000"),
                false_breakout_rate_pct=None,
                winner_average_confidence=Decimal("78.0000"),
                loser_average_confidence=Decimal("55.0000"),
            )
        ],
        performance_by_action=[],
        performance_by_risk_grade=[],
        performance_by_confidence_bucket=[],
        performance_by_symbol=[],
    )


def _similar_report(
    *,
    status: str = "ready",
    reliability: str = "promising",
    sample_size: int = 6,
    expectancy: Decimal | None = Decimal("0.9000"),
) -> SimilarSetupReport:
    return SimilarSetupReport(
        status=status,
        reliability_label=reliability,
        matching_sample_size=sample_size,
        best_horizon="15m",
        horizons=[
            SimilarSetupHorizonMetric(
                horizon="15m",
                sample_size=sample_size,
                win_rate_pct=Decimal("70.0000") if expectancy is not None else None,
                expectancy_pct=expectancy,
                average_favorable_move_pct=Decimal("1.3000"),
                average_adverse_move_pct=Decimal("-0.3500"),
            )
        ],
        explanation=f"{sample_size} similar evaluated outcomes were found.",
        matched_attributes=["symbol", "action", "regime"],
    )


def _eligibility_input(**overrides) -> TradeEligibilityInput:
    values = {
        "symbol": "BTCUSDT",
        "action": "buy",
        "confidence": 78,
        "risk_grade": "medium",
        "preferred_horizon": "15m",
        "expected_edge_pct": Decimal("1.10"),
        "estimated_cost_pct": Decimal("0.20"),
        "blocker_reasons": (),
        "current_warnings": (),
        "regime_label": "trending_up",
        "regime_confidence": 76,
        "regime_warnings": (),
        "regime_avoid_conditions": (),
        "similar_setup": _similar_report(),
        "signal_validation": _validation_report(),
    }
    values.update(overrides)
    return TradeEligibilityInput(**values)


def test_trade_eligibility_allows_strong_supported_signal() -> None:
    result = evaluate_trade_eligibility(
        _eligibility_input(similar_setup=_similar_report(reliability="strong", sample_size=11))
    )

    assert result.status == "eligible"
    assert result.evidence_strength == "strong"
    assert result.minimum_confidence_threshold == 65
    assert "support paper automation consideration" in result.reason


def test_trade_eligibility_watch_only_for_mixed_evidence() -> None:
    result = evaluate_trade_eligibility(
        _eligibility_input(similar_setup=_similar_report(reliability="mixed"))
    )

    assert result.status == "watch_only"
    assert result.evidence_strength == "mixed"
    assert result.minimum_confidence_threshold == 75


def test_trade_eligibility_blocks_bad_risk_regime_and_blockers() -> None:
    blocked = evaluate_trade_eligibility(
        _eligibility_input(blocker_reasons=("Expected edge below costs.",))
    )
    bad_regime = evaluate_trade_eligibility(
        _eligibility_input(risk_grade="high", regime_label="choppy")
    )

    assert blocked.status == "not_eligible"
    assert "Expected edge below costs." in blocked.blocker_summary
    assert bad_regime.status == "not_eligible"
    assert "high risk grade" in bad_regime.conditions_to_avoid
    assert "choppy regime" in bad_regime.conditions_to_avoid


def test_trade_eligibility_returns_insufficient_data_for_small_samples() -> None:
    result = evaluate_trade_eligibility(
        _eligibility_input(
            similar_setup=_similar_report(
                status="insufficient_data",
                reliability="insufficient_data",
                sample_size=1,
                expectancy=None,
            ),
            signal_validation=_validation_report(
                status="insufficient_data",
                sample_size=1,
                expectancy=None,
            ),
        )
    )

    assert result.status == "insufficient_data"
    assert result.evidence_strength == "insufficient"
    assert "not enough measured signal history" in result.reason.lower()


def _db_path() -> Path:
    base = Path("tests/.tmp_storage")
    base.mkdir(parents=True, exist_ok=True)
    return (base / f"trade_eligibility_{uuid4().hex}.sqlite").resolve()


def _snapshot(*, timestamp: datetime, price: Decimal = Decimal("100")) -> SignalValidationSnapshotRecord:
    return SignalValidationSnapshotRecord(
        id=None,
        symbol="BTCUSDT",
        timestamp=timestamp,
        price=price,
        final_action="buy",
        fusion_final_signal="long",
        confidence=78,
        expected_edge_pct=Decimal("1.20"),
        estimated_cost_pct=Decimal("0.20"),
        risk_grade="medium",
        preferred_horizon="15m",
        technical_score=Decimal("70"),
        technical_context_json='{"trend_direction":"bullish"}',
        sentiment_score=Decimal("55"),
        sentiment_context_json='{"label":"bullish"}',
        pattern_score=Decimal("1.5"),
        pattern_context_json='{"trend_character":"persistent","overall_direction":"bullish"}',
        ai_context_json='{"bias":"bullish"}',
        top_reasons=("Technical trend is bullish.",),
        warnings=(),
        invalidation_hint="Invalidate below support.",
        trade_opened=True,
        signal_ignored_or_blocked=False,
        blocker_reasons=(),
        regime_label="trending_up",
    )


def _candle(*, open_time: datetime, close: Decimal) -> Candle:
    return Candle(
        symbol="BTCUSDT",
        timeframe="1m",
        open=close,
        high=close + Decimal("0.2"),
        low=close - Decimal("0.2"),
        close=close,
        volume=Decimal("10"),
        quote_volume=close * Decimal("10"),
        open_time=open_time,
        close_time=open_time + timedelta(minutes=1),
        event_time=open_time + timedelta(minutes=1),
        trade_count=10,
        is_closed=True,
    )


def test_trade_eligibility_api_response_shape_and_paper_only_flags() -> None:
    db_path = _db_path()
    settings = Settings(DATABASE_URL=f"sqlite:///{db_path}")
    repository = StorageRepository(settings.database_url)
    try:
        base = datetime(2024, 1, 1, 12, 0, tzinfo=UTC)
        for index in range(6):
            signal_time = base + timedelta(hours=index)
            repository.insert_signal_validation_snapshot(_snapshot(timestamp=signal_time))
            repository.upsert_historical_candles(
                [_candle(open_time=signal_time + timedelta(minutes=14), close=Decimal("102"))],
                source="test",
            )
        live_candles = [
            _candle(open_time=base + timedelta(days=1, minutes=index), close=Decimal("110") + index)
            for index in range(80)
        ]
        repository.upsert_historical_candles(live_candles, source="test")
    finally:
        repository.close()

    app.dependency_overrides[get_symbol_sentiment_service] = lambda: FakeSymbolSentimentService()
    app.dependency_overrides[get_bot_runtime] = lambda: NeutralRuntime()
    app.dependency_overrides[get_settings_dependency] = lambda: settings
    app.dependency_overrides[get_backfill_service] = lambda: FakeBackfillService()
    client = TestClient(app)
    try:
        response = client.get("/bot/trade-eligibility", params={"symbol": "BTCUSDT", "horizon": "15m"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "BTCUSDT"
    assert payload["status"] in {"eligible", "not_eligible", "watch_only", "insufficient_data"}
    assert payload["paper_only"] is True
    assert payload["advisory_only"] is True
    assert payload["live_trading_enabled"] is False
    assert payload["futures_enabled"] is False
    assert "minimum_confidence_threshold" in payload
