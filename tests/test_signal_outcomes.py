from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.market_data.candles import Candle
from app.monitoring.signal_outcomes import (
    SignalSnapshotInput,
    evaluate_pending_signal_outcomes,
    evaluate_signal_outcome,
    persist_signal_snapshot,
    snapshot_record_from_signal,
)
from app.storage import StorageRepository


def _db_path() -> Path:
    base = Path("tests/.tmp_storage")
    base.mkdir(parents=True, exist_ok=True)
    return (base / f"signal_outcomes_{uuid4().hex}.sqlite").resolve()


def _candles(symbol: str, *, base_time: datetime, closes: list[Decimal]) -> list[Candle]:
    candles: list[Candle] = []
    previous = closes[0]
    for index, close in enumerate(closes):
        high = max(previous, close) + Decimal("0.20")
        low = min(previous, close) - Decimal("0.20")
        candles.append(
            Candle(
                symbol=symbol,
                timeframe="1m",
                open=previous,
                high=high,
                low=low,
                close=close,
                volume=Decimal("100"),
                quote_volume=Decimal("100000"),
                open_time=base_time + timedelta(minutes=index),
                close_time=base_time + timedelta(minutes=index + 1),
                event_time=base_time + timedelta(minutes=index + 1),
                trade_count=100,
                is_closed=True,
            )
        )
        previous = close
    return candles


def test_signal_storage_works() -> None:
    repository = StorageRepository(f"sqlite:///{_db_path()}")
    try:
        signal_id = persist_signal_snapshot(
            repository=repository,
            payload=SignalSnapshotInput(
                symbol="btcusdt",
                source="assistant",
                signal_type="buy",
                confidence=82,
                entry_price=Decimal("100"),
                liquidity_bias="neutral",
                sweep_risk="none",
                notes="test signal",
            ),
        )
        snapshots = repository.get_signal_outcome_snapshots(symbol="BTCUSDT")
    finally:
        repository.close()

    assert signal_id is not None
    assert len(snapshots) == 1
    assert snapshots[0].source == "assistant"
    assert snapshots[0].signal_type == "BUY"


def test_buy_outcome_tracking_computes_direction_tp_and_sweep() -> None:
    db_path = _db_path()
    repository = StorageRepository(f"sqlite:///{db_path}")
    base_time = datetime(2024, 3, 9, 10, 0, tzinfo=UTC)
    try:
        repository.upsert_historical_candles(
            _candles(
                "BTCUSDT",
                base_time=base_time,
                closes=[Decimal("100"), Decimal("100.4"), Decimal("101.0"), Decimal("101.7"), Decimal("102.0"), Decimal("102.2")],
            ),
            source="test",
        )
        snapshot = snapshot_record_from_signal(
            SignalSnapshotInput(
                symbol="BTCUSDT",
                source="assistant",
                signal_type="BUY",
                confidence=80,
                entry_price=Decimal("100"),
                sweep_risk="upside_sweep",
                notes="upside liquidity nearby",
                timestamp=base_time,
            )
        )
        repository.insert_signal_outcome_snapshot(snapshot)

        outcome = evaluate_signal_outcome(
            snapshot=snapshot,
            repository=repository,
            horizon="5m",
            as_of=base_time + timedelta(minutes=6),
        )
    finally:
        repository.close()

    assert outcome.price_change_percent == Decimal("2.0000")
    assert outcome.direction_correct is True
    assert outcome.did_price_hit_tp is True
    assert outcome.first_hit == "take_profit"
    assert outcome.sweep_direction_actual == "up"
    assert outcome.sweep_prediction_correct is True


def test_sell_outcome_tracking_computes_tp_sl_model() -> None:
    db_path = _db_path()
    repository = StorageRepository(f"sqlite:///{db_path}")
    base_time = datetime(2024, 3, 9, 10, 0, tzinfo=UTC)
    try:
        repository.upsert_historical_candles(
            _candles(
                "ETHUSDT",
                base_time=base_time,
                closes=[Decimal("100"), Decimal("99.5"), Decimal("99.0"), Decimal("98.3"), Decimal("98.1"), Decimal("98.0")],
            ),
            source="test",
        )
        snapshot = snapshot_record_from_signal(
            SignalSnapshotInput(
                symbol="ETHUSDT",
                source="scanner",
                signal_type="SELL",
                confidence=76,
                entry_price=Decimal("100"),
                sweep_risk="downside_sweep",
                notes="short setup",
                timestamp=base_time,
            )
        )
        repository.insert_signal_outcome_snapshot(snapshot)

        outcome = evaluate_signal_outcome(
            snapshot=snapshot,
            repository=repository,
            horizon="5m",
            as_of=base_time + timedelta(minutes=6),
        )
    finally:
        repository.close()

    assert outcome.direction_correct is True
    assert outcome.did_price_hit_tp is True
    assert outcome.did_price_hit_sl is False
    assert outcome.sweep_prediction_correct is True


def test_pending_evaluation_is_idempotent_per_horizon() -> None:
    db_path = _db_path()
    repository = StorageRepository(f"sqlite:///{db_path}")
    base_time = datetime(2024, 3, 9, 10, 0, tzinfo=UTC)
    try:
        repository.upsert_historical_candles(
            _candles("BTCUSDT", base_time=base_time, closes=[Decimal("100"), Decimal("101")] * 20),
            source="test",
        )
        persist_signal_snapshot(
            repository=repository,
            payload=SignalSnapshotInput(
                symbol="BTCUSDT",
                source="assistant",
                signal_type="BUY",
                confidence=70,
                entry_price=Decimal("100"),
                timestamp=base_time,
            ),
        )
        first = evaluate_pending_signal_outcomes(repository=repository, as_of=base_time + timedelta(hours=25))
        second = evaluate_pending_signal_outcomes(repository=repository, as_of=base_time + timedelta(hours=25))
        outcomes = repository.get_signal_outcomes()
    finally:
        repository.close()

    assert first == 5
    assert second == 0
    assert len(outcomes) == 5
