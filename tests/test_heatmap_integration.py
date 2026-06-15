from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.data.heatmap_provider import LiquidationCluster, MockHeatmapProvider, enrich_signal_with_heatmap
from app.market_data.candles import Candle
from app.monitoring.signal_outcomes import evaluate_signal_outcome
from app.storage import StorageRepository
from app.storage.models import SignalOutcomeSnapshotRecord


class StaticHeatmapProvider:
    def __init__(self, clusters: list[LiquidationCluster]) -> None:
        self.clusters = clusters

    def get_liquidation_clusters(self, symbol: str) -> list[LiquidationCluster]:
        return [cluster for cluster in self.clusters if cluster.symbol == symbol.upper()]

    def get_nearest_liquidity_above(self, symbol: str, price: Decimal) -> LiquidationCluster | None:
        clusters = [
            cluster
            for cluster in self.get_liquidation_clusters(symbol)
            if cluster.side == "above" and cluster.level > price
        ]
        return min(clusters, key=lambda cluster: cluster.level - price, default=None)

    def get_nearest_liquidity_below(self, symbol: str, price: Decimal) -> LiquidationCluster | None:
        clusters = [
            cluster
            for cluster in self.get_liquidation_clusters(symbol)
            if cluster.side == "below" and cluster.level < price
        ]
        return min(clusters, key=lambda cluster: price - cluster.level, default=None)

    def get_liquidity_intensity(self, symbol: str) -> int:
        return max((cluster.intensity for cluster in self.get_liquidation_clusters(symbol)), default=0)


def _cluster(level: str, side: str, intensity: int) -> LiquidationCluster:
    return LiquidationCluster(
        symbol="BTCUSDT",
        level=Decimal(level),
        side=side,  # type: ignore[arg-type]
        intensity=intensity,
        source="test",
    )


def _db_path() -> Path:
    base = Path("tests/.tmp_storage")
    base.mkdir(parents=True, exist_ok=True)
    return (base / f"heatmap_{uuid4().hex}.sqlite").resolve()


def _candles(symbol: str, *, base_time: datetime, closes: list[Decimal]) -> list[Candle]:
    candles: list[Candle] = []
    previous = closes[0]
    for index, close in enumerate(closes):
        candles.append(
            Candle(
                symbol=symbol,
                timeframe="1m",
                open=previous,
                high=max(previous, close) + Decimal("0.20"),
                low=min(previous, close) - Decimal("0.20"),
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


def test_mock_heatmap_provider_works_without_external_api() -> None:
    provider = MockHeatmapProvider()

    clusters = provider.get_liquidation_clusters("BTCUSDT")

    assert {cluster.side for cluster in clusters} == {"above", "below"}
    assert 0 <= provider.get_liquidity_intensity("BTCUSDT") <= 100


def test_heatmap_enrichment_confirms_aligned_signal() -> None:
    provider = StaticHeatmapProvider([_cluster("101", "above", 88), _cluster("99", "below", 40)])

    enrichment = enrich_signal_with_heatmap(
        symbol="BTCUSDT",
        price=Decimal("100"),
        base_signal_type="BUY",
        base_confidence=70,
        provider=provider,
    )

    assert enrichment.heatmap_bias == "upside_squeeze"
    assert enrichment.base_signal_type == "BUY"
    assert enrichment.heatmap_signal_type == "BUY"
    assert enrichment.heatmap_alignment == "confirmed"
    assert enrichment.heatmap_confidence >= enrichment.base_confidence


def test_heatmap_dual_signal_marks_conflict_without_overriding_base() -> None:
    provider = StaticHeatmapProvider([_cluster("101", "above", 35), _cluster("99", "below", 92)])

    enrichment = enrich_signal_with_heatmap(
        symbol="BTCUSDT",
        price=Decimal("100"),
        base_signal_type="BUY",
        base_confidence=76,
        provider=provider,
    )

    assert enrichment.heatmap_bias == "downside_sweep"
    assert enrichment.base_signal_type == "BUY"
    assert enrichment.heatmap_signal_type == "WAIT"
    assert enrichment.heatmap_alignment == "conflict"
    assert enrichment.heatmap_confidence < enrichment.base_confidence


def test_outcome_comparison_tracks_heatmap_improvement_and_sweep_accuracy() -> None:
    db_path = _db_path()
    repository = StorageRepository(f"sqlite:///{db_path}")
    base_time = datetime(2024, 3, 9, 10, 0, tzinfo=UTC)
    snapshot = SignalOutcomeSnapshotRecord(
        id="heatmap-signal",
        symbol="BTCUSDT",
        timestamp=base_time,
        source="assistant",
        signal_type="BUY",
        confidence=75,
        entry_price=Decimal("100"),
        liquidity_bias="neutral",
        sweep_risk="none",
        nearest_liquidity_above=None,
        nearest_liquidity_below=None,
        funding_rate=None,
        open_interest=None,
        notes="base long, heatmap warned downside",
        heatmap_liquidity_below=Decimal("99"),
        heatmap_intensity_score=90,
        heatmap_bias="downside_sweep",
        base_signal_type="BUY",
        heatmap_signal_type="SELL",
        base_confidence=75,
        heatmap_confidence=70,
        heatmap_alignment="conflict",
    )
    try:
        repository.upsert_historical_candles(
            _candles(
                "BTCUSDT",
                base_time=base_time,
                closes=[Decimal("100"), Decimal("99.5"), Decimal("99.0"), Decimal("98.5"), Decimal("98.2"), Decimal("98.0")],
            ),
            source="test",
        )

        outcome = evaluate_signal_outcome(
            snapshot=snapshot,
            repository=repository,
            horizon="5m",
            as_of=base_time + timedelta(minutes=6),
        )
    finally:
        repository.close()

    assert outcome.base_signal_correct is False
    assert outcome.heatmap_signal_correct is True
    assert outcome.did_heatmap_improve_result is True
    assert outcome.did_heatmap_reduce_loss is True
    assert outcome.predicted_sweep_direction == "down"
    assert outcome.actual_sweep_direction == "down"
    assert outcome.sweep_prediction_correct is True
