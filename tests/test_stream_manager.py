import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.exchange.binance_ws import BinanceWebSocketClient
from app.market_data.models import MarketSnapshot
from app.market_data.stream_manager import StreamManager


class FakeWebSocket:
    def __init__(self, events: list[Any]) -> None:
        self._events = list(events)

    async def recv(self) -> str:
        if not self._events:
            raise RuntimeError("connection closed")

        next_event = self._events.pop(0)
        if isinstance(next_event, Exception):
            raise next_event
        return str(next_event)


class FakeConnector:
    def __init__(self, connections: list[list[Any]]) -> None:
        self._connections = list(connections)
        self.urls: list[str] = []

    @asynccontextmanager
    async def __call__(self, url: str) -> AsyncIterator[FakeWebSocket]:
        self.urls.append(url)
        websocket = FakeWebSocket(self._connections.pop(0))
        yield websocket


class FakeStreamClient:
    def __init__(self, payloads: list[dict[str, Any]]) -> None:
        self._payloads = payloads
        self.streams_seen: list[list[str]] = []

    async def messages(self, streams: list[str]) -> AsyncIterator[dict[str, Any]]:
        self.streams_seen.append(streams)
        for payload in self._payloads:
            yield payload


@pytest.mark.asyncio
async def test_binance_websocket_client_reconnects_and_yields_combined_payload_data() -> None:
    sleep_calls: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    connector = FakeConnector(
        connections=[
            [
                json.dumps(
                    {
                        "stream": "btcusdt@trade",
                        "data": {"e": "trade", "s": "BTCUSDT", "E": 1710000000123, "t": 1, "p": "10", "q": "1", "T": 1710000000123, "m": False},
                    }
                ),
                RuntimeError("socket dropped"),
            ],
            [
                json.dumps(
                    {
                        "stream": "btcusdt@bookticker",
                        "data": {"e": "bookTicker", "s": "BTCUSDT", "E": 1710000000456, "u": 10, "b": "9.9", "B": "2", "a": "10.1", "A": "3"},
                    }
                )
            ],
        ]
    )
    client = BinanceWebSocketClient(
        base_url="wss://stream.binance.com:9443/ws",
        connector=connector,
        sleep_fn=fake_sleep,
        reconnect_delay=0.25,
        max_reconnect_delay=1.0,
    )

    messages: list[dict[str, Any]] = []
    async for payload in client.messages(["btcusdt@trade", "btcusdt@bookTicker"]):
        messages.append(payload)
        if len(messages) == 2:
            break

    assert connector.urls == [
        "wss://stream.binance.com:9443/stream?streams=btcusdt@trade/btcusdt@bookticker",
        "wss://stream.binance.com:9443/stream?streams=btcusdt@trade/btcusdt@bookticker",
    ]
    assert sleep_calls == [0.25]
    assert messages[0]["e"] == "trade"
    assert messages[1]["e"] == "bookTicker"


def test_stream_manager_merges_snapshot_updates_and_detects_staleness() -> None:
    clock = datetime(2024, 3, 9, 16, 0, 1, tzinfo=UTC)
    manager = StreamManager(stale_after=timedelta(seconds=2), time_provider=lambda: clock)

    trade_snapshot = manager.normalize_trade(
        {
            "e": "trade",
            "E": 1710000000123,
            "s": "BTCUSDT",
            "t": 10,
            "p": "68000.12",
            "q": "0.2",
            "T": 1710000000120,
            "m": False,
        }
    )
    merged_snapshot = manager.normalize_top_of_book(
        {
            "e": "bookTicker",
            "E": 1710000000456,
            "s": "BTCUSDT",
            "u": 20,
            "b": "67999.90",
            "B": "1.1",
            "a": "68000.10",
            "A": "0.9",
        }
    )

    assert trade_snapshot.last_price == Decimal("68000.12")
    assert merged_snapshot.trade is not None
    assert merged_snapshot.top_of_book is not None
    assert merged_snapshot.bid_price == Decimal("67999.90")
    assert merged_snapshot.ask_price == Decimal("68000.10")
    assert merged_snapshot.is_stale is False

    clock = clock + timedelta(seconds=3)
    stale_snapshot = manager.get_snapshot("BTCUSDT")

    assert stale_snapshot is not None
    assert stale_snapshot.is_stale is True
    assert manager.stale_symbols() == ["BTCUSDT"]


@pytest.mark.asyncio
async def test_stream_manager_stream_normalizes_supported_payloads() -> None:
    payloads = [
        {
            "stream": "btcusdt@trade",
            "data": {
                "e": "trade",
                "E": 1710000000123,
                "s": "BTCUSDT",
                "t": 11,
                "p": "68001.00",
                "q": "0.1",
                "T": 1710000000123,
                "m": True,
            },
        },
        {
            "stream": "btcusdt@kline_1m",
            "data": {
                "e": "kline",
                "E": 1710000000789,
                "s": "BTCUSDT",
                "k": {
                    "t": 1710000000000,
                    "T": 1710000059999,
                    "i": "1m",
                    "o": "67950.00",
                    "c": "68010.50",
                    "h": "68025.00",
                    "l": "67940.10",
                    "v": "12.345",
                    "n": 105,
                    "x": True,
                    "q": "839999.99",
                },
            },
        },
        {"stream": "btcusdt@ignored", "data": {"e": "24hrTicker", "s": "BTCUSDT"}},
    ]
    client = FakeStreamClient(payloads)
    manager = StreamManager(websocket_client=client)

    stream = manager.stream(["btcusdt@trade", "btcusdt@kline_1m"])
    snapshots: list[MarketSnapshot] = []

    try:
        snapshots.append(await anext(stream))
        snapshots.append(await anext(stream))
    finally:
        await stream.aclose()

    assert client.streams_seen == [["btcusdt@trade", "btcusdt@kline_1m"]]
    assert len(snapshots) == 2
    assert snapshots[0].trade is not None
    assert snapshots[0].last_price == Decimal("68001.00")
    assert snapshots[1].candle is not None
    assert snapshots[1].candle.is_closed is True
    assert snapshots[1].last_price == Decimal("68010.50")
