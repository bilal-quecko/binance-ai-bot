from decimal import Decimal

from app.risk.limits import RiskEngine, check_daily_loss
from app.risk.models import RiskInput
from app.strategies.models import StrategySignal


BASE_SIGNAL = StrategySignal(
    symbol="BTCUSDT",
    side="BUY",
    confidence=Decimal("0.60"),
    reason_codes=("EMA_BULLISH",),
)


def build_risk_input(**overrides: object) -> RiskInput:
    payload: dict[str, object] = {
        "signal": BASE_SIGNAL,
        "entry_price": Decimal("100"),
        "requested_quantity": Decimal("5"),
        "equity": Decimal("10000"),
        "day_start_equity": Decimal("10000"),
        "daily_pnl": Decimal("0"),
        "open_positions": 1,
        "stop_price": Decimal("98"),
        "volatility": Decimal("1.5"),
        "risk_per_trade": Decimal("0.01"),
        "max_daily_loss": Decimal("0.02"),
        "max_open_positions": 3,
        "min_stop_distance_ratio": Decimal("0.005"),
        "quantity_step": Decimal("0.00000001"),
        "mode": "paper",
    }
    payload.update(overrides)
    return RiskInput(**payload)


def test_check_daily_loss_limit_blocks() -> None:
    decision = check_daily_loss(current_drawdown=Decimal("0.03"), max_daily_loss=Decimal("0.02"))

    assert decision.approved is False
    assert decision.reason == "daily_loss_limit_reached"


def test_risk_engine_approves_trade_when_limits_pass() -> None:
    engine = RiskEngine()

    decision = engine.evaluate(build_risk_input())

    assert decision.decision == "approve"
    assert decision.approved_quantity == Decimal("5")
    assert decision.reason_codes == ("APPROVED",)


def test_risk_engine_rejects_trade_on_daily_loss_limit() -> None:
    engine = RiskEngine()

    decision = engine.evaluate(build_risk_input(daily_pnl=Decimal("-250")))

    assert decision.decision == "reject"
    assert decision.approved_quantity == Decimal("0")
    assert decision.reason_codes == ("DAILY_LOSS_LIMIT",)


def test_risk_engine_rejects_trade_on_open_position_limit() -> None:
    engine = RiskEngine()

    decision = engine.evaluate(build_risk_input(open_positions=3))

    assert decision.decision == "reject"
    assert decision.reason_codes == ("OPEN_POSITION_LIMIT",)


def test_risk_engine_resizes_trade_when_requested_size_exceeds_risk_budget() -> None:
    engine = RiskEngine()

    decision = engine.evaluate(build_risk_input(requested_quantity=Decimal("100")))

    assert decision.decision == "resize"
    assert decision.approved_quantity == Decimal("50.00000000")
    assert decision.reason_codes == ("RESIZED_FOR_RISK",)
