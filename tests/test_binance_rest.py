from decimal import Decimal
from urllib.parse import parse_qsl

import httpx
import pytest

from app.config import Settings
from app.exchange.auth import sign_query
from app.exchange.binance_rest import BinanceRestClient
from app.exchange.models import AccountInfo, ExchangeInfo


@pytest.mark.asyncio
async def test_signed_request_adds_signature_and_api_key() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/v3/account"
        assert request.headers["X-MBX-APIKEY"] == "test-key"

        query = request.url.query.decode()
        signed_query, signature = query.rsplit("&signature=", maxsplit=1)
        params = dict(parse_qsl(signed_query))

        assert params["recvWindow"] == "5000"
        assert params["timestamp"] == "1700000000000"
        assert signature == sign_query(signed_query, "test-secret")

        return httpx.Response(
            200,
            json={
                "makerCommission": 15,
                "takerCommission": 15,
                "buyerCommission": 0,
                "sellerCommission": 0,
                "canTrade": True,
                "canWithdraw": True,
                "canDeposit": True,
                "accountType": "SPOT",
                "updateTime": 1700000000123,
                "permissions": ["SPOT"],
                "balances": [],
            },
        )

    settings = Settings(
        BINANCE_API_KEY="test-key",
        BINANCE_API_SECRET="test-secret",
        BINANCE_BASE_URL="https://api.binance.com",
    )
    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(base_url=settings.binance_base_url, transport=transport) as http_client:
        client = BinanceRestClient(
            settings=settings,
            client=http_client,
            time_provider=lambda: 1700000000000,
        )

        payload = await client.signed_request("GET", "/api/v3/account")

    assert payload["accountType"] == "SPOT"


@pytest.mark.asyncio
async def test_get_account_info_parses_balances() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "makerCommission": 15,
                "takerCommission": 15,
                "buyerCommission": 0,
                "sellerCommission": 0,
                "canTrade": True,
                "canWithdraw": True,
                "canDeposit": True,
                "accountType": "SPOT",
                "updateTime": 1700000000456,
                "permissions": ["SPOT"],
                "balances": [
                    {"asset": "BTC", "free": "0.12300000", "locked": "0.01000000"},
                    {"asset": "USDT", "free": "150.50000000", "locked": "0.00000000"},
                ],
            },
        )

    settings = Settings(
        BINANCE_API_KEY="test-key",
        BINANCE_API_SECRET="test-secret",
        BINANCE_BASE_URL="https://api.binance.com",
    )
    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(base_url=settings.binance_base_url, transport=transport) as http_client:
        client = BinanceRestClient(
            settings=settings,
            client=http_client,
            time_provider=lambda: 1700000000000,
        )
        account = await client.get_account_info()

    assert isinstance(account, AccountInfo)
    assert account.account_type == "SPOT"
    assert account.permissions == ["SPOT"]
    assert account.balances[0].asset == "BTC"
    assert account.balances[0].free == Decimal("0.12300000")
    assert account.balances[0].locked == Decimal("0.01000000")


@pytest.mark.asyncio
async def test_get_exchange_info_parses_typed_filters() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "timezone": "UTC",
                "serverTime": 1700000000999,
                "symbols": [
                    {
                        "symbol": "BTCUSDT",
                        "status": "TRADING",
                        "baseAsset": "BTC",
                        "quoteAsset": "USDT",
                        "baseAssetPrecision": 8,
                        "quoteAssetPrecision": 8,
                        "orderTypes": ["LIMIT", "MARKET"],
                        "permissions": ["SPOT"],
                        "filters": [
                            {
                                "filterType": "PRICE_FILTER",
                                "minPrice": "0.01000000",
                                "maxPrice": "1000000.00000000",
                                "tickSize": "0.01000000",
                            },
                            {
                                "filterType": "LOT_SIZE",
                                "minQty": "0.00001000",
                                "maxQty": "9000.00000000",
                                "stepSize": "0.00001000",
                            },
                            {
                                "filterType": "MARKET_LOT_SIZE",
                                "minQty": "0.00000000",
                                "maxQty": "12.50000000",
                                "stepSize": "0.00001000",
                            },
                            {
                                "filterType": "NOTIONAL",
                                "minNotional": "10.00000000",
                                "maxNotional": "1000000.00000000",
                                "applyMinToMarket": True,
                                "applyMaxToMarket": False,
                                "avgPriceMins": 5,
                            },
                        ],
                    },
                    {
                        "symbol": "ETHUSDT",
                        "status": "TRADING",
                        "baseAsset": "ETH",
                        "quoteAsset": "USDT",
                        "baseAssetPrecision": 8,
                        "quoteAssetPrecision": 8,
                        "orderTypes": ["LIMIT", "MARKET"],
                        "permissions": ["SPOT"],
                        "filters": [
                            {
                                "filterType": "PRICE_FILTER",
                                "minPrice": "0.01000000",
                                "maxPrice": "1000000.00000000",
                                "tickSize": "0.01000000",
                            },
                            {
                                "filterType": "LOT_SIZE",
                                "minQty": "0.00010000",
                                "maxQty": "100000.00000000",
                                "stepSize": "0.00010000",
                            },
                            {
                                "filterType": "MIN_NOTIONAL",
                                "minNotional": "10.00000000",
                                "applyToMarket": True,
                                "avgPriceMins": 5,
                            },
                        ],
                    },
                ],
            },
        )

    settings = Settings(BINANCE_BASE_URL="https://api.binance.com")
    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(base_url=settings.binance_base_url, transport=transport) as http_client:
        client = BinanceRestClient(settings=settings, client=http_client)
        exchange_info = await client.get_exchange_info()

    assert isinstance(exchange_info, ExchangeInfo)
    assert exchange_info.timezone == "UTC"
    assert len(exchange_info.symbols) == 2

    btcusdt = exchange_info.symbols[0]
    assert btcusdt.filters.price is not None
    assert btcusdt.filters.price.tick_size == Decimal("0.01000000")
    assert btcusdt.filters.lot_size is not None
    assert btcusdt.filters.lot_size.step_size == Decimal("0.00001000")
    assert btcusdt.filters.market_lot_size is not None
    assert btcusdt.filters.market_lot_size.max_qty == Decimal("12.50000000")
    assert btcusdt.filters.notional is not None
    assert btcusdt.filters.notional.filter_type == "NOTIONAL"
    assert btcusdt.filters.notional.max_notional == Decimal("1000000.00000000")

    ethusdt = exchange_info.symbols[1]
    assert ethusdt.filters.notional is not None
    assert ethusdt.filters.notional.filter_type == "MIN_NOTIONAL"
    assert ethusdt.filters.notional.min_notional == Decimal("10.00000000")


@pytest.mark.asyncio
async def test_place_order_is_disabled_outside_paper_mode() -> None:
    settings = Settings(APP_MODE="live")
    client = BinanceRestClient(settings=settings)

    try:
        with pytest.raises(RuntimeError, match="disabled unless paper mode"):
            await client.place_order(symbol="BTCUSDT", side="BUY")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_place_order_returns_stub_in_paper_mode() -> None:
    settings = Settings(APP_MODE="paper")
    client = BinanceRestClient(settings=settings)

    try:
        result = await client.place_order(symbol="BTCUSDT", side="BUY", quantity="0.01")
    finally:
        await client.close()

    assert result["status"] == "paper_only"
    assert result["order"]["symbol"] == "BTCUSDT"
