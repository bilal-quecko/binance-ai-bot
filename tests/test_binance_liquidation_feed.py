from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.data.binance_liquidation_feed import (
    BinanceLiquidationFeedService,
    build_force_order_streams,
    normalize_force_order_payload,
)


def _payload(*, side: str = "SELL", qty: str = "2", price: str = "100", event_ms: int = 1710000000000):
    return {
        "e": "forceOrder",
        "E": event_ms,
        "o": {
            "s": "BTCUSDT",
            "S": side,
            "o": "LIMIT",
            "f": "IOC",
            "q": qty,
            "p": price,
            "ap": price,
            "X": "FILLED",
            "l": qty,
            "z": qty,
            "T": event_ms,
        },
    }


def test_force_order_stream_names_support_symbol_and_all_market() -> None:
    assert build_force_order_streams(mode="all_market") == ["!forceOrder@arr"]
    assert build_force_order_streams(symbols=["btcusdt"], mode="symbol") == ["btcusdt@forceOrder"]


def test_binance_force_order_payload_is_normalized() -> None:
    event = normalize_force_order_payload({"stream": "btcusdt@forceOrder", "data": _payload()})

    assert event is not None
    assert event.symbol == "BTCUSDT"
    assert event.side == "SELL"
    assert event.notional_value == Decimal("200.0000")
    assert event.event_time == datetime(2024, 3, 9, 16, 0, tzinfo=UTC)


def test_event_based_liquidation_pressure_is_computed() -> None:
    service = BinanceLiquidationFeedService(websocket_client=object())  # type: ignore[arg-type]
    event = normalize_force_order_payload(_payload(side="SELL", qty="1000", price="100"))
    assert event is not None

    service.add_event(event)
    snapshot = service.pressure_snapshot("BTCUSDT", now=event.event_time + timedelta(seconds=30))

    assert snapshot.recent_long_liquidation_notional == Decimal("100000.0000")
    assert snapshot.recent_short_liquidation_notional == Decimal("0.0000")
    assert snapshot.liquidation_pressure == "high"
    assert snapshot.liquidation_spike_detected is True
    assert snapshot.recent_liquidation_direction == "long"
