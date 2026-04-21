"""Binance Spot REST client."""

from collections.abc import Callable, Mapping
from decimal import Decimal
import time
from typing import Any
from urllib.parse import urlencode

import httpx

from app.config import Settings
from app.exchange.auth import sign_query
from app.exchange.filters import parse_symbol_filters
from app.exchange.models import AccountBalance, AccountInfo, ExchangeInfo, ExchangeSymbol


def _serialize_param_value(value: Any) -> str:
    """Serialize a request parameter for Binance query strings."""

    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


class BinanceRestClient:
    """Async Binance Spot REST client with signed request support."""

    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        time_provider: Callable[[], int] | None = None,
    ) -> None:
        self.settings = settings
        self._client = client or httpx.AsyncClient(
            base_url=settings.binance_base_url,
            timeout=10.0,
        )
        self._owns_client = client is None
        self._time_provider = time_provider or self._default_timestamp_ms

    @staticmethod
    def _default_timestamp_ms() -> int:
        """Return the current Unix timestamp in milliseconds."""

        return int(time.time() * 1000)

    async def close(self) -> None:
        """Close the underlying HTTP client if this instance owns it."""

        if self._owns_client:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        signed: bool = False,
        recv_window: int = 5_000,
    ) -> Any:
        """Send a Binance REST request and return the decoded JSON payload."""

        request_params = {key: _serialize_param_value(value) for key, value in (params or {}).items()}
        headers: dict[str, str] = {}

        if signed:
            if not self.settings.binance_api_key or not self.settings.binance_api_secret:
                raise ValueError("Signed Binance requests require both API key and API secret.")
            request_params["timestamp"] = str(self._time_provider())
            request_params["recvWindow"] = str(recv_window)
            query_string = urlencode(request_params)
            request_params["signature"] = sign_query(query_string, self.settings.binance_api_secret)
            headers["X-MBX-APIKEY"] = self.settings.binance_api_key

        response = await self._client.request(method=method, url=path, params=request_params, headers=headers)
        response.raise_for_status()
        return response.json()

    async def get_exchange_info(self) -> ExchangeInfo:
        """Fetch and normalize Binance Spot exchange metadata."""

        payload = await self._request("GET", "/api/v3/exchangeInfo")
        symbols = [
            ExchangeSymbol(
                symbol=raw_symbol["symbol"],
                status=raw_symbol["status"],
                base_asset=raw_symbol["baseAsset"],
                quote_asset=raw_symbol["quoteAsset"],
                base_asset_precision=int(raw_symbol["baseAssetPrecision"]),
                quote_asset_precision=int(raw_symbol["quoteAssetPrecision"]),
                order_types=list(raw_symbol.get("orderTypes", [])),
                permissions=list(raw_symbol.get("permissions", [])),
                filters=parse_symbol_filters(
                    symbol=raw_symbol["symbol"],
                    raw_filters=raw_symbol.get("filters", []),
                ),
            )
            for raw_symbol in payload.get("symbols", [])
        ]
        return ExchangeInfo(
            timezone=payload["timezone"],
            server_time=int(payload["serverTime"]),
            symbols=symbols,
        )

    async def get_ticker_24h(self) -> list[dict[str, Any]]:
        """Fetch 24-hour ticker statistics for all Spot symbols."""

        payload = await self._request("GET", "/api/v3/ticker/24hr")
        if not isinstance(payload, list):
            raise ValueError("Expected Binance 24h ticker response to be a list.")
        return [item for item in payload if isinstance(item, dict)]

    async def get_account_info(self) -> AccountInfo:
        """Fetch Binance Spot account information via a signed request."""

        payload = await self._request("GET", "/api/v3/account", signed=True)
        balances = [
            AccountBalance(
                asset=raw_balance["asset"],
                free=Decimal(raw_balance["free"]),
                locked=Decimal(raw_balance["locked"]),
            )
            for raw_balance in payload.get("balances", [])
        ]
        return AccountInfo(
            maker_commission=int(payload["makerCommission"]),
            taker_commission=int(payload["takerCommission"]),
            buyer_commission=int(payload["buyerCommission"]),
            seller_commission=int(payload["sellerCommission"]),
            can_trade=bool(payload["canTrade"]),
            can_withdraw=bool(payload["canWithdraw"]),
            can_deposit=bool(payload["canDeposit"]),
            account_type=str(payload.get("accountType", "SPOT")),
            update_time=int(payload["updateTime"]),
            permissions=list(payload.get("permissions", [])),
            balances=balances,
        )

    async def signed_request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        recv_window: int = 5_000,
    ) -> Any:
        """Send a reusable signed Binance request."""

        return await self._request(
            method=method,
            path=path,
            params=params,
            signed=True,
            recv_window=recv_window,
        )

    async def place_order(self, **order_params: Any) -> dict[str, Any]:
        """Keep live Binance order placement disabled outside paper mode."""

        if self.settings.app_mode != "paper":
            raise RuntimeError("Binance live order placement is disabled unless paper mode is active.")

        return {
            "status": "paper_only",
            "message": "Binance Spot live order placement is disabled in this module.",
            "order": order_params,
        }
