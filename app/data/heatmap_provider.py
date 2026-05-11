"""Liquidation heatmap provider abstraction.

Mock remains the default. Real-capable providers are optional and clearly
label whether data is mock, event-based, vendor heatmap, or unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import logging
from typing import Protocol

from app.config import Settings, get_settings
from app.data.binance_liquidation_feed import get_global_liquidation_feed_service
from app.data.heatmap_models import (
    HeatmapAlignment,
    HeatmapBias,
    HeatmapSignalEnrichment,
    HeatmapSnapshot,
    LiquidationCluster,
    unavailable_heatmap_snapshot,
)
from app.data.vendor_heatmap_provider import VendorHeatmapProvider

LOGGER = logging.getLogger(__name__)


class HeatmapProvider(Protocol):
    """Provider contract for normalized heatmap snapshots."""

    provider_name: str

    def snapshot(self, *, symbol: str, current_price: Decimal | None) -> HeatmapSnapshot:
        """Return a normalized heatmap snapshot."""


@dataclass(slots=True, frozen=True)
class HeatmapProviderSelection:
    """Resolved provider state for status endpoints."""

    configured_provider: str
    active_provider: str
    provider_status: str
    explanation: str


class MockHeatmapProvider:
    """Deterministic local heatmap provider used by default."""

    provider_name = "mock"

    def snapshot(self, *, symbol: str, current_price: Decimal | None) -> HeatmapSnapshot:
        anchor = current_price if current_price is not None and current_price > 0 else _mock_anchor(symbol)
        skew = _mock_skew(symbol)
        above_intensity = min(100, 55 + max(skew, 0))
        below_intensity = min(100, 55 + max(-skew, 0))
        above = _quantize_price(anchor * Decimal("1.012"))
        below = _quantize_price(anchor * Decimal("0.988"))
        bias = _heatmap_bias_from_intensity(above_intensity=above_intensity, below_intensity=below_intensity)
        intensity = max(above_intensity, below_intensity)
        return HeatmapSnapshot(
            symbol=symbol.upper(),
            provider=self.provider_name,
            provider_status="available",
            timestamp=datetime.now(tz=UTC),
            current_price=anchor,
            nearest_liquidity_above=above,
            nearest_liquidity_below=below,
            liquidity_above_intensity=above_intensity,
            liquidity_below_intensity=below_intensity,
            heatmap_intensity_score=intensity,
            heatmap_bias=bias,
            liquidation_pressure="medium" if intensity >= 65 else "low",
            liquidation_imbalance=None,
            data_quality="mock",
            is_real_data=False,
            explanation="Mock heatmap data is deterministic scaffolding. Do not treat it as real market heatmap.",
        )

    def get_liquidation_clusters(self, symbol: str) -> list[LiquidationCluster]:
        snapshot = self.snapshot(symbol=symbol, current_price=None)
        clusters: list[LiquidationCluster] = []
        if snapshot.nearest_liquidity_above is not None:
            clusters.append(
                LiquidationCluster(
                    symbol=snapshot.symbol,
                    level=snapshot.nearest_liquidity_above,
                    side="above",
                    intensity=snapshot.liquidity_above_intensity,
                    source=self.provider_name,
                )
            )
        if snapshot.nearest_liquidity_below is not None:
            clusters.append(
                LiquidationCluster(
                    symbol=snapshot.symbol,
                    level=snapshot.nearest_liquidity_below,
                    side="below",
                    intensity=snapshot.liquidity_below_intensity,
                    source=self.provider_name,
                )
            )
        return clusters

    def get_nearest_liquidity_above(self, symbol: str, price: Decimal) -> LiquidationCluster | None:
        snapshot = self.snapshot(symbol=symbol, current_price=price)
        if snapshot.nearest_liquidity_above is None:
            return None
        return LiquidationCluster(
            symbol=snapshot.symbol,
            level=snapshot.nearest_liquidity_above,
            side="above",
            intensity=snapshot.liquidity_above_intensity,
            source=self.provider_name,
        )

    def get_nearest_liquidity_below(self, symbol: str, price: Decimal) -> LiquidationCluster | None:
        snapshot = self.snapshot(symbol=symbol, current_price=price)
        if snapshot.nearest_liquidity_below is None:
            return None
        return LiquidationCluster(
            symbol=snapshot.symbol,
            level=snapshot.nearest_liquidity_below,
            side="below",
            intensity=snapshot.liquidity_below_intensity,
            source=self.provider_name,
        )

    def get_liquidity_intensity(self, symbol: str) -> int:
        return self.snapshot(symbol=symbol, current_price=None).heatmap_intensity_score


class BinanceForceOrderHeatmapProvider:
    """Event-based heatmap provider from Binance force-order activity."""

    provider_name = "binance_force_orders"

    def snapshot(self, *, symbol: str, current_price: Decimal | None) -> HeatmapSnapshot:
        service = get_global_liquidation_feed_service()
        if service is None:
            return unavailable_heatmap_snapshot(
                symbol=symbol,
                provider=self.provider_name,
                current_price=current_price,
                explanation="Binance force-order feed is not running; falling back to mock heatmap data.",
            )
        pressure = service.pressure_snapshot(symbol)
        if not pressure.data_available:
            return HeatmapSnapshot(
                symbol=symbol.upper(),
                provider=self.provider_name,
                provider_status="available",
                timestamp=pressure.timestamp,
                current_price=current_price,
                nearest_liquidity_above=None,
                nearest_liquidity_below=None,
                liquidity_above_intensity=0,
                liquidity_below_intensity=0,
                heatmap_intensity_score=0,
                heatmap_bias="neutral",
                liquidation_pressure="low",
                liquidation_imbalance=pressure.liquidation_imbalance,
                data_quality="event_based",
                is_real_data=True,
                explanation=(
                    "Binance force-order feed is real event data, but no recent liquidation events exist for this symbol. "
                    "This is not a future liquidation heatmap."
                ),
            )
        bias = _bias_from_liquidation_direction(pressure.recent_liquidation_direction)
        intensity = _pressure_intensity(pressure.liquidation_pressure)
        return HeatmapSnapshot(
            symbol=symbol.upper(),
            provider=self.provider_name,
            provider_status="available",
            timestamp=pressure.timestamp,
            current_price=current_price,
            nearest_liquidity_above=None,
            nearest_liquidity_below=None,
            liquidity_above_intensity=intensity if bias == "upside_squeeze" else 0,
            liquidity_below_intensity=intensity if bias == "downside_sweep" else 0,
            heatmap_intensity_score=intensity,
            heatmap_bias=bias,
            liquidation_pressure=pressure.liquidation_pressure,
            liquidation_imbalance=pressure.liquidation_imbalance,
            data_quality="event_based",
            is_real_data=True,
            explanation=(
                "Binance force-order data reflects actual liquidation events after they occur, not future heatmap clusters. "
                f"Recent long liquidations: {pressure.recent_long_liquidation_notional}; "
                f"recent short liquidations: {pressure.recent_short_liquidation_notional}."
            ),
        )


class VendorHttpHeatmapProvider:
    """Provider wrapper for configured vendor HTTP heatmap snapshots."""

    def __init__(self, adapter: VendorHeatmapProvider) -> None:
        self._adapter = adapter
        self.provider_name = adapter.vendor_name

    def snapshot(self, *, symbol: str, current_price: Decimal | None) -> HeatmapSnapshot:
        return self._adapter.snapshot(symbol=symbol, current_price=current_price)


def get_heatmap_provider(settings: Settings | None = None) -> HeatmapProvider:
    """Return the configured heatmap provider, defaulting/falling back to mock."""

    resolved = settings or get_settings()
    provider = str(getattr(resolved, "heatmap_provider", "mock")).lower()
    if provider == "binance_force_orders":
        return BinanceForceOrderHeatmapProvider()
    if provider == "vendor_http":
        base_url = getattr(resolved, "heatmap_vendor_base_url", "")
        api_key = getattr(resolved, "heatmap_vendor_api_key", "")
        path = getattr(resolved, "heatmap_vendor_clusters_path", "")
        if base_url and api_key and path:
            return VendorHttpHeatmapProvider(
                VendorHeatmapProvider(
                    base_url=base_url,
                    api_key=api_key,
                    vendor_name=getattr(resolved, "heatmap_vendor_name", "vendor_http") or "vendor_http",
                    clusters_path=path,
                    symbol_param=getattr(resolved, "heatmap_vendor_symbol_param", "symbol"),
                    timeout_seconds=float(getattr(resolved, "heatmap_request_timeout_seconds", 10)),
                )
            )
        LOGGER.warning("Vendor heatmap provider requested but config is incomplete; falling back to mock.")
    elif provider != "mock":
        LOGGER.warning("Unknown HEATMAP_PROVIDER=%s; falling back to mock.", provider)
    return MockHeatmapProvider()


def get_heatmap_provider_selection(settings: Settings | None = None) -> HeatmapProviderSelection:
    """Return configured/active provider status for API diagnostics."""

    resolved = settings or get_settings()
    configured = str(getattr(resolved, "heatmap_provider", "mock")).lower()
    active = get_heatmap_provider(resolved)
    status = "available"
    explanation = "Heatmap provider is configured."
    if configured == "vendor_http" and isinstance(active, MockHeatmapProvider):
        status = "fallback"
        explanation = "Vendor heatmap configuration is incomplete or invalid; mock fallback is active."
    elif configured not in {"mock", "binance_force_orders", "vendor_http"}:
        status = "fallback"
        explanation = "Unknown heatmap provider; mock fallback is active."
    elif configured == "binance_force_orders" and get_global_liquidation_feed_service() is None:
        status = "fallback"
        explanation = "Binance force-order provider is configured, but the feed is not running."
    return HeatmapProviderSelection(
        configured_provider=configured,
        active_provider=active.provider_name,
        provider_status=status,
        explanation=explanation,
    )


def get_heatmap_snapshot(
    *,
    symbol: str,
    current_price: Decimal | None = None,
    settings: Settings | None = None,
) -> HeatmapSnapshot:
    """Return a normalized snapshot, using mock fallback if the real provider is unavailable."""

    provider = get_heatmap_provider(settings)
    try:
        snapshot = provider.snapshot(symbol=symbol, current_price=current_price)
    except Exception as exc:
        LOGGER.warning("Heatmap provider %s failed for %s: %s", provider.provider_name, symbol, exc)
        snapshot = unavailable_heatmap_snapshot(
            symbol=symbol,
            provider=provider.provider_name,
            current_price=current_price,
            explanation=f"Heatmap provider failed: {exc}",
        )
    if snapshot.provider_status == "available":
        return snapshot
    fallback = MockHeatmapProvider().snapshot(symbol=symbol, current_price=current_price)
    return HeatmapSnapshot(
        symbol=fallback.symbol,
        provider=fallback.provider,
        provider_status="fallback",
        timestamp=fallback.timestamp,
        current_price=fallback.current_price,
        nearest_liquidity_above=fallback.nearest_liquidity_above,
        nearest_liquidity_below=fallback.nearest_liquidity_below,
        liquidity_above_intensity=fallback.liquidity_above_intensity,
        liquidity_below_intensity=fallback.liquidity_below_intensity,
        heatmap_intensity_score=fallback.heatmap_intensity_score,
        heatmap_bias=fallback.heatmap_bias,
        liquidation_pressure=fallback.liquidation_pressure,
        liquidation_imbalance=fallback.liquidation_imbalance,
        data_quality=fallback.data_quality,
        is_real_data=False,
        explanation=f"{snapshot.explanation} Mock fallback is active; do not treat this as real market heatmap.",
    )


def get_liquidation_clusters(symbol: str) -> list[LiquidationCluster]:
    provider = get_heatmap_provider()
    getter = getattr(provider, "get_liquidation_clusters", None)
    return getter(symbol) if callable(getter) else []


def get_nearest_liquidity_above(symbol: str, price: Decimal) -> LiquidationCluster | None:
    provider = get_heatmap_provider()
    getter = getattr(provider, "get_nearest_liquidity_above", None)
    return getter(symbol, price) if callable(getter) else None


def get_nearest_liquidity_below(symbol: str, price: Decimal) -> LiquidationCluster | None:
    provider = get_heatmap_provider()
    getter = getattr(provider, "get_nearest_liquidity_below", None)
    return getter(symbol, price) if callable(getter) else None


def get_liquidity_intensity(symbol: str) -> int:
    snapshot = get_heatmap_snapshot(symbol=symbol)
    return snapshot.heatmap_intensity_score


def enrich_signal_with_heatmap(
    *,
    symbol: str,
    price: Decimal | None,
    base_signal_type: str,
    base_confidence: int,
    provider: HeatmapProvider | None = None,
) -> HeatmapSignalEnrichment:
    """Build a parallel heatmap-enhanced signal for validation only."""

    normalized_base = _normalize_signal_type(base_signal_type)
    if price is None or price <= Decimal("0"):
        snapshot = unavailable_heatmap_snapshot(
            symbol=symbol,
            provider="unavailable",
            current_price=price,
            explanation="Heatmap unavailable because no valid reference price exists.",
        )
    else:
        snapshot = _snapshot_from_provider(provider or get_heatmap_provider(), symbol=symbol, price=price)
    proposed = _signal_from_bias(snapshot.heatmap_bias)
    heatmap_signal = _heatmap_signal_type(
        base=normalized_base,
        proposed=proposed,
        intensity=snapshot.heatmap_intensity_score,
    )
    alignment = _alignment(base=normalized_base, heatmap=heatmap_signal)
    confidence = _heatmap_confidence(
        base_confidence=base_confidence,
        alignment=alignment,
        intensity=snapshot.heatmap_intensity_score,
    )
    return HeatmapSignalEnrichment(
        heatmap_liquidity_above=snapshot.nearest_liquidity_above,
        heatmap_liquidity_below=snapshot.nearest_liquidity_below,
        heatmap_intensity_score=snapshot.heatmap_intensity_score,
        heatmap_bias=snapshot.heatmap_bias,
        base_signal_type=normalized_base,
        heatmap_signal_type=heatmap_signal,
        base_confidence=base_confidence,
        heatmap_confidence=confidence,
        heatmap_alignment=alignment,
        heatmap_explanation=_explanation(snapshot=snapshot, alignment=alignment),
        heatmap_provider=snapshot.provider,
        heatmap_data_quality=snapshot.data_quality,
        heatmap_is_real_data=snapshot.is_real_data,
        heatmap_provider_status=snapshot.provider_status,
        liquidation_pressure=snapshot.liquidation_pressure,
        liquidation_imbalance=snapshot.liquidation_imbalance,
    )


def _signal_from_bias(bias: HeatmapBias) -> str:
    if bias == "upside_squeeze":
        return "BUY"
    if bias == "downside_sweep":
        return "SELL"
    return "WAIT"


def _snapshot_from_provider(provider: HeatmapProvider, *, symbol: str, price: Decimal) -> HeatmapSnapshot:
    snapshot_getter = getattr(provider, "snapshot", None)
    if callable(snapshot_getter):
        return snapshot_getter(symbol=symbol, current_price=price)
    above_getter = getattr(provider, "get_nearest_liquidity_above", None)
    below_getter = getattr(provider, "get_nearest_liquidity_below", None)
    intensity_getter = getattr(provider, "get_liquidity_intensity", None)
    above = above_getter(symbol, price) if callable(above_getter) else None
    below = below_getter(symbol, price) if callable(below_getter) else None
    above_intensity = above.intensity if above is not None else 0
    below_intensity = below.intensity if below is not None else 0
    intensity = max(
        above_intensity,
        below_intensity,
        intensity_getter(symbol) if callable(intensity_getter) else 0,
    )
    return HeatmapSnapshot(
        symbol=symbol.upper(),
        provider=getattr(provider, "provider_name", getattr(provider, "source", "custom")),
        provider_status="available",
        timestamp=datetime.now(tz=UTC),
        current_price=price,
        nearest_liquidity_above=above.level if above is not None else None,
        nearest_liquidity_below=below.level if below is not None else None,
        liquidity_above_intensity=above_intensity,
        liquidity_below_intensity=below_intensity,
        heatmap_intensity_score=intensity,
        heatmap_bias=_heatmap_bias_from_intensity(
            above_intensity=above_intensity,
            below_intensity=below_intensity,
        ),
        liquidation_pressure="high" if intensity >= 75 else "medium" if intensity >= 45 else "low",
        liquidation_imbalance=None,
        data_quality="mock",
        is_real_data=False,
        explanation="Compatibility heatmap provider data.",
    )


def _heatmap_signal_type(*, base: str, proposed: str, intensity: int) -> str:
    if proposed == "WAIT" or intensity < 45:
        return base
    if base in {"BUY", "SELL"} and proposed != base:
        return "WAIT"
    if intensity >= 70:
        return proposed
    return base


def _alignment(*, base: str, heatmap: str) -> HeatmapAlignment:
    if base in {"BUY", "SELL"} and heatmap == base:
        return "confirmed"
    if base in {"BUY", "SELL"} and heatmap in {"BUY", "SELL", "WAIT"} and heatmap != base:
        return "conflict"
    return "neutral"


def _heatmap_confidence(*, base_confidence: int, alignment: HeatmapAlignment, intensity: int) -> int:
    if alignment == "confirmed":
        return min(100, base_confidence + min(3, intensity // 30))
    if alignment == "conflict":
        return max(0, base_confidence - min(8, max(3, intensity // 12)))
    return base_confidence


def _normalize_signal_type(value: str) -> str:
    normalized = value.strip().upper()
    if normalized in {"LONG", "BUY"}:
        return "BUY"
    if normalized in {"SHORT", "SELL", "SELL_EXIT", "EXIT"}:
        return "SELL"
    if normalized == "AVOID":
        return "AVOID"
    return "WAIT"


def _heatmap_bias_from_intensity(*, above_intensity: int, below_intensity: int) -> HeatmapBias:
    if above_intensity >= below_intensity + 12 and above_intensity >= 60:
        return "upside_squeeze"
    if below_intensity >= above_intensity + 12 and below_intensity >= 60:
        return "downside_sweep"
    return "neutral"


def _bias_from_liquidation_direction(direction: str) -> HeatmapBias:
    if direction == "short":
        return "upside_squeeze"
    if direction == "long":
        return "downside_sweep"
    return "neutral"


def _pressure_intensity(pressure: str) -> int:
    if pressure == "high":
        return 85
    if pressure == "medium":
        return 60
    return 35


def _mock_anchor(symbol: str) -> Decimal:
    digest = int(hashlib.sha256(symbol.upper().encode("utf-8")).hexdigest()[:8], 16)
    return Decimal("80") + Decimal(digest % 8000) / Decimal("100")


def _mock_skew(symbol: str) -> int:
    digest = int(hashlib.sha256(f"{symbol.upper()}-skew".encode("utf-8")).hexdigest()[:4], 16)
    return (digest % 41) - 20


def _quantize_price(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _explanation(*, snapshot: HeatmapSnapshot, alignment: HeatmapAlignment) -> str:
    real_label = "real" if snapshot.is_real_data else snapshot.data_quality
    return (
        f"Heatmap read is {snapshot.heatmap_bias} with intensity {snapshot.heatmap_intensity_score}; "
        f"provider={snapshot.provider}, quality={snapshot.data_quality}, real_data={snapshot.is_real_data}. "
        f"Heatmap and base signal are {alignment}. {snapshot.explanation}"
        if real_label
        else snapshot.explanation
    )
