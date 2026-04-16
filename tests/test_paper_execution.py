from datetime import UTC, datetime
from decimal import Decimal

from app.execution.execution_engine import ExecutionEngine
from app.paper.broker import PaperBroker
from app.paper.models import OrderRequest
from app.risk.models import RiskDecision


NOW = datetime(2024, 3, 9, 16, 0, 0, tzinfo=UTC)


def build_order(*, side: str, quantity: str, market_price: str) -> OrderRequest:
    return OrderRequest(
        symbol="BTCUSDT",
        side=side,  # type: ignore[arg-type]
        quantity=Decimal(quantity),
        market_price=Decimal(market_price),
        timestamp=NOW,
    )


def test_execution_engine_executes_successful_buy() -> None:
    broker = PaperBroker(initial_balances={"USDT": Decimal("1000")}, fee_rate=Decimal("0.001"))
    engine = ExecutionEngine(broker)
    order = build_order(side="BUY", quantity="1", market_price="100")
    risk_decision = RiskDecision(decision="approve", approved_quantity=Decimal("1"), reason_codes=("APPROVED",))

    fill = engine.execute(order, risk_decision)

    assert fill.status == "executed"
    assert fill.filled_quantity == Decimal("1")
    assert fill.fill_price == Decimal("100")
    assert fill.fee_paid == Decimal("0.100")
    assert broker.get_balance("USDT") == Decimal("899.900")
    position = broker.get_position("BTCUSDT")
    assert position is not None
    assert position.quantity == Decimal("1")
    assert position.avg_entry_price == Decimal("100.100")


def test_execution_engine_executes_successful_sell_and_updates_pnl() -> None:
    broker = PaperBroker(initial_balances={"USDT": Decimal("1000")}, fee_rate=Decimal("0.001"))
    engine = ExecutionEngine(broker)

    buy_fill = engine.execute(
        build_order(side="BUY", quantity="1", market_price="100"),
        RiskDecision(decision="approve", approved_quantity=Decimal("1"), reason_codes=("APPROVED",)),
    )
    sell_fill = engine.execute(
        build_order(side="SELL", quantity="1", market_price="110"),
        RiskDecision(decision="approve", approved_quantity=Decimal("1"), reason_codes=("APPROVED",)),
    )

    assert buy_fill.status == "executed"
    assert sell_fill.status == "executed"
    assert sell_fill.realized_pnl == Decimal("9.790")
    assert broker.realized_pnl == Decimal("9.790")
    assert broker.get_balance("USDT") == Decimal("1009.790")
    assert broker.get_position("BTCUSDT") is None


def test_paper_broker_tracks_position_increase_and_reduce() -> None:
    broker = PaperBroker(initial_balances={"USDT": Decimal("2000")}, fee_rate=Decimal("0.001"))
    engine = ExecutionEngine(broker)

    engine.execute(
        build_order(side="BUY", quantity="1", market_price="100"),
        RiskDecision(decision="approve", approved_quantity=Decimal("1"), reason_codes=("APPROVED",)),
    )
    engine.execute(
        build_order(side="BUY", quantity="2", market_price="120"),
        RiskDecision(decision="approve", approved_quantity=Decimal("2"), reason_codes=("APPROVED",)),
    )
    reduce_fill = engine.execute(
        build_order(side="SELL", quantity="1.5", market_price="130"),
        RiskDecision(decision="approve", approved_quantity=Decimal("1.5"), reason_codes=("APPROVED",)),
    )

    position = broker.get_position("BTCUSDT")

    assert reduce_fill.status == "executed"
    assert position is not None
    assert position.quantity == Decimal("1.5")
    assert position.avg_entry_price == Decimal("113.4466666666666666666666667")
    assert position.realized_pnl == Decimal("24.6350000000000000000000000")


def test_execution_engine_respects_risk_rejection_and_does_not_execute() -> None:
    broker = PaperBroker(initial_balances={"USDT": Decimal("1000")}, fee_rate=Decimal("0.001"))
    engine = ExecutionEngine(broker)
    order = build_order(side="BUY", quantity="1", market_price="100")
    risk_decision = RiskDecision(decision="reject", approved_quantity=Decimal("0"), reason_codes=("DAILY_LOSS_LIMIT",))

    fill = engine.execute(order, risk_decision)

    assert fill.status == "rejected"
    assert fill.reason_codes == ("DAILY_LOSS_LIMIT",)
    assert broker.get_balance("USDT") == Decimal("1000")
    assert broker.get_position("BTCUSDT") is None


def test_execution_engine_uses_resized_quantity() -> None:
    broker = PaperBroker(initial_balances={"USDT": Decimal("1000")}, fee_rate=Decimal("0.001"))
    engine = ExecutionEngine(broker)
    order = build_order(side="BUY", quantity="5", market_price="100")
    risk_decision = RiskDecision(decision="resize", approved_quantity=Decimal("2"), reason_codes=("RESIZED_FOR_RISK",))

    fill = engine.execute(order, risk_decision)

    assert fill.status == "executed"
    assert fill.requested_quantity == Decimal("2")
    assert fill.filled_quantity == Decimal("2")
    position = broker.get_position("BTCUSDT")
    assert position is not None
    assert position.quantity == Decimal("2")
