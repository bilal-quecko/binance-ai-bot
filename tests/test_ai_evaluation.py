from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.ai.evaluation import AIOutcomeEvaluator
from app.ai.models import AIFeatureVector, AISignalSnapshot
from app.market_data.candles import Candle
from app.storage import StorageRepository


def _db_path(name: str) -> Path:
    base = Path("tests/.tmp_storage")
    base.mkdir(parents=True, exist_ok=True)
    return (base / f"{name}_{uuid4().hex}.sqlite").resolve()


def _insert_snapshot(
    repository: StorageRepository,
    *,
    timestamp: datetime,
    bias: str,
    confidence: int,
    close_price: str,
    entry_signal: bool,
    suggested_action: str,
) -> None:
    repository.insert_ai_signal_snapshot(
        AISignalSnapshot(
            symbol="BTCUSDT",
            bias=bias,
            confidence=confidence,
            entry_signal=entry_signal,
            exit_signal=False,
            suggested_action=suggested_action,
            explanation=f"{bias} view",
            feature_vector=AIFeatureVector(
                symbol="BTCUSDT",
                timestamp=timestamp,
                candle_count=5,
                close_price=Decimal(close_price),
                ema_fast=Decimal(close_price),
                ema_slow=Decimal("100"),
                rsi=Decimal("55"),
                atr=Decimal("1"),
                volatility_pct=Decimal("0.01"),
                momentum=Decimal("0.02"),
                recent_returns=(Decimal("0.01"),),
                wick_body_ratio=Decimal("1"),
                upper_wick_ratio=Decimal("0.2"),
                lower_wick_ratio=Decimal("0.1"),
                volume_change_pct=Decimal("0.3"),
                volume_spike_ratio=Decimal("1.2"),
                spread_ratio=Decimal("0.001"),
                order_book_imbalance=Decimal("0.2"),
                microstructure_healthy=True,
            ),
        )
    )


def _insert_candle(repository: StorageRepository, *, close_time: datetime, close_price: str) -> None:
    open_time = close_time - timedelta(minutes=1) + timedelta(milliseconds=1)
    repository.insert_market_candle_snapshot(
        Candle(
            symbol="BTCUSDT",
            timeframe="1m",
            open=Decimal(close_price),
            high=Decimal(close_price),
            low=Decimal(close_price),
            close=Decimal(close_price),
            volume=Decimal("10"),
            quote_volume=Decimal("1000"),
            open_time=open_time,
            close_time=close_time,
            event_time=close_time,
            trade_count=100,
            is_closed=True,
        )
    )


def test_ai_outcome_evaluator_scores_direction_and_calibration() -> None:
    db_path = _db_path("ai_outcome_eval")
    repository = StorageRepository(f"sqlite:///{db_path}")
    base_time = datetime(2024, 3, 9, 16, 0, tzinfo=UTC)

    _insert_snapshot(
        repository,
        timestamp=base_time,
        bias="bullish",
        confidence=80,
        close_price="100",
        entry_signal=True,
        suggested_action="enter",
    )
    _insert_snapshot(
        repository,
        timestamp=base_time + timedelta(minutes=10),
        bias="bullish",
        confidence=70,
        close_price="101",
        entry_signal=True,
        suggested_action="enter",
    )
    _insert_snapshot(
        repository,
        timestamp=base_time + timedelta(minutes=20),
        bias="sideways",
        confidence=60,
        close_price="100",
        entry_signal=False,
        suggested_action="wait",
    )

    for minute, price in (
        (5, "101"),
        (15, "99"),
        (25, "100.05"),
        (35, "103"),
    ):
        _insert_candle(repository, close_time=base_time + timedelta(minutes=minute), close_price=price)

    evaluation = AIOutcomeEvaluator(repository).evaluate(symbol="BTCUSDT")
    repository.close()

    summary_by_horizon = {item.horizon: item for item in evaluation.horizons}
    five_minute = summary_by_horizon["5m"]
    fifteen_minute = summary_by_horizon["15m"]
    one_hour = summary_by_horizon["1h"]

    assert five_minute.sample_size == 3
    assert five_minute.actionable_sample_size == 3
    assert five_minute.abstain_count == 0
    assert five_minute.directional_accuracy_pct == Decimal("66.67")
    assert five_minute.confidence_calibration_pct == Decimal("56.67")
    assert five_minute.false_positive_count == 1
    assert five_minute.false_positive_rate_pct == Decimal("33.33")
    assert five_minute.false_reversal_count == 1
    assert five_minute.false_reversal_rate_pct == Decimal("33.33")

    assert fifteen_minute.sample_size == 3
    assert fifteen_minute.directional_accuracy_pct == Decimal("0.00")
    assert one_hour.sample_size == 0

    assert evaluation.recent_samples[0].horizon in {"5m", "15m"}
    assert evaluation.recent_samples[0].symbol == "BTCUSDT"
