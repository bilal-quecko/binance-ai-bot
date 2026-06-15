"""Normalized heatmap/liquidation data models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

HeatmapBias = Literal["upside_squeeze", "downside_sweep", "neutral"]
ClusterSide = Literal["above", "below"]
HeatmapAlignment = Literal["confirmed", "conflict", "neutral"]
HeatmapProviderMode = Literal["mock", "binance_force_orders", "vendor_http"]
HeatmapProviderStatus = Literal["available", "unavailable", "fallback"]
HeatmapDataQuality = Literal["mock", "estimated", "event_based", "vendor_heatmap", "unavailable"]
LiquidationPressure = Literal["low", "medium", "high"]


@dataclass(slots=True, frozen=True)
class LiquidationCluster:
    """One liquidation-liquidity cluster from a heatmap provider."""

    symbol: str
    level: Decimal
    side: ClusterSide
    intensity: int
    source: str


@dataclass(slots=True, frozen=True)
class HeatmapSnapshot:
    """Normalized heatmap snapshot shared by mock, event-based, and vendor providers."""

    symbol: str
    provider: str
    provider_status: HeatmapProviderStatus
    timestamp: datetime
    current_price: Decimal | None
    nearest_liquidity_above: Decimal | None
    nearest_liquidity_below: Decimal | None
    liquidity_above_intensity: int
    liquidity_below_intensity: int
    heatmap_intensity_score: int
    heatmap_bias: HeatmapBias
    liquidation_pressure: LiquidationPressure
    liquidation_imbalance: Decimal | None
    data_quality: HeatmapDataQuality
    is_real_data: bool
    explanation: str


@dataclass(slots=True, frozen=True)
class HeatmapSignalEnrichment:
    """Parallel heatmap signal read used for validation, not execution."""

    heatmap_liquidity_above: Decimal | None
    heatmap_liquidity_below: Decimal | None
    heatmap_intensity_score: int
    heatmap_bias: HeatmapBias
    base_signal_type: str
    heatmap_signal_type: str
    base_confidence: int
    heatmap_confidence: int
    heatmap_alignment: HeatmapAlignment
    heatmap_explanation: str
    heatmap_provider: str = "mock"
    heatmap_data_quality: HeatmapDataQuality = "mock"
    heatmap_is_real_data: bool = False
    heatmap_provider_status: HeatmapProviderStatus = "available"
    liquidation_pressure: LiquidationPressure = "low"
    liquidation_imbalance: Decimal | None = None


def unavailable_heatmap_snapshot(
    *,
    symbol: str,
    provider: str,
    current_price: Decimal | None,
    explanation: str,
) -> HeatmapSnapshot:
    """Build a safe unavailable snapshot."""

    return HeatmapSnapshot(
        symbol=symbol.upper(),
        provider=provider,
        provider_status="unavailable",
        timestamp=datetime.now(tz=UTC),
        current_price=current_price,
        nearest_liquidity_above=None,
        nearest_liquidity_below=None,
        liquidity_above_intensity=0,
        liquidity_below_intensity=0,
        heatmap_intensity_score=0,
        heatmap_bias="neutral",
        liquidation_pressure="low",
        liquidation_imbalance=None,
        data_quality="unavailable",
        is_real_data=False,
        explanation=explanation,
    )
