from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.market_data.candles import Candle
from app.monitoring.liquidity_bias import LiquidityBiasInput, LiquidityBiasSnapshot, estimate_liquidity_bias
from app.monitoring.liquidity_zones import estimate_liquidity_zones, validate_liquidity_zones_with_liquidations


def _candle(index: int, *, open_price: Decimal, high: Decimal, low: Decimal, close: Decimal) -> Candle:
    base_time = datetime(2024, 3, 9, 10, 0, tzinfo=UTC)
    return Candle(
        symbol="BTCUSDT",
        timeframe="15m",
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=Decimal("100"),
        quote_volume=Decimal("1000000"),
        open_time=base_time + timedelta(minutes=15 * index),
        close_time=base_time + timedelta(minutes=15 * index + 14),
        event_time=base_time + timedelta(minutes=15 * index + 14),
        trade_count=100,
        is_closed=True,
    )


def _range_candles(*, count: int = 36, compressed_tail: bool = False) -> list[Candle]:
    candles: list[Candle] = []
    for index in range(count):
        price = Decimal("100") + (Decimal(index % 4) * Decimal("0.12"))
        spread = Decimal("0.25") if compressed_tail and index >= count - 12 else Decimal("1.20")
        high = Decimal("102.00") if index % 7 in {1, 2} else price + spread
        low = Decimal("98.00") if index % 9 in {3, 4} else price - spread
        candles.append(_candle(index, open_price=price, high=high, low=low, close=price))
    return candles


def test_detects_upside_liquidity_zone_from_recent_equal_highs() -> None:
    zones = estimate_liquidity_zones(symbol="BTCUSDT", candles=_range_candles(), current_price=Decimal("100"))

    assert zones.upside_liquidity_zone.level == Decimal("102.0000")
    assert zones.upside_liquidity_zone.strength in {"medium", "high"}
    assert "equal highs" in zones.upside_liquidity_zone.reason


def test_detects_downside_liquidity_zone_from_recent_equal_lows() -> None:
    zones = estimate_liquidity_zones(symbol="BTCUSDT", candles=_range_candles(), current_price=Decimal("100"))

    assert zones.downside_liquidity_zone.level == Decimal("98.0000")
    assert zones.downside_liquidity_zone.strength in {"medium", "high"}
    assert "equal lows" in zones.downside_liquidity_zone.reason


def test_selects_nearest_liquidity_target() -> None:
    zones = estimate_liquidity_zones(symbol="BTCUSDT", candles=_range_candles(), current_price=Decimal("101.40"))

    assert zones.nearest_liquidity_target.direction == "up"
    assert zones.nearest_liquidity_target.level == Decimal("102.0000")


def test_long_stop_too_close_to_downside_liquidity() -> None:
    zones = estimate_liquidity_zones(
        symbol="BTCUSDT",
        candles=_range_candles(),
        current_price=Decimal("100"),
        trade_direction="long",
        stop_loss=Decimal("98.15"),
        take_profit=Decimal("102.20"),
    )

    assert zones.tp_sl_alignment == "stop_too_close_to_liquidity"


def test_short_stop_too_close_to_upside_liquidity() -> None:
    zones = estimate_liquidity_zones(
        symbol="BTCUSDT",
        candles=_range_candles(),
        current_price=Decimal("100"),
        trade_direction="short",
        stop_loss=Decimal("101.90"),
        take_profit=Decimal("97.80"),
    )

    assert zones.tp_sl_alignment == "stop_too_close_to_liquidity"


def test_long_waits_for_sweep_when_downside_risk_opposes_entry() -> None:
    bias = LiquidityBiasSnapshot(
        liquidity_bias="bearish",
        liquidity_pressure="high",
        likely_liquidation_direction="down",
        trap_risk="long_trap",
        explanation="Estimated crowded long positioning.",
    )
    zones = estimate_liquidity_zones(
        symbol="BTCUSDT",
        candles=_range_candles(),
        current_price=Decimal("98.45"),
        trade_direction="long",
        stop_loss=Decimal("97.40"),
        take_profit=Decimal("102.20"),
        liquidity_bias=bias,
    )

    assert zones.sweep_risk == "downside_sweep"
    assert zones.trade_timing_adjustment == "wait_for_sweep"


def test_liquidation_sweep_confirmation_validates_nearest_zone() -> None:
    bias = LiquidityBiasSnapshot(
        liquidity_bias="bearish",
        liquidity_pressure="high",
        likely_liquidation_direction="down",
        trap_risk="long_trap",
        explanation="Estimated crowded long positioning.",
    )
    zones = estimate_liquidity_zones(
        symbol="BTCUSDT",
        candles=_range_candles(),
        current_price=Decimal("98.45"),
        trade_direction="long",
        stop_loss=Decimal("97.40"),
        take_profit=Decimal("102.20"),
        liquidity_bias=bias,
    )

    validated = validate_liquidity_zones_with_liquidations(
        zones=zones,
        liquidation_signal="sweep_confirmation",
        dominant_side="longs_liquidated",
    )

    assert validated.downside_liquidity_zone.strength == "high"
    assert validated.nearest_liquidity_target.direction == "down"
    assert validated.nearest_liquidity_target.strength == "high"
    assert validated.trade_timing_adjustment == "wait_for_confirmation"
    assert "liquidation events" in validated.explanation


def test_short_waits_for_sweep_when_upside_risk_opposes_entry() -> None:
    bias = LiquidityBiasSnapshot(
        liquidity_bias="bullish",
        liquidity_pressure="high",
        likely_liquidation_direction="up",
        trap_risk="short_trap",
        explanation="Estimated crowded short positioning.",
    )
    zones = estimate_liquidity_zones(
        symbol="BTCUSDT",
        candles=_range_candles(),
        current_price=Decimal("101.55"),
        trade_direction="short",
        stop_loss=Decimal("102.80"),
        take_profit=Decimal("98.00"),
        liquidity_bias=bias,
    )

    assert zones.sweep_risk == "upside_sweep"
    assert zones.trade_timing_adjustment == "wait_for_sweep"


def test_choppy_both_side_liquidity_returns_avoid_chop() -> None:
    zones = estimate_liquidity_zones(
        symbol="BTCUSDT",
        candles=_range_candles(compressed_tail=True),
        current_price=Decimal("100"),
        trade_direction="long",
        stop_loss=Decimal("97"),
        take_profit=Decimal("103"),
        regime_label="choppy",
    )

    assert zones.sweep_risk == "both_sides"
    assert zones.trade_timing_adjustment == "avoid_chop"


def test_missing_candle_data_returns_safe_neutral_fallback() -> None:
    zones = estimate_liquidity_zones(symbol="BTCUSDT", candles=[], current_price=Decimal("100"))

    assert zones.nearest_liquidity_target.direction == "none"
    assert zones.sweep_risk == "none"
    assert zones.tp_sl_alignment == "needs_review"


def test_existing_liquidity_bias_behavior_still_detects_long_trap() -> None:
    snapshot = estimate_liquidity_bias(
        LiquidityBiasInput(
            symbol="BTCUSDT",
            candles=_range_candles(compressed_tail=True),
            funding_rate=Decimal("0.015"),
            open_interest_change_pct=Decimal("4.0"),
        )
    )

    assert snapshot.trap_risk == "long_trap"
    assert snapshot.likely_liquidation_direction == "down"
