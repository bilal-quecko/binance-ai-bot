from decimal import Decimal

import httpx
import pytest

from app.config import Settings
from app.data.binance_derivatives_data import BinanceDerivativesDataClient


@pytest.mark.asyncio
async def test_derivatives_snapshot_normalizes_real_funding_and_oi() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/fapi/v1/fundingRate":
            return httpx.Response(
                200,
                json=[
                    {"symbol": "BTCUSDT", "fundingRate": "0.00010000", "fundingTime": 1},
                    {"symbol": "BTCUSDT", "fundingRate": "0.00030000", "fundingTime": 2},
                ],
            )
        if request.url.path == "/fapi/v1/openInterest":
            return httpx.Response(200, json={"symbol": "BTCUSDT", "openInterest": "12345.5"})
        if request.url.path == "/futures/data/openInterestHist":
            return httpx.Response(
                200,
                json=[
                    {"sumOpenInterest": "100", "timestamp": 1},
                    {"sumOpenInterest": "103", "timestamp": 2},
                ],
            )
        return httpx.Response(404)

    async_client = httpx.AsyncClient(
        base_url="https://fapi.binance.com",
        transport=httpx.MockTransport(handler),
    )
    client = BinanceDerivativesDataClient(Settings(), client=async_client)
    try:
        snapshot = await client.snapshot("BTCUSDT")
    finally:
        await client.close()
        await async_client.aclose()

    assert snapshot.data_quality == "real"
    assert snapshot.funding_rate == Decimal("0.00030000")
    assert snapshot.funding_bias == "long"
    assert snapshot.open_interest == Decimal("12345.5")
    assert snapshot.oi_trend == "rising"


@pytest.mark.asyncio
async def test_derivatives_snapshot_falls_back_when_api_unavailable() -> None:
    async_client = httpx.AsyncClient(
        base_url="https://fapi.binance.com",
        transport=httpx.MockTransport(lambda request: httpx.Response(500)),
    )
    client = BinanceDerivativesDataClient(Settings(), client=async_client)
    try:
        snapshot = await client.snapshot("BTCUSDT")
    finally:
        await client.close()
        await async_client.aclose()

    assert snapshot.data_quality == "fallback"
    assert snapshot.funding_rate is None
    assert snapshot.oi_trend == "neutral"
