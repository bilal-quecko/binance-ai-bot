"""Generic HTTP adapter for vendor-provided liquidation heatmap snapshots."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import json
import logging
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.data.heatmap_models import HeatmapBias, HeatmapSnapshot, unavailable_heatmap_snapshot

LOGGER = logging.getLogger(__name__)


class VendorHeatmapProvider:
    """Configurable vendor heatmap adapter.

    The adapter expects the configured endpoint to return already-normalizable
    JSON fields. Unknown formats return unavailable instead of inventing data.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        vendor_name: str,
        clusters_path: str,
        symbol_param: str = "symbol",
        timeout_seconds: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.vendor_name = vendor_name or "vendor_http"
        self.clusters_path = clusters_path
        self.symbol_param = symbol_param or "symbol"
        self.timeout_seconds = timeout_seconds

    def snapshot(self, *, symbol: str, current_price: Decimal | None) -> HeatmapSnapshot:
        """Fetch and normalize one vendor heatmap snapshot."""

        if not self.base_url or not self.api_key or not self.clusters_path:
            return unavailable_heatmap_snapshot(
                symbol=symbol,
                provider=self.vendor_name,
                current_price=current_price,
                explanation="Vendor heatmap provider is not configured.",
            )
        url = self._url(symbol)
        request = Request(
            url,
            headers={
                "accept": "application/json",
                "authorization": f"Bearer {self.api_key}",
                "x-api-key": self.api_key,
            },
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, json.JSONDecodeError) as exc:
            LOGGER.warning("Vendor heatmap provider %s unavailable for %s: %s", self.vendor_name, symbol, exc)
            return unavailable_heatmap_snapshot(
                symbol=symbol,
                provider=self.vendor_name,
                current_price=current_price,
                explanation=f"Vendor heatmap provider unavailable: {exc}",
            )
        parsed = normalize_vendor_heatmap_payload(
            payload,
            symbol=symbol,
            provider=self.vendor_name,
            current_price=current_price,
        )
        if parsed is None:
            return unavailable_heatmap_snapshot(
                symbol=symbol,
                provider=self.vendor_name,
                current_price=current_price,
                explanation="Vendor response format is unsupported; no real heatmap data was used.",
            )
        return parsed

    def _url(self, symbol: str) -> str:
        path = self.clusters_path if self.clusters_path.startswith("/") else f"/{self.clusters_path}"
        separator = "&" if "?" in path else "?"
        return f"{self.base_url}{path}{separator}{urlencode({self.symbol_param: symbol.upper()})}"


def normalize_vendor_heatmap_payload(
    payload: Any,
    *,
    symbol: str,
    provider: str,
    current_price: Decimal | None,
) -> HeatmapSnapshot | None:
    """Normalize a vendor response if it exposes supported fields."""

    if not isinstance(payload, dict):
        return None
    source = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(source, dict):
        return None
    try:
        price = _optional_decimal(source.get("current_price")) or current_price
        above = _optional_decimal(
            source.get("nearest_liquidity_above")
            or source.get("liquidity_above")
            or source.get("heatmap_liquidity_above")
        )
        below = _optional_decimal(
            source.get("nearest_liquidity_below")
            or source.get("liquidity_below")
            or source.get("heatmap_liquidity_below")
        )
        above_intensity = _bounded_int(source.get("liquidity_above_intensity") or source.get("above_intensity"))
        below_intensity = _bounded_int(source.get("liquidity_below_intensity") or source.get("below_intensity"))
        intensity = _bounded_int(source.get("heatmap_intensity_score") or max(above_intensity, below_intensity))
    except (ValueError, ArithmeticError):
        return None
    if above is None and below is None and intensity <= 0:
        return None
    bias = _bias_from_fields(
        raw_bias=source.get("heatmap_bias"),
        above_intensity=above_intensity,
        below_intensity=below_intensity,
    )
    return HeatmapSnapshot(
        symbol=symbol.upper(),
        provider=provider,
        provider_status="available",
        timestamp=_timestamp(source.get("raw_timestamp") or source.get("timestamp")),
        current_price=price,
        nearest_liquidity_above=above,
        nearest_liquidity_below=below,
        liquidity_above_intensity=above_intensity,
        liquidity_below_intensity=below_intensity,
        heatmap_intensity_score=intensity,
        heatmap_bias=bias,
        liquidation_pressure="high" if intensity >= 75 else "medium" if intensity >= 45 else "low",
        liquidation_imbalance=None,
        data_quality="vendor_heatmap",
        is_real_data=True,
        explanation=f"Vendor heatmap data from {provider}; endpoint response was normalized without changing base scoring.",
    )


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _bounded_int(value: Any) -> int:
    try:
        return max(0, min(100, int(value)))
    except (TypeError, ValueError):
        return 0


def _bias_from_fields(*, raw_bias: Any, above_intensity: int, below_intensity: int) -> HeatmapBias:
    normalized = str(raw_bias or "").lower()
    if normalized in {"upside_squeeze", "downside_sweep", "neutral"}:
        return normalized  # type: ignore[return-value]
    if above_intensity >= below_intensity + 12 and above_intensity >= 60:
        return "upside_squeeze"
    if below_intensity >= above_intensity + 12 and below_intensity >= 60:
        return "downside_sweep"
    return "neutral"


def _timestamp(value: Any) -> datetime:
    if value is None:
        return datetime.now(tz=UTC)
    if isinstance(value, int | float):
        numeric = float(value)
        if numeric > 10_000_000_000:
            numeric /= 1000
        return datetime.fromtimestamp(numeric, tz=UTC)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    except ValueError:
        return datetime.now(tz=UTC)
