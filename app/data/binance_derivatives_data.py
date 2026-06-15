"""Binance USD-M Futures funding and open-interest data access."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Any, Literal

import httpx

from app.config import Settings, get_settings

LOGGER = logging.getLogger(__name__)

FundingBias = Literal["long", "short", "neutral"]
OiTrend = Literal["rising", "falling", "neutral"]
DerivativesDataQuality = Literal["real", "fallback"]


@dataclass(slots=True, frozen=True)
class BinanceDerivativesSnapshot:
    """Normalized Binance futures crowd-positioning inputs."""

    symbol: str
    funding_rate: Decimal | None
    funding_bias: FundingBias
    open_interest: Decimal | None
    oi_change_1h: Decimal | None
    oi_change_24h: Decimal | None
    oi_trend: OiTrend
    data_quality: DerivativesDataQuality
    explanation: str


FALLBACK_DERIVATIVES_SNAPSHOT = BinanceDerivativesSnapshot(
    symbol="",
    funding_rate=None,
    funding_bias="neutral",
    open_interest=None,
    oi_change_1h=None,
    oi_change_24h=None,
    oi_trend="neutral",
    data_quality="fallback",
    explanation="Binance futures funding/open-interest data is unavailable; crowd positioning is neutral fallback.",
)


class BinanceDerivativesDataClient:
    """Async client for Binance USD-M Futures market-data endpoints."""

    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        resolved = settings or get_settings()
        self._client = client or httpx.AsyncClient(
            base_url=resolved.binance_futures_base_url,
            timeout=10.0,
        )
        self._owns_client = client is None

    async def close(self) -> None:
        """Close the underlying client if owned."""

        if self._owns_client:
            await self._client.aclose()

    async def get_funding_rate(self, symbol: str, *, limit: int = 5) -> list[dict[str, Any]]:
        """Fetch recent funding-rate rows."""

        response = await self._client.get(
            "/fapi/v1/fundingRate",
            params={"symbol": symbol.upper(), "limit": max(1, min(limit, 100))},
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else []

    async def get_open_interest(self, symbol: str) -> dict[str, Any]:
        """Fetch current open interest."""

        response = await self._client.get("/fapi/v1/openInterest", params={"symbol": symbol.upper()})
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    async def get_open_interest_trend(self, symbol: str, *, period: str = "1h", limit: int = 24) -> list[dict[str, Any]]:
        """Fetch recent open-interest history when available."""

        response = await self._client.get(
            "/futures/data/openInterestHist",
            params={
                "symbol": symbol.upper(),
                "period": period,
                "limit": max(2, min(limit, 500)),
            },
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else []

    async def snapshot(self, symbol: str) -> BinanceDerivativesSnapshot:
        """Fetch and normalize funding/open-interest data."""

        normalized = symbol.upper()
        try:
            funding_rows = await self.get_funding_rate(normalized, limit=5)
            open_interest_row = await self.get_open_interest(normalized)
            oi_history = await self.get_open_interest_trend(normalized, period="1h", limit=24)
        except Exception as exc:
            LOGGER.warning("Binance derivatives data unavailable for %s: %s", normalized, exc)
            return fallback_derivatives_snapshot(normalized)

        funding_rate = _latest_funding_rate(funding_rows)
        open_interest = _decimal_or_none(open_interest_row.get("openInterest"))
        oi_change_1h = _oi_change_pct(oi_history, lookback=1)
        oi_change_24h = _oi_change_pct(oi_history, lookback=24)
        oi_trend = _oi_trend(oi_change_1h=oi_change_1h, oi_change_24h=oi_change_24h)
        funding_bias = _funding_bias(funding_rate)
        return BinanceDerivativesSnapshot(
            symbol=normalized,
            funding_rate=funding_rate,
            funding_bias=funding_bias,
            open_interest=open_interest,
            oi_change_1h=oi_change_1h,
            oi_change_24h=oi_change_24h,
            oi_trend=oi_trend,
            data_quality="real",
            explanation=(
                f"Funding bias is {funding_bias}; open interest trend is {oi_trend}. "
                "Data is from Binance USD-M Futures public market-data endpoints."
            ),
        )


async def get_funding_rate(symbol: str) -> Decimal | None:
    """Fetch the latest Binance funding rate for a symbol."""

    client = BinanceDerivativesDataClient()
    try:
        rows = await client.get_funding_rate(symbol, limit=5)
        return _latest_funding_rate(rows)
    finally:
        await client.close()


async def get_open_interest(symbol: str) -> Decimal | None:
    """Fetch current Binance open interest for a symbol."""

    client = BinanceDerivativesDataClient()
    try:
        row = await client.get_open_interest(symbol)
        return _decimal_or_none(row.get("openInterest"))
    finally:
        await client.close()


async def get_open_interest_trend(symbol: str) -> OiTrend:
    """Fetch and normalize the open-interest trend for a symbol."""

    client = BinanceDerivativesDataClient()
    try:
        rows = await client.get_open_interest_trend(symbol)
        return _oi_trend(oi_change_1h=_oi_change_pct(rows, lookback=1), oi_change_24h=_oi_change_pct(rows, lookback=24))
    finally:
        await client.close()


async def get_derivatives_snapshot(
    symbol: str,
    *,
    settings: Settings | None = None,
    client: BinanceDerivativesDataClient | None = None,
) -> BinanceDerivativesSnapshot:
    """Fetch a normalized Binance derivatives snapshot with safe fallback."""

    if client is not None:
        return await client.snapshot(symbol)
    owned = BinanceDerivativesDataClient(settings=settings)
    try:
        return await owned.snapshot(symbol)
    finally:
        await owned.close()


def fallback_derivatives_snapshot(symbol: str) -> BinanceDerivativesSnapshot:
    """Return a symbol-scoped fallback snapshot."""

    return BinanceDerivativesSnapshot(
        symbol=symbol.upper(),
        funding_rate=None,
        funding_bias="neutral",
        open_interest=None,
        oi_change_1h=None,
        oi_change_24h=None,
        oi_trend="neutral",
        data_quality="fallback",
        explanation="Binance futures funding/open-interest data is unavailable; crowd positioning is neutral fallback.",
    )


def _latest_funding_rate(rows: list[dict[str, Any]]) -> Decimal | None:
    if not rows:
        return None
    latest = max(rows, key=lambda item: int(item.get("fundingTime", 0)))
    return _decimal_or_none(latest.get("fundingRate"))


def _funding_bias(funding_rate: Decimal | None) -> FundingBias:
    if funding_rate is None or abs(funding_rate) < Decimal("0.00005"):
        return "neutral"
    return "long" if funding_rate > Decimal("0") else "short"


def _oi_trend(*, oi_change_1h: Decimal | None, oi_change_24h: Decimal | None) -> OiTrend:
    basis = oi_change_1h if oi_change_1h is not None else oi_change_24h
    if basis is None or abs(basis) < Decimal("0.2500"):
        return "neutral"
    return "rising" if basis > Decimal("0") else "falling"


def _oi_change_pct(rows: list[dict[str, Any]], *, lookback: int) -> Decimal | None:
    if len(rows) < 2:
        return None
    ordered = sorted(rows, key=lambda item: int(item.get("timestamp", 0)))
    latest = _decimal_or_none(ordered[-1].get("sumOpenInterest") or ordered[-1].get("sumOpenInterestValue"))
    prior_index = max(0, len(ordered) - 1 - lookback)
    prior = _decimal_or_none(ordered[prior_index].get("sumOpenInterest") or ordered[prior_index].get("sumOpenInterestValue"))
    if latest is None or prior is None or prior <= Decimal("0"):
        return None
    return (((latest - prior) / prior) * Decimal("100")).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except ArithmeticError:
        return None
