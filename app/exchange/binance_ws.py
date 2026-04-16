"""Binance websocket client with reconnect-safe streaming."""

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol

import websockets


class WebSocketReceiver(Protocol):
    """Minimal protocol for websocket receive operations used by the client."""

    async def recv(self) -> str:
        """Receive the next raw websocket message."""


Connector = Callable[[str], AbstractAsyncContextManager[WebSocketReceiver]]
SleepFn = Callable[[float], Awaitable[None]]


class BinanceWebSocketClient:
    """Reconnect-safe Binance Spot websocket client."""

    def __init__(
        self,
        base_url: str,
        connector: Connector | None = None,
        sleep_fn: SleepFn | None = None,
        reconnect_delay: float = 1.0,
        max_reconnect_delay: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._connector = connector or websockets.connect
        self._sleep = sleep_fn or asyncio.sleep
        self._reconnect_delay = reconnect_delay
        self._max_reconnect_delay = max_reconnect_delay

    def _build_stream_url(self, streams: Sequence[str]) -> str:
        """Build a Binance combined stream URL."""

        normalized_streams = [stream.strip().lower() for stream in streams if stream.strip()]
        if not normalized_streams:
            raise ValueError("At least one Binance websocket stream is required.")

        stream_path = "/".join(normalized_streams)
        if self.base_url.endswith("/ws"):
            return f"{self.base_url[:-3]}/stream?streams={stream_path}"
        if self.base_url.endswith("/stream"):
            return f"{self.base_url}?streams={stream_path}"
        return f"{self.base_url}/stream?streams={stream_path}"

    async def connect(self, streams: Sequence[str]) -> AbstractAsyncContextManager[WebSocketReceiver]:
        """Return a websocket context manager for the requested streams."""

        return self._connector(self._build_stream_url(streams))

    async def messages(self, streams: Sequence[str]) -> AsyncIterator[dict[str, Any]]:
        """Yield decoded websocket payloads and reconnect on disconnects."""

        url = self._build_stream_url(streams)
        backoff = self._reconnect_delay

        while True:
            try:
                async with self._connector(url) as websocket:
                    backoff = self._reconnect_delay
                    while True:
                        raw_message = await websocket.recv()
                        payload = json.loads(raw_message)
                        yield payload.get("data", payload)
            except asyncio.CancelledError:
                raise
            except Exception:
                await self._sleep(backoff)
                backoff = min(backoff * 2, self._max_reconnect_delay)
