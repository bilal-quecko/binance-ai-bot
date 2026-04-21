from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.monitoring.metrics import build_performance_analytics
from app.storage.models import DrawdownSummary, PnlSnapshotRecord, TradeRecord


def _trade(
    *,
    order_id: str,
    symbol: str,
    side: str,
    realized_pnl: str,
    event_time: datetime,
    quantity: str = "1",
) -> TradeRecord:
    return TradeRecord(
        order_id=order_id,
        symbol=symbol,
        side=side,
        requested_quantity=Decimal(quantity),
        approved_quantity=Decimal(quantity),
        filled_quantity=Decimal(quantity),
        status="executed",
        risk_decision="approve",
        reason_codes=("APPROVED",),
        fill_price=Decimal("100"),
        realized_pnl=Decimal(realized_pnl),
        quote_balance=Decimal("1000"),
        event_time=event_time,
    )


def test_build_performance_analytics_calculates_expected_metrics() -> None:
    base_time = datetime(2024, 3, 9, 16, 0, tzinfo=UTC)
    analytics = build_performance_analytics(
        trades=[
            _trade(order_id="1", symbol="BTCUSDT", side="BUY", realized_pnl="0", event_time=base_time),
            _trade(order_id="2", symbol="BTCUSDT", side="SELL", realized_pnl="10", event_time=base_time + timedelta(minutes=5)),
            _trade(order_id="3", symbol="BTCUSDT", side="BUY", realized_pnl="0", event_time=base_time + timedelta(minutes=10)),
            _trade(order_id="4", symbol="BTCUSDT", side="SELL", realized_pnl="-4", event_time=base_time + timedelta(minutes=20)),
        ],
        latest_pnl=PnlSnapshotRecord(
            snapshot_time=base_time + timedelta(minutes=20),
            equity=Decimal("1080"),
            total_pnl=Decimal("40"),
            realized_pnl=Decimal("6"),
            cash_balance=Decimal("900"),
        ),
        drawdown=DrawdownSummary(
            current_drawdown=Decimal("12"),
            current_drawdown_pct=Decimal("0.01"),
            max_drawdown=Decimal("24"),
            max_drawdown_pct=Decimal("0.02"),
            points=[],
        ),
    )

    assert analytics.total_closed_trades == 2
    assert analytics.expectancy_per_closed_trade == Decimal("3")
    assert analytics.profit_factor == Decimal("2.5000")
    assert analytics.average_hold_seconds == 450
    assert analytics.average_win == Decimal("10")
    assert analytics.average_loss == Decimal("-4")
    assert analytics.session_realized_pnl == Decimal("6")
    assert analytics.session_unrealized_pnl == Decimal("34")
    assert analytics.symbol_realized_pnl == Decimal("6")
    assert analytics.max_drawdown == Decimal("24")
    assert analytics.current_drawdown == Decimal("12")


def test_build_performance_analytics_respects_start_date_for_closed_trade_metrics() -> None:
    base_time = datetime(2024, 3, 9, 16, 0, tzinfo=UTC)
    analytics = build_performance_analytics(
        trades=[
            _trade(order_id="1", symbol="BTCUSDT", side="BUY", realized_pnl="0", event_time=base_time),
            _trade(order_id="2", symbol="BTCUSDT", side="SELL", realized_pnl="10", event_time=base_time + timedelta(minutes=5)),
            _trade(order_id="3", symbol="BTCUSDT", side="BUY", realized_pnl="0", event_time=base_time + timedelta(days=1)),
            _trade(order_id="4", symbol="BTCUSDT", side="SELL", realized_pnl="-2", event_time=base_time + timedelta(days=1, minutes=15)),
        ],
        latest_pnl=None,
        drawdown=DrawdownSummary(
            current_drawdown=Decimal("0"),
            current_drawdown_pct=Decimal("0"),
            max_drawdown=Decimal("0"),
            max_drawdown_pct=Decimal("0"),
            points=[],
        ),
        start_date=date(2024, 3, 10),
        end_date=date(2024, 3, 10),
    )

    assert analytics.total_closed_trades == 1
    assert analytics.expectancy_per_closed_trade == Decimal("-2")
    assert analytics.average_hold_seconds == 900
    assert analytics.average_win is None
    assert analytics.average_loss == Decimal("-2")
