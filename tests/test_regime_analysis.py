from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.analysis.pattern_summary import PatternAnalysisSnapshot
from app.analysis.regime import RegimeAnalysisService
from app.analysis.technical import TechnicalAnalysisService
from app.api.bot_api import get_bot_runtime, get_settings_dependency, get_symbol_sentiment_service
from app.config import Settings
from app.features.feature_store import FeatureEngine
from app.features.models import FeatureConfig, FeatureSnapshot
from app.main import app
from app.market_data.candles import Candle
from app.storage import StorageRepository


def _db_path() -> Path:
    base = Path("tests/.tmp_storage")
    base.mkdir(parents=True, exist_ok=True)
    return (base / f"regime_analysis_{uuid4().hex}.sqlite").resolve()


def _candles(closes: list[Decimal], *, symbol: str = "BTCUSDT", wide_ranges: bool = False) -> list[Candle]:
    base_time = datetime(2024, 3, 9, 16, 0, tzinfo=UTC)
    candles: list[Candle] = []
    previous = closes[0]
    for index, close in enumerate(closes):
        open_price = previous if index > 0 else close
        range_buffer = Decimal("3") if wide_ranges else Decimal("0.05")
        candles.append(
            Candle(
                symbol=symbol,
                timeframe="1m",
                open=open_price,
                high=max(open_price, close) + range_buffer,
                low=min(open_price, close) - range_buffer,
                close=close,
                volume=Decimal("100") + Decimal(index),
                quote_volume=(Decimal("100") + Decimal(index)) * close,
                open_time=base_time + timedelta(minutes=index),
                close_time=base_time + timedelta(minutes=index, seconds=59),
                event_time=base_time + timedelta(minutes=index, seconds=59),
                trade_count=20 + index,
                is_closed=True,
            )
        )
        previous = close
    return candles


def _features(candles: list[Candle], *, spread: Decimal | None = None) -> FeatureSnapshot:
    snapshot = FeatureEngine(FeatureConfig(ema_fast_period=3, ema_slow_period=5, rsi_period=3, atr_period=3)).build_snapshot(candles)
    if spread is None:
        return snapshot
    return FeatureSnapshot(
        symbol=snapshot.symbol,
        timestamp=snapshot.timestamp,
        ema_fast=snapshot.ema_fast,
        ema_slow=snapshot.ema_slow,
        rsi=snapshot.rsi,
        atr=snapshot.atr,
        mid_price=candles[-1].close,
        bid_ask_spread=spread,
        order_book_imbalance=Decimal("0.1"),
        regime=snapshot.regime,
    )


def _pattern(
    *,
    direction: str = "bullish",
    trend_character: str = "persistent",
    breakout_tendency: str = "mixed",
    reversal_tendency: str = "low",
    realized_volatility_pct: Decimal = Decimal("1.0"),
) -> PatternAnalysisSnapshot:
    return PatternAnalysisSnapshot(
        symbol="BTCUSDT",
        horizon="7d",
        generated_at=datetime(2024, 3, 9, 16, 30, tzinfo=UTC),
        data_state="ready",
        status_message="Pattern analysis is ready.",
        coverage_start=datetime(2024, 3, 2, 16, 30, tzinfo=UTC),
        coverage_end=datetime(2024, 3, 9, 16, 30, tzinfo=UTC),
        coverage_ratio_pct=Decimal("100"),
        partial_coverage=False,
        overall_direction=direction,  # type: ignore[arg-type]
        net_return_pct=Decimal("4"),
        up_moves=10,
        down_moves=3,
        flat_moves=0,
        up_move_ratio_pct=Decimal("76.92"),
        down_move_ratio_pct=Decimal("23.08"),
        realized_volatility_pct=realized_volatility_pct,
        max_drawdown_pct=Decimal("1.5"),
        trend_character=trend_character,  # type: ignore[arg-type]
        breakout_tendency=breakout_tendency,  # type: ignore[arg-type]
        reversal_tendency=reversal_tendency,  # type: ignore[arg-type]
        explanation="Pattern fixture.",
    )


def test_regime_analysis_detects_trending_up() -> None:
    candles = _candles([Decimal("100") + (Decimal(index) * Decimal("0.2")) for index in range(18)])
    technical = TechnicalAnalysisService().analyze(
        symbol="BTCUSDT",
        candles=candles,
        feature_snapshot=_features(candles),
    )

    regime = RegimeAnalysisService().analyze(
        symbol="BTCUSDT",
        horizon="7d",
        candles=candles,
        technical_analysis=technical,
        pattern_analysis=_pattern(),
        feature_snapshot=_features(candles),
    )

    assert regime.data_state == "ready"
    assert regime.regime_label == "trending_up"
    assert regime.confidence >= 55
    assert any("bullish" in item for item in regime.supporting_evidence)


