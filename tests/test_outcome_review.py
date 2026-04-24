from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.monitoring.outcome_review import build_paper_trade_review
from app.storage.models import FillRecord, RunnerEventRecord, TradeRecord


def _trade(
    *,
    order_id: str,
    symbol: str,
    side: str,
    realized_pnl: str,
    event_time: datetime,
    execution_source: str,
    trading_profile: str,
) -> TradeRecord:
    return TradeRecord(
        order_id=order_id,
        symbol=symbol,
        side=side,
        requested_quantity=Decimal("1"),
        approved_quantity=Decimal("1"),
        filled_quantity=Decimal("1"),
        status="executed",
        risk_decision="approve",
        reason_codes=("APPROVED",),
        fill_price=Decimal("1"),
        realized_pnl=Decimal(realized_pnl),
        quote_balance=Decimal("1000"),
        event_time=event_time,
        execution_source=execution_source,
        trading_profile=trading_profile,
        session_id="session-a",
    )


def _fill(
    *,
    order_id: str,
    symbol: str,
    side: str,
    event_time: datetime,
    fee_paid: str,
    execution_source: str,
    trading_profile: str,
) -> FillRecord:
    return FillRecord(
        order_id=order_id,
        symbol=symbol,
        side=side,
        filled_quantity=Decimal("1"),
        fill_price=Decimal("1"),
        fee_paid=Decimal(fee_paid),
        realized_pnl=Decimal("0"),
        quote_balance=Decimal("1000"),
        event_time=event_time,
        execution_source=execution_source,
        trading_profile=trading_profile,
        session_id="session-a",
    )


def _event(*, reason_codes: tuple[str, ...], event_time: datetime) -> RunnerEventRecord:
    return RunnerEventRecord(
        event_type="trade_blocked",
        symbol="XRPUSDT",
        message=f"blocked={reason_codes[0]}",
        payload_json='{"reason_codes": ["' + '", "'.join(reason_codes) + '"]}',
        event_time=event_time,
    )


def test_build_paper_trade_review_calculates_session_profile_and_blocker_analytics() -> None:
    base_time = datetime(2024, 3, 9, 12, 0, tzinfo=UTC)
    trades = [
        _trade(
            order_id="AUTO-BUY-1",
            symbol="XRPUSDT",
            side="BUY",
            realized_pnl="0",
            event_time=base_time,
            execution_source="auto",
            trading_profile="balanced",
        ),
        _trade(
            order_id="AUTO-SELL-1",
            symbol="XRPUSDT",
            side="SELL",
            realized_pnl="12",
            event_time=base_time + timedelta(minutes=10),
            execution_source="auto",
            trading_profile="balanced",
        ),
        _trade(
            order_id="MANUAL-BUY-1",
            symbol="XRPUSDT",
            side="BUY",
            realized_pnl="0",
            event_time=base_time + timedelta(minutes=20),
            execution_source="manual",
            trading_profile="aggressive",
        ),
        _trade(
            order_id="MANUAL-SELL-1",
            symbol="XRPUSDT",
            side="SELL",
            realized_pnl="-6",
            event_time=base_time + timedelta(minutes=30),
            execution_source="manual",
            trading_profile="aggressive",
        ),
        _trade(
            order_id="CONS-BUY-1",
            symbol="BTCUSDT",
            side="BUY",
            realized_pnl="0",
            event_time=base_time + timedelta(minutes=40),
            execution_source="auto",
            trading_profile="conservative",
        ),
        _trade(
            order_id="CONS-SELL-1",
            symbol="BTCUSDT",
            side="SELL",
            realized_pnl="4",
            event_time=base_time + timedelta(minutes=50),
            execution_source="auto",
            trading_profile="conservative",
        ),
    ]
    fills = [
        _fill(
            order_id=trade.order_id,
            symbol=trade.symbol,
            side=trade.side,
            event_time=trade.event_time,
            fee_paid="0.2",
            execution_source=trade.execution_source,
            trading_profile=trade.trading_profile,
        )
        for trade in trades
    ]
    events = [
        _event(reason_codes=("VOL_TOO_LOW",), event_time=base_time + timedelta(minutes=5)),
        _event(reason_codes=("EDGE_BELOW_COSTS",), event_time=base_time + timedelta(minutes=15)),
        _event(reason_codes=("REGIME_NOT_TREND",), event_time=base_time + timedelta(minutes=25)),
        _event(reason_codes=("VOL_TOO_LOW",), event_time=base_time + timedelta(minutes=35)),
        RunnerEventRecord(
            event_type="execution_result",
            symbol="XRPUSDT",
            message="status=executed",
            payload_json='{"status": "executed"}',
            event_time=base_time + timedelta(minutes=50),
        ),
    ]

    review = build_paper_trade_review(
        symbol="XRPUSDT",
        start_date=date(2024, 3, 9),
        end_date=date(2024, 3, 9),
        trades=trades,
        fills=fills,
        events=events,
    )

    assert review.session.total_closed_trades == 3
    assert review.session.trades_per_hour == Decimal("7.20")
    assert review.session.win_rate == Decimal("66.67")
    assert review.session.average_pnl == Decimal("3.3333")
    assert review.session.average_hold_seconds == 600
    assert review.session.fees_paid == Decimal("1.2")
    assert review.session.idle_duration_seconds == 0
    assert [(item.symbol, item.trade_count) for item in review.session.trades_per_symbol] == [
        ("XRPUSDT", 4),
        ("BTCUSDT", 2),
    ]

    assert [(item.blocker_key, item.count, item.frequency_pct) for item in review.blockers] == [
        ("low_volatility", 2, Decimal("50.00")),
        ("edge_below_fees", 1, Decimal("25.00")),
        ("no_trend_confirmation", 1, Decimal("25.00")),
    ]

    assert [(item.profile, item.trade_count, item.realized_pnl) for item in review.profiles] == [
        ("conservative", 1, Decimal("4")),
        ("balanced", 1, Decimal("12")),
        ("aggressive", 1, Decimal("-6")),
    ]
    assert [(item.execution_source, item.trade_count, item.realized_pnl) for item in review.execution_sources] == [
        ("auto", 2, Decimal("16")),
        ("manual", 1, Decimal("-6")),
    ]
    assert any("quiet conditions" in item.summary for item in review.suggestions)
