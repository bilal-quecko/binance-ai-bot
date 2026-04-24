from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.monitoring.profile_calibration import build_profile_calibration_report
from app.storage.models import DrawdownSummary, FillRecord, RunnerEventRecord, TradeRecord


def _trade(
    *,
    order_id: str,
    side: str,
    realized_pnl: str,
    event_time: datetime,
    trading_profile: str,
) -> TradeRecord:
    return TradeRecord(
        order_id=order_id,
        symbol="XRPUSDT",
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
        execution_source="auto",
        trading_profile=trading_profile,
        session_id="session-a",
    )


def _fill(*, order_id: str, event_time: datetime, trading_profile: str, fee_paid: str = "0.1") -> FillRecord:
    return FillRecord(
        order_id=order_id,
        symbol="XRPUSDT",
        side="BUY",
        filled_quantity=Decimal("1"),
        fill_price=Decimal("1"),
        fee_paid=Decimal(fee_paid),
        realized_pnl=Decimal("0"),
        quote_balance=Decimal("1000"),
        event_time=event_time,
        execution_source="auto",
        trading_profile=trading_profile,
        session_id="session-a",
    )


def _event(*, reason_codes: tuple[str, ...], event_time: datetime, trading_profile: str) -> RunnerEventRecord:
    reason_list = '", "'.join(reason_codes)
    return RunnerEventRecord(
        event_type="trade_blocked",
        symbol="XRPUSDT",
        message=f"blocked={reason_codes[0]}",
        payload_json=(
            '{"reason_codes": ["' + reason_list + '"], "trading_profile": "' + trading_profile + '"}'
        ),
        event_time=event_time,
    )


def _drawdown(*, current_pct: str = "0.01", max_pct: str = "0.02") -> DrawdownSummary:
    return DrawdownSummary(
        current_drawdown=Decimal("10"),
        current_drawdown_pct=Decimal(current_pct),
        max_drawdown=Decimal("20"),
        max_drawdown_pct=Decimal(max_pct),
        points=[],
    )


def test_profile_calibration_reports_insufficient_sample_size() -> None:
    report = build_profile_calibration_report(
        symbol="XRPUSDT",
        start_date=date(2024, 3, 9),
        end_date=date(2024, 3, 9),
        trades=[],
        fills=[],
        events=[],
        drawdown=_drawdown(),
    )

    conservative = next(item for item in report.recommendations if item.profile == "conservative")
    assert conservative.profile_health == "insufficient_data"
    assert conservative.recommendation == "keep"
    assert conservative.sample_size_warning is not None


def test_profile_calibration_recommends_loosen_for_too_strict_profile() -> None:
    base_time = datetime(2024, 3, 9, 12, 0, tzinfo=UTC)
    report = build_profile_calibration_report(
        symbol="XRPUSDT",
        start_date=date(2024, 3, 9),
        end_date=date(2024, 3, 9),
        trades=[],
        fills=[],
        events=[
            _event(reason_codes=("VOL_TOO_LOW",), event_time=base_time, trading_profile="balanced"),
            _event(reason_codes=("REGIME_NOT_TREND",), event_time=base_time + timedelta(minutes=1), trading_profile="balanced"),
            _event(reason_codes=("VOL_TOO_LOW",), event_time=base_time + timedelta(minutes=2), trading_profile="balanced"),
            _event(reason_codes=("MISSING_ATR_CONTEXT",), event_time=base_time + timedelta(minutes=3), trading_profile="balanced"),
        ],
        drawdown=_drawdown(),
    )

    balanced = next(item for item in report.recommendations if item.profile == "balanced")
    assert balanced.profile_health == "too_strict"
    assert balanced.recommendation == "loosen"
    assert any(item.threshold == "min_atr_ratio" for item in balanced.affected_thresholds)