def test_regime_analysis_prioritizes_low_liquidity_from_wide_spread() -> None:
    candles = _candles([Decimal("100") + (Decimal(index) * Decimal("0.2")) for index in range(18)])
    technical = TechnicalAnalysisService().analyze(
        symbol="BTCUSDT",
        candles=candles,
        feature_snapshot=_features(candles),
    )

    regime = RegimeAnalysisService().analyze(
        symbol="BTCUSDT",
        horizon="7d",
        candles=candles,
        technical_analysis=technical,
        pattern_analysis=_pattern(),
        feature_snapshot=_features(candles, spread=Decimal("1.0")),
    )

    assert regime.regime_label == "low_liquidity"
    assert any("spread" in item.lower() for item in regime.supporting_evidence)
    assert any("Wide spread" in item for item in regime.risk_warnings)


def test_regime_analysis_detects_choppy_conditions() -> None:
    candles = _candles(
        [
            Decimal("100"),
            Decimal("100.1"),
            Decimal("100"),
            Decimal("100.1"),
            Decimal("100"),
            Decimal("100.1"),
            Decimal("100"),
            Decimal("100.1"),
            Decimal("100"),
            Decimal("100.1"),
        ]
    )
    technical = TechnicalAnalysisService().analyze(
        symbol="BTCUSDT",
        candles=candles,
        feature_snapshot=_features(candles),
    )

    regime = RegimeAnalysisService().analyze(
        symbol="BTCUSDT",
        horizon="7d",
        candles=candles,
        technical_analysis=technical,
        pattern_analysis=_pattern(direction="sideways", trend_character="choppy", breakout_tendency="range_bound"),
        feature_snapshot=_features(candles),
    )

    assert regime.regime_label == "choppy"
    assert any("choppy" in item.lower() for item in regime.supporting_evidence)
    assert any("Avoid directional entries" in item for item in regime.avoid_conditions)


def test_regime_analysis_returns_incomplete_without_history() -> None:
    regime = RegimeAnalysisService().analyze(
        symbol="BTCUSDT",
        horizon="7d",
        candles=_candles([Decimal("100"), Decimal("101"), Decimal("102")]),
        technical_analysis=None,
        pattern_analysis=None,
        feature_snapshot=None,
    )

    assert regime.data_state == "incomplete"
    assert regime.regime_label is None
    assert regime.confidence == 0


class _Runtime:
    def status(self):
        from app.bot import BotStatus

        return BotStatus(state="stopped", mode="stopped", timeframe="1m")

    def candle_history(self, symbol: str):
        return []

    def technical_analysis(self, symbol: str):
        return None

    def top_of_book(self, symbol: str):
        return None


class _SentimentService:
    def analyze(self, *, symbol: str, candles=(), benchmark_symbol=None, benchmark_closes=()):
        from app.sentiment.models import SymbolSentimentSnapshot

        return SymbolSentimentSnapshot(
            symbol=symbol,
            generated_at=datetime(2024, 3, 9, 16, 0, tzinfo=UTC),
            data_state="incomplete",
            status_message="Proxy sentiment needs more history.",
            score=None,
            label="insufficient_data",
            confidence=None,
            momentum_state="unknown",
            risk_flag="unknown",
            explanation="No sentiment fixture.",
            source_mode="proxy",
            components=(),
        )


def test_regime_analysis_api_response_shape() -> None:
    db_path = _db_path()
    repository = StorageRepository(f"sqlite:///{db_path}")
    try:
        repository.upsert_historical_candles(
            _candles([Decimal("100") + Decimal(index) for index in range(20)]),
            source="test",
        )
    finally:
        repository.close()

    app.dependency_overrides[get_settings_dependency] = lambda: Settings(DATABASE_URL=f"sqlite:///{db_path}")
    app.dependency_overrides[get_bot_runtime] = lambda: _Runtime()
    app.dependency_overrides[get_symbol_sentiment_service] = lambda: _SentimentService()
    client = TestClient(app)
    try:
        response = client.get("/bot/regime-analysis", params={"symbol": "BTCUSDT", "horizon": "7d"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "BTCUSDT"
    assert payload["horizon"] == "7d"
    assert payload["data_state"] == "ready"
    assert payload["regime_label"] in {
        "trending_up",
        "breakout_building",
        "high_volatility",
        "sideways",
        "choppy",
    }
    assert isinstance(payload["supporting_evidence"], list)
    assert isinstance(payload["avoid_conditions"], list)
