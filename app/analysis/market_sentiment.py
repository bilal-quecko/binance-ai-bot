"""Broader-market sentiment analysis for one selected symbol."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from app.analysis.market_breadth import (
    BreadthState,
    BreadthSummary,
    RelativeStrengthState,
    classify_market_breadth,
    classify_relative_strength,
    realized_volatility_pct,
    recent_return_pct,
)
from app.data import MarketContextPoint


AnalysisState = Literal["ready", "incomplete"]
MarketState = Literal["risk_on", "risk_off", "mixed", "insufficient_data"]
AssetBias = Literal["bullish", "bearish", "neutral"]
VolatilityEnvironment = Literal["calm", "normal", "stressed", "insufficient_data"]


@dataclass(slots=True)
class MarketSentimentSnapshot:
    """Typed broader-market sentiment payload for one selected symbol."""

    symbol: str
    generated_at: datetime
    data_state: AnalysisState
    status_message: str | None
    market_state: MarketState
    sentiment_score: int | None
    btc_bias: AssetBias | None
    eth_bias: AssetBias | None
    selected_symbol_relative_strength: RelativeStrengthState
    relative_strength_pct: Decimal | None
    market_breadth_state: BreadthState
    breadth_advancing_symbols: int
    breadth_declining_symbols: int
    breadth_sample_size: int
    volatility_environment: VolatilityEnvironment
    explanation: str | None


class MarketSentimentService:
    """Build a deterministic broader-market sentiment view."""

    def analyze(
        self,
        *,
        symbol: str,
        symbol_points: Mapping[str, Sequence[MarketContextPoint]],
    ) -> MarketSentimentSnapshot:
        """Return a market-sentiment snapshot for one selected symbol."""

        normalized_symbol = symbol.strip().upper()
        selected_points = symbol_points.get(normalized_symbol, ())
        btc_points = symbol_points.get("BTCUSDT", ())
        eth_points = symbol_points.get("ETHUSDT", ())

        btc_bias = _classify_asset_bias(btc_points)
        eth_bias = _classify_asset_bias(eth_points)
        breadth = classify_market_breadth(symbol_points)
        relative_strength, relative_strength_pct = classify_relative_strength(
            selected_points,
            btc_points,
        )
        volatility_environment = _classify_volatility_environment(btc_points)

        if btc_bias is None:
            return MarketSentimentSnapshot(
                symbol=normalized_symbol,
                generated_at=datetime.now(tz=UTC),
                data_state="incomplete",
                status_message=(
                    f"Market sentiment for {normalized_symbol} needs more BTC market history before a broader risk-on or risk-off read is reliable."
                ),
                market_state="insufficient_data",
                sentiment_score=None,
                btc_bias=None,
                eth_bias=eth_bias,
                selected_symbol_relative_strength=relative_strength,
                relative_strength_pct=relative_strength_pct,
                market_breadth_state=breadth.state,
                breadth_advancing_symbols=breadth.advancing_symbols,
                breadth_declining_symbols=breadth.declining_symbols,
                breadth_sample_size=breadth.sample_size,
                volatility_environment=volatility_environment,
                explanation=None,
            )

        sentiment_score = _score_sentiment(
            btc_bias=btc_bias,
            eth_bias=eth_bias,
            breadth=breadth,
            relative_strength=relative_strength,
            volatility_environment=volatility_environment,
        )
        market_state = _classify_market_state(sentiment_score)
        explanation = _build_explanation(
            symbol=normalized_symbol,
            market_state=market_state,
            btc_bias=btc_bias,
            eth_bias=eth_bias,
            breadth=breadth,
            relative_strength=relative_strength,
            relative_strength_pct=relative_strength_pct,
            volatility_environment=volatility_environment,
        )

        return MarketSentimentSnapshot(
            symbol=normalized_symbol,
            generated_at=datetime.now(tz=UTC),
            data_state="ready",
            status_message=f"Broader market sentiment is ready for {normalized_symbol}.",
            market_state=market_state,
            sentiment_score=sentiment_score,
            btc_bias=btc_bias,
            eth_bias=eth_bias,
            selected_symbol_relative_strength=relative_strength,
            relative_strength_pct=relative_strength_pct,
            market_breadth_state=breadth.state,
            breadth_advancing_symbols=breadth.advancing_symbols,
            breadth_declining_symbols=breadth.declining_symbols,
            breadth_sample_size=breadth.sample_size,
            volatility_environment=volatility_environment,
            explanation=explanation,
        )


def _classify_asset_bias(points: Sequence[MarketContextPoint]) -> AssetBias | None:
    """Classify one asset's recent trend and momentum bias."""

    short_return = recent_return_pct(points, lookback_points=20)
    medium_return = recent_return_pct(points, lookback_points=60)
    if short_return is None:
        return None
    medium = medium_return if medium_return is not None else short_return
    if short_return >= Decimal("0.008") and medium >= Decimal("0"):
        return "bullish"
    if short_return <= Decimal("-0.008") and medium <= Decimal("0"):
        return "bearish"
    return "neutral"


