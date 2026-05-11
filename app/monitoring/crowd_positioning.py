"""Crowd positioning from funding and open-interest context."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.data.binance_derivatives_data import BinanceDerivativesSnapshot

CrowdSide = Literal["long_crowded", "short_crowded", "balanced"]
CrowdStrength = Literal["low", "medium", "high"]
PositioningConfidence = Literal["low", "medium", "high"]
SqueezeRisk = Literal["long_squeeze", "short_squeeze", "low"]


@dataclass(slots=True, frozen=True)
class CrowdPositioningSnapshot:
    """Crowd-positioning read used by liquidity decision layers."""

    crowd_side: CrowdSide
    crowd_strength: CrowdStrength
    positioning_confidence: PositioningConfidence
    squeeze_risk: SqueezeRisk
    explanation: str
    funding_rate: Decimal | None = None
    open_interest: Decimal | None = None
    oi_trend: str = "neutral"
    data_quality: str = "fallback"


NEUTRAL_CROWD_POSITIONING = CrowdPositioningSnapshot(
    crowd_side="balanced",
    crowd_strength="low",
    positioning_confidence="low",
    squeeze_risk="low",
    explanation="Crowd positioning is balanced or unavailable; funding/OI fallback is neutral.",
)


def estimate_crowd_positioning(
    *,
    funding_rate: Decimal | None,
    oi_trend: str | None,
    open_interest: Decimal | None = None,
    oi_change_1h: Decimal | None = None,
    oi_change_24h: Decimal | None = None,
    price_trend: str | None = None,
    volume_trend: str | None = None,
    data_quality: str = "fallback",
) -> CrowdPositioningSnapshot:
    """Estimate which side of leveraged positioning is crowded."""

    del price_trend, volume_trend
    trend = oi_trend or "neutral"
    if funding_rate is None:
        return NEUTRAL_CROWD_POSITIONING
    if abs(funding_rate) < Decimal("0.00005"):
        return CrowdPositioningSnapshot(
            crowd_side="balanced",
            crowd_strength="low",
            positioning_confidence="medium" if data_quality == "real" else "low",
            squeeze_risk="low",
            funding_rate=funding_rate,
            open_interest=open_interest,
            oi_trend=trend,
            data_quality=data_quality,
            explanation="Funding is near zero, so crowd positioning is treated as balanced.",
        )
    if trend == "falling":
        return CrowdPositioningSnapshot(
            crowd_side="balanced",
            crowd_strength="low",
            positioning_confidence="low",
            squeeze_risk="low",
            funding_rate=funding_rate,
            open_interest=open_interest,
            oi_trend=trend,
            data_quality=data_quality,
            explanation="Open interest is falling, so crowded positioning pressure is weak.",
        )
    if trend != "rising":
        return CrowdPositioningSnapshot(
            crowd_side="balanced",
            crowd_strength="low",
            positioning_confidence="low" if data_quality != "real" else "medium",
            squeeze_risk="low",
            funding_rate=funding_rate,
            open_interest=open_interest,
            oi_trend=trend,
            data_quality=data_quality,
            explanation="Open interest is not rising, so funding does not confirm crowd buildup.",
        )
    strength = _crowd_strength(funding_rate=funding_rate, oi_change_1h=oi_change_1h, oi_change_24h=oi_change_24h)
    confidence: PositioningConfidence = "high" if data_quality == "real" and strength == "high" else "medium"
    if funding_rate > Decimal("0"):
        return CrowdPositioningSnapshot(
            crowd_side="long_crowded",
            crowd_strength=strength,
            positioning_confidence=confidence,
            squeeze_risk="long_squeeze",
            funding_rate=funding_rate,
            open_interest=open_interest,
            oi_trend=trend,
            data_quality=data_quality,
            explanation="Positive funding with rising open interest suggests crowded longs and downside squeeze risk.",
        )
    return CrowdPositioningSnapshot(
        crowd_side="short_crowded",
        crowd_strength=strength,
        positioning_confidence=confidence,
        squeeze_risk="short_squeeze",
        funding_rate=funding_rate,
        open_interest=open_interest,
        oi_trend=trend,
        data_quality=data_quality,
        explanation="Negative funding with rising open interest suggests crowded shorts and upside squeeze risk.",
    )


def crowd_positioning_from_derivatives(snapshot: BinanceDerivativesSnapshot) -> CrowdPositioningSnapshot:
    """Build crowd positioning from a normalized Binance derivatives snapshot."""

    return estimate_crowd_positioning(
        funding_rate=snapshot.funding_rate,
        oi_trend=snapshot.oi_trend,
        open_interest=snapshot.open_interest,
        oi_change_1h=snapshot.oi_change_1h,
        oi_change_24h=snapshot.oi_change_24h,
        data_quality=snapshot.data_quality,
    )


def _crowd_strength(
    *,
    funding_rate: Decimal,
    oi_change_1h: Decimal | None,
    oi_change_24h: Decimal | None,
) -> CrowdStrength:
    abs_funding = abs(funding_rate)
    oi_change = abs(oi_change_1h if oi_change_1h is not None else oi_change_24h or Decimal("0"))
    if abs_funding >= Decimal("0.0005") or oi_change >= Decimal("5"):
        return "high"
    if abs_funding >= Decimal("0.00015") or oi_change >= Decimal("1.5"):
        return "medium"
    return "low"
