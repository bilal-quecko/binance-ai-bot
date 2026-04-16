"""Binance WebSocket scaffold."""

from collections.abc import AsyncIterator


class BinanceWebSocketClient:
    """Minimal stream client placeholder."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    async def connect(self) -> None:
        return None

    async def messages(self) -> AsyncIterator[dict]:
        if False:
            yield {}
        return
