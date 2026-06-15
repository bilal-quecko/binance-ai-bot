import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.monitoring.futures_scanner_ws_heartbeat import (
    FuturesScannerWebSocketHeartbeatService,
    sanitize_scanner_symbols,
)


class FakeMiniTickerClient:
    def __init__(self, payloads: list[dict[str, Any]] | None = None) -> None:
        self.payloads = payloads or []
        self.streams: list[str] = []

    async def messages(self, streams):
        self.streams = list(streams)
        for payload in self.payloads:
            yield payload


def test_sanitize_scanner_symbols_dedupes_filters_and_caps() -> None:
    symbols = ["btcusdt", "ETHUSDT", "bad/usdt", "btcusdt", "", "SOLUSDT"]

    assert sanitize_scanner_symbols(symbols, max_symbols=2) == ("BTCUSDT", "ETHUSDT")


@pytest.mark.asyncio
async def test_subscription_update_sanitizes_symbols() -> None:
    client = FakeMiniTickerClient()
    service = FuturesScannerWebSocketHeartbeatService(client)

    subscribed = await service.update_subscriptions(["btcusdt", "bad/usdt", "ETHUSDT", "btcusdt"])
    await asyncio.sleep(0)
    await service.close()

    assert subscribed == ("BTCUSDT", "ETHUSDT")
    assert client.streams == ["btcusdt@markPrice", "ethusdt@markPrice"]


@pytest.mark.asyncio
async def test_empty_subscription_list_is_safe() -> None:
    service = FuturesScannerWebSocketHeartbeatService(FakeMiniTickerClient())

    subscribed = await service.update_subscriptions([])
    await service.close()

    assert subscribed == ()
    assert service.active_symbols == ()


@pytest.mark.asyncio
async def test_websocket_payload_updates_latest_price_cache() -> None:
    event_time = datetime(2024, 3, 9, 16, 0, tzinfo=UTC)
    client = FakeMiniTickerClient(
        [{"s": "BTCUSDT", "p": "43210.50", "E": int(event_time.timestamp() * 1000)}]
    )
    service = FuturesScannerWebSocketHeartbeatService(client)

    await service.update_subscriptions(["BTCUSDT"])
    await asyncio.sleep(0)
    await service.close()
    prices = service.latest_prices(["BTCUSDT"], now=event_time + timedelta(seconds=2))

    assert prices["BTCUSDT"].live_price == Decimal("43210.50")
    assert prices["BTCUSDT"].source == "websocket"
    assert prices["BTCUSDT"].price_type == "mark_price"
    assert prices["BTCUSDT"].stale is False


@pytest.mark.asyncio
async def test_websocket_combined_payload_updates_latest_price_cache() -> None:
    event_time = datetime(2024, 3, 9, 16, 0, tzinfo=UTC)
    client = FakeMiniTickerClient(
        [
            {
                "stream": "btcusdt@markPrice",
                "data": {"s": "BTCUSDT", "p": "43211.75", "E": int(event_time.timestamp() * 1000)},
            }
        ]
    )
    service = FuturesScannerWebSocketHeartbeatService(client)

    await service.update_subscriptions(["BTCUSDT"])
    await asyncio.sleep(0)
    await service.close()
    prices = service.latest_prices(["BTCUSDT"], now=event_time + timedelta(seconds=2))

    assert prices["BTCUSDT"].live_price == Decimal("43211.75")
    assert prices["BTCUSDT"].source == "websocket"
    assert prices["BTCUSDT"].stale is False


@pytest.mark.asyncio
async def test_stale_websocket_cache_is_marked_cache() -> None:
    event_time = datetime(2024, 3, 9, 16, 0, tzinfo=UTC)
    client = FakeMiniTickerClient(
        [{"s": "BTCUSDT", "p": "43210.50", "E": int(event_time.timestamp() * 1000)}]
    )
    service = FuturesScannerWebSocketHeartbeatService(client)

    await service.update_subscriptions(["BTCUSDT"])
    await asyncio.sleep(0)
    await service.close()
    prices = service.latest_prices(["BTCUSDT"], now=event_time + timedelta(seconds=6))

    assert prices["BTCUSDT"].live_price == Decimal("43210.50")
    assert prices["BTCUSDT"].source == "cache"
    assert prices["BTCUSDT"].stale is True
