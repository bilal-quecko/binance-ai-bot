from datetime import UTC, datetime
from decimal import Decimal

from app.config import Settings
from app.data.binance_liquidation_feed import (
    BinanceLiquidationFeedService,
    normalize_force_order_payload,
    set_global_liquidation_feed_service,
)
from app.data.heatmap_provider import (
    BinanceForceOrderHeatmapProvider,
    MockHeatmapProvider,
    get_heatmap_provider,
    get_heatmap_provider_selection,
    get_heatmap_snapshot,
)
from app.data.vendor_heatmap_provider import normalize_vendor_heatmap_payload


def test_mock_remains_default_provider() -> None:
    settings = Settings()

    provider = get_heatmap_provider(settings)
    snapshot = get_heatmap_snapshot(symbol="BTCUSDT", current_price=Decimal("100"), settings=settings)

    assert isinstance(provider, MockHeatmapProvider)
    assert snapshot.data_quality == "mock"
    assert snapshot.is_real_data is False


def test_invalid_vendor_config_falls_back_safely() -> None:
    settings = Settings(HEATMAP_PROVIDER="vendor_http")

    provider = get_heatmap_provider(settings)
    selection = get_heatmap_provider_selection(settings)

    assert isinstance(provider, MockHeatmapProvider)
    assert selection.provider_status == "fallback"
    assert selection.active_provider == "mock"


def test_vendor_payload_normalizes_real_heatmap_snapshot() -> None:
    snapshot = normalize_vendor_heatmap_payload(
        {
            "current_price": "100",
            "nearest_liquidity_above": "102",
            "nearest_liquidity_below": "98",
            "liquidity_above_intensity": 84,
            "liquidity_below_intensity": 20,
            "heatmap_intensity_score": 84,
            "raw_timestamp": "2024-03-09T16:00:00+00:00",
        },
        symbol="BTCUSDT",
        provider="test_vendor",
        current_price=Decimal("100"),
    )

    assert snapshot is not None
    assert snapshot.data_quality == "vendor_heatmap"
    assert snapshot.is_real_data is True
    assert snapshot.heatmap_bias == "upside_squeeze"
    assert snapshot.timestamp == datetime(2024, 3, 9, 16, 0, tzinfo=UTC)


def test_binance_force_order_provider_returns_event_based_real_data() -> None:
    service = BinanceLiquidationFeedService(websocket_client=object())  # type: ignore[arg-type]
    event_ms = int(datetime.now(tz=UTC).timestamp() * 1000)
    event = normalize_force_order_payload(
        {
            "E": event_ms,
            "o": {
                "s": "BTCUSDT",
                "S": "SELL",
                "o": "LIMIT",
                "f": "IOC",
                "q": "1000",
                "p": "100",
                "ap": "100",
                "X": "FILLED",
                "l": "1000",
                "z": "1000",
                "T": event_ms,
            },
        }
    )
    assert event is not None
    service.add_event(event)
    set_global_liquidation_feed_service(service)
    try:
        snapshot = BinanceForceOrderHeatmapProvider().snapshot(
            symbol="BTCUSDT",
            current_price=Decimal("100"),
        )
    finally:
        set_global_liquidation_feed_service(None)

    assert snapshot.data_quality == "event_based"
    assert snapshot.is_real_data is True
    assert snapshot.liquidation_pressure == "high"
    assert snapshot.heatmap_bias == "downside_sweep"