def test_profile_calibration_recommends_tighten_for_too_loose_profile() -> None:
    base_time = datetime(2024, 3, 9, 12, 0, tzinfo=UTC)
    trades = [
        _trade(order_id="A-BUY-1", side="BUY", realized_pnl="0", event_time=base_time, trading_profile="aggressive"),
        _trade(order_id="A-SELL-1", side="SELL", realized_pnl="-4", event_time=base_time + timedelta(minutes=5), trading_profile="aggressive"),
        _trade(order_id="A-BUY-2", side="BUY", realized_pnl="0", event_time=base_time + timedelta(minutes=10), trading_profile="aggressive"),
        _trade(order_id="A-SELL-2", side="SELL", realized_pnl="-3", event_time=base_time + timedelta(minutes=15), trading_profile="aggressive"),
    ]
    fills = [_fill(order_id=trade.order_id, event_time=trade.event_time, trading_profile="aggressive") for trade in trades]
    report = build_profile_calibration_report(
        symbol="XRPUSDT",
        start_date=date(2024, 3, 9),
        end_date=date(2024, 3, 9),
        trades=trades,
        fills=fills,
        events=[],
        drawdown=_drawdown(current_pct="0.06", max_pct="0.10"),
    )

    aggressive = next(item for item in report.recommendations if item.profile == "aggressive")
    assert aggressive.profile_health == "too_loose"
    assert aggressive.recommendation == "tighten"
    assert any(item.threshold == "max_spread_ratio" for item in aggressive.affected_thresholds)


def test_profile_calibration_flags_fee_drag() -> None:
    base_time = datetime(2024, 3, 9, 12, 0, tzinfo=UTC)
    trades = [
        _trade(order_id="B-BUY-1", side="BUY", realized_pnl="0", event_time=base_time, trading_profile="balanced"),
        _trade(order_id="B-SELL-1", side="SELL", realized_pnl="-0.2", event_time=base_time + timedelta(minutes=10), trading_profile="balanced"),
        _trade(order_id="B-BUY-2", side="BUY", realized_pnl="0", event_time=base_time + timedelta(minutes=20), trading_profile="balanced"),
        _trade(order_id="B-SELL-2", side="SELL", realized_pnl="-0.3", event_time=base_time + timedelta(minutes=30), trading_profile="balanced"),
    ]
    fills = [
        _fill(order_id="B-BUY-1", event_time=base_time, trading_profile="balanced", fee_paid="0.3"),
        _fill(order_id="B-SELL-1", event_time=base_time + timedelta(minutes=10), trading_profile="balanced", fee_paid="0.3"),
        _fill(order_id="B-BUY-2", event_time=base_time + timedelta(minutes=20), trading_profile="balanced", fee_paid="0.3"),
        _fill(order_id="B-SELL-2", event_time=base_time + timedelta(minutes=30), trading_profile="balanced", fee_paid="0.3"),
    ]
    report = build_profile_calibration_report(
        symbol="XRPUSDT",
        start_date=date(2024, 3, 9),
        end_date=date(2024, 3, 9),
        trades=trades,
        fills=fills,
        events=[],
        drawdown=_drawdown(),
    )

    balanced = next(item for item in report.recommendations if item.profile == "balanced")
    assert balanced.profile_health == "fee_drag"
    assert balanced.recommendation == "tighten"
    assert any(item.threshold == "min_expected_edge_buffer_pct" for item in balanced.affected_thresholds)


def test_profile_calibration_uses_blocker_driven_loosen_recommendation() -> None:
    base_time = datetime(2024, 3, 9, 12, 0, tzinfo=UTC)
    report = build_profile_calibration_report(
        symbol="XRPUSDT",
        start_date=date(2024, 3, 9),
        end_date=date(2024, 3, 9),
        trades=[],
        fills=[],
        events=[
            _event(reason_codes=("REGIME_NOT_TREND",), event_time=base_time, trading_profile="conservative"),
            _event(reason_codes=("REGIME_NOT_TREND",), event_time=base_time + timedelta(minutes=1), trading_profile="conservative"),
            _event(reason_codes=("EMA_NOT_BULLISH",), event_time=base_time + timedelta(minutes=2), trading_profile="conservative"),
            _event(reason_codes=("MISSING_EMA",), event_time=base_time + timedelta(minutes=3), trading_profile="conservative"),
        ],
        drawdown=_drawdown(),
    )

    conservative = next(item for item in report.recommendations if item.profile == "conservative")
    assert conservative.recommendation == "loosen"
    assert conservative.blocker_share["no_trend_confirmation"] == Decimal("50.00")
