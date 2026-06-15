from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.market_data.candles import Candle
from app.monitoring.liquidity_bias import LiquidityBiasInput, estimate_liquidity_bias


def _candles(*, step: Decimal = Decimal("0.1"), count: int = 36, compressed_tail: bool = False) -> list[Candle]:
    base_time = datetime(2024, 3, 9, 10, 0, tzinfo=UTC)
    price = Decimal("100")
    candles: list[Candle] = []
    for index in range(count):
        price += step
        spread = Decimal("0.15") if compressed_tail and index >= count - 12 else Decimal("1.00")
        candles.append(
            Candle(
                symbol="BTCUSDT",
                timeframe="15m",
                open=price - (step / Decimal("2")),
                high=price + spread,
                low=price - spread,
                close=price,
                volume=Decimal("100"),
                quote_volume=Decimal("1000000"),
                open_time=base_time + timedelta(minutes=15 * index),
                close_time=base_time + timedelta(minutes=15 * index + 14),
                event_time=base_time + timedelta(minutes=15 * index + 14),
                trade_count=100,
                is_closed=True,
            )
        )
    return candles


def test_positive_funding_and_rising_oi_detects_long_trap() -> None:
    snapshot = estimate_liquidity_bias(
        LiquidityBiasInput(
            symbol="BTCUSDT",
            candles=_candles(),
            funding_rate=Decimal("0.015"),
            open_interest_change_pct=Decimal("4.2"),
        )
    )

    assert snapshot.liquidity_bias == "bearish"
    assert snapshot.trap_risk == "long_trap"
    assert snapshot.likely_liquidation_direction == "down"


def test_negative_funding_and_rising_oi_detects_short_trap() -> None:
    snapshot = estimate_liquidity_bias(
        LiquidityBiasInput(
            symbol="BTCUSDT",
            candles=_candles(),
            funding_rate=Decimal("-0.012"),
            open_interest_change_pct=Decimal("4.2"),
        )
    )

    assert snapshot.liquidity_bias == "bullish"
    assert snapshot.trap_risk == "short_trap"
    assert snapshot.likely_liquidation_direction == "up"


def test_neutral_conditions_return_low_pressure() -> None:
    snapshot = estimate_liquidity_bias(
        LiquidityBiasInput(
            symbol="BTCUSDT",
            candles=_candles(step=Decimal("0.01")),
            funding_rate=Decimal("0"),
            open_interest_change_pct=Decimal("-1"),
        )
    )

    assert snapshot.liquidity_bias == "neutral"
    assert snapshot.liquidity_pressure == "low"
    assert snapshot.trap_risk == "low"


def test_structure_fallback_when_funding_and_oi_are_missing() -> None:
    snapshot = estimate_liquidity_bias(
        LiquidityBiasInput(
            symbol="BTCUSDT",
            candles=_candles(step=Decimal("0.35"), compressed_tail=True),
            volatility_regime="low",
        )
    )

    assert snapshot.liquidity_bias == "bearish"
    assert snapshot.liquidity_pressure == "high"
    assert snapshot.trap_risk == "long_trap"
