from decimal import Decimal

from app.monitoring.crowd_positioning import estimate_crowd_positioning
from app.monitoring.liquidity_bias import LiquidityBiasInput, estimate_liquidity_bias
from app.api.bot_api import BackfillStatusResponse, FusionSignalResponse, _build_trading_assistant_response


def test_positive_funding_and_rising_oi_is_long_crowded() -> None:
    crowd = estimate_crowd_positioning(
        funding_rate=Decimal("0.0003"),
        oi_trend="rising",
        oi_change_1h=Decimal("2.0"),
        data_quality="real",
    )

    assert crowd.crowd_side == "long_crowded"
    assert crowd.squeeze_risk == "long_squeeze"
    assert crowd.crowd_strength == "medium"


def test_negative_funding_and_rising_oi_is_short_crowded() -> None:
    crowd = estimate_crowd_positioning(
        funding_rate=Decimal("-0.0004"),
        oi_trend="rising",
        oi_change_1h=Decimal("2.0"),
        data_quality="real",
    )

    assert crowd.crowd_side == "short_crowded"
    assert crowd.squeeze_risk == "short_squeeze"


def test_falling_oi_returns_weak_positioning() -> None:
    crowd = estimate_crowd_positioning(
        funding_rate=Decimal("0.0005"),
        oi_trend="falling",
        oi_change_1h=Decimal("-1.0"),
        data_quality="real",
    )

    assert crowd.crowd_side == "balanced"
    assert crowd.crowd_strength == "low"
    assert crowd.positioning_confidence == "low"


def test_crowd_positioning_enhances_existing_liquidity_bias() -> None:
    crowd = estimate_crowd_positioning(
        funding_rate=Decimal("0.0006"),
        oi_trend="rising",
        oi_change_1h=Decimal("6.0"),
        data_quality="real",
    )

    bias = estimate_liquidity_bias(
        LiquidityBiasInput(
            symbol="BTCUSDT",
            candles=(),
            crowd_positioning=crowd,
        )
    )

    assert bias.liquidity_bias == "bearish"
    assert bias.trap_risk == "long_trap"
    assert bias.likely_liquidation_direction == "down"


def test_trading_assistant_downgrades_buy_when_longs_are_crowded() -> None:
    crowd = estimate_crowd_positioning(
        funding_rate=Decimal("0.0006"),
        oi_trend="rising",
        oi_change_1h=Decimal("6.0"),
        data_quality="real",
    )

    assistant = _build_trading_assistant_response(
        symbol="BTCUSDT",
        backfill_status=BackfillStatusResponse(
            symbol="BTCUSDT",
            requested_interval="1m",
            requested_lookback_days=7,
            candle_count=100,
            coverage_pct=Decimal("100"),
            status="ready",
            message="ready",
        ),
        fusion_signal=FusionSignalResponse(
            symbol="BTCUSDT",
            data_state="ready",
            final_signal="long",
            confidence=75,
            risk_grade="medium",
            top_reasons=["Bullish setup."],
        ),
        technical_analysis=None,
        workstation=None,
        crowd_positioning=crowd,
    )

    assert assistant.decision == "wait"
    assert assistant.crowd_side == "long_crowded"
    assert assistant.squeeze_risk == "long_squeeze"
