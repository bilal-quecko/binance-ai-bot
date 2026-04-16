"""Binance REST client scaffold."""

from typing import Any

import httpx

from app.config import Settings


class BinanceRestClient:
    """Minimal Binance REST client scaffold."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = httpx.AsyncClient(base_url=settings.binance_base_url, timeout=10.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def get_exchange_info(self) -> dict[str, Any]:
        response = await self._client.get("/api/v3/exchangeInfo")
        response.raise_for_status()
        return response.json()

    async def get_account_info(self) -> dict[str, Any]:
        raise NotImplementedError("Signed endpoints will be implemented in the next step.")

    async def place_order(self, **_: Any) -> dict[str, Any]:
        raise NotImplementedError("Order placement is intentionally disabled in scaffold stage.")
