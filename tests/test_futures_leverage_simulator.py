from decimal import Decimal

from app.monitoring.futures_leverage_simulator import simulate_futures_leverage


def test_long_leverage_simulation_math() -> None:
    simulation = simulate_futures_leverage(
        direction="long",
        entry_price=Decimal("100"),
        take_profit=Decimal("110"),
        stop_loss=Decimal("98"),
        live_price=Decimal("103"),
        leverage=5,
        fee_slippage_pct=Decimal("0.10"),
    )

    assert simulation.selected_leverage == 5
    assert simulation.estimated_tp_return_percent == Decimal("50.0000")
    assert simulation.estimated_sl_return_percent == Decimal("-10.0000")
    assert simulation.estimated_current_unrealized_return_percent == Decimal("15.0000")
    assert simulation.fee_adjusted_tp_return_percent == Decimal("49.5000")
    assert simulation.fee_adjusted_sl_return_percent == Decimal("-10.5000")
    assert simulation.liquidation_risk_label == "medium"


def test_short_leverage_simulation_math() -> None:
    simulation = simulate_futures_leverage(
        direction="short",
        entry_price=Decimal("100"),
        take_profit=Decimal("90"),
        stop_loss=Decimal("103"),
        live_price=Decimal("97"),
        leverage=10,
        fee_slippage_pct=Decimal("0.12"),
    )

    assert simulation.estimated_tp_return_percent == Decimal("100.0000")
    assert simulation.estimated_sl_return_percent == Decimal("-30.0000")
    assert simulation.estimated_current_unrealized_return_percent == Decimal("30.0000")
    assert simulation.fee_adjusted_tp_return_percent == Decimal("98.8000")
    assert simulation.fee_adjusted_sl_return_percent == Decimal("-31.2000")
    assert simulation.liquidation_risk_label == "high"


def test_high_and_extreme_leverage_risk_labeling() -> None:
    high = simulate_futures_leverage(
        direction="long",
        entry_price=Decimal("100"),
        take_profit=Decimal("102"),
        stop_loss=Decimal("99"),
        live_price=Decimal("101"),
        leverage=25,
    )
    extreme = simulate_futures_leverage(
        direction="long",
        entry_price=Decimal("100"),
        take_profit=Decimal("102"),
        stop_loss=Decimal("99"),
        live_price=Decimal("101"),
        leverage=100,
    )

    assert high.liquidation_risk_label == "high"
    assert high.leverage_warning is not None
    assert extreme.liquidation_risk_label == "extreme"
    assert extreme.leverage_warning == "Extreme paper leverage. Small adverse moves can wipe out simulated margin."


def test_leverage_does_not_touch_scanner_scores_or_ranking_inputs() -> None:
    low = simulate_futures_leverage(
        direction="long",
        entry_price=Decimal("100"),
        take_profit=Decimal("102"),
        stop_loss=Decimal("99"),
        live_price=Decimal("101"),
        leverage=1,
    )
    high = simulate_futures_leverage(
        direction="long",
        entry_price=Decimal("100"),
        take_profit=Decimal("102"),
        stop_loss=Decimal("99"),
        live_price=Decimal("101"),
        leverage=100,
    )

    assert low.selected_leverage == 1
    assert high.selected_leverage == 100
    assert not hasattr(low, "opportunity_score")
    assert not hasattr(high, "opportunity_score")