def _classify_volatility_environment(
    btc_points: Sequence[MarketContextPoint],
) -> VolatilityEnvironment:
    """Classify BTC's recent volatility regime as a market proxy."""

    volatility_pct = realized_volatility_pct(btc_points, lookback_points=30)
    if volatility_pct is None:
        return "insufficient_data"
    if volatility_pct < Decimal("0.35"):
        return "calm"
    if volatility_pct < Decimal("0.90"):
        return "normal"
    return "stressed"


def _score_sentiment(
    *,
    btc_bias: AssetBias,
    eth_bias: AssetBias | None,
    breadth: BreadthSummary,
    relative_strength: RelativeStrengthState,
    volatility_environment: VolatilityEnvironment,
) -> int:
    """Return a bounded market-sentiment score from 0 to 100."""

    score = 50
    score += _bias_score(btc_bias, bullish=18, bearish=-18)
    if eth_bias is not None:
        score += _bias_score(eth_bias, bullish=12, bearish=-12)
    if breadth.state == "positive":
        score += 10
    elif breadth.state == "negative":
        score -= 10
    if relative_strength == "outperforming_btc":
        score += 8
    elif relative_strength == "underperforming_btc":
        score -= 8
    if volatility_environment == "calm":
        score += 7
    elif volatility_environment == "stressed":
        score -= 12
    return max(0, min(100, score))


def _bias_score(
    bias: AssetBias,
    *,
    bullish: int,
    bearish: int,
) -> int:
    """Map one bias label into a signed score adjustment."""

    if bias == "bullish":
        return bullish
    if bias == "bearish":
        return bearish
    return 0


def _classify_market_state(score: int) -> MarketState:
    """Map a market-sentiment score into a readable state."""

    if score >= 65:
        return "risk_on"
    if score <= 35:
        return "risk_off"
    return "mixed"


def _build_explanation(
    *,
    symbol: str,
    market_state: MarketState,
    btc_bias: AssetBias,
    eth_bias: AssetBias | None,
    breadth: BreadthSummary,
    relative_strength: RelativeStrengthState,
    relative_strength_pct: Decimal | None,
    volatility_environment: VolatilityEnvironment,
) -> str:
    """Build a concise human-readable market-sentiment summary."""

    parts = [
        f"The broader crypto backdrop reads {market_state.replace('_', ' ')}.",
        f"BTC is {btc_bias}.",
    ]
    if eth_bias is not None:
        parts.append(f"ETH is {eth_bias}.")
    if breadth.state != "insufficient_data":
        parts.append(
            f"Market breadth is {breadth.state} with {breadth.advancing_symbols} advancing and {breadth.declining_symbols} declining tracked symbols."
        )
    else:
        parts.append("Tracked market breadth is still limited.")
    if relative_strength == "insufficient_data":
        parts.append(f"Relative strength for {symbol} versus BTC still needs more history.")
    elif relative_strength_pct is not None:
        parts.append(
            f"{symbol} is {relative_strength.replace('_', ' ')} by about {relative_strength_pct.quantize(Decimal('0.01'))}% versus BTC."
        )
    else:
        parts.append(f"{symbol} is {relative_strength.replace('_', ' ')} versus BTC.")
    if volatility_environment != "insufficient_data":
        parts.append(f"BTC volatility is {volatility_environment}.")
    else:
        parts.append("BTC volatility still needs more data.")
    return " ".join(parts)
