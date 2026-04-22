from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.monitoring.trade_quality import build_trade_quality_analytics
from app.storage.models import MarketCandleSnapshotRecord, TradeRecord


def _trade(
    *,
    order_id: str,
    symbol: str,
    side: str,
    fill_price: str,
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
        fill_price=Decimal(fill_price),
        realized_pnl=Decimal(realized_pnl),
        quote_balance=Decimal("1000"),
        event_time=event_time,
    )


def _candle(
    *,
    symbol: str,
    close_time: datetime,
    close_price: str,
    minutes: int,
) -> MarketCandleSnapshotRecord:
    return MarketCandleSnapshotRecord(
        symbol=symbol,
        timeframe="1m",
        open_time=close_time - timedelta(minutes=minutes),
        close_time=close_time,
        close_price=Decimal(close_price),
        event_time=close_time,
    )


def test_build_trade_quality_analytics_calculates_expected_attribution() -> None:
    base_time = datetime(2024, 3, 9, 16, 0, tzinfo=UTC)
    analytics = build_trade_quality_analytics(
        trades=[
            _trade(
                order_id="BUY-1",
                symbol="BTCUSDT",
                side="BUY",
                fill_price="100",
                realized_pnl="0",
                event_time=base_time,
            ),
            _trade(
                order_id="SELL-1",
                symbol="BTCUSDT",
                side="SELL",
                fill_price="103",
                realized_pnl="3",
                event_time=base_time + timedelta(minutes=3),
            ),
            _trade(
                order_id="BUY-2",
                symbol="BTCUSDT",
                side="BUY",
                fill_price="102",
                realized_pnl="0",
                event_time=base_time + timedelta(minutes=10),
            ),
            _trade(
                order_id="SELL-2",
                symbol="BTCUSDT",
                side="SELL",
                fill_price="100",
                realized_pnl="-2",
                event_time=base_time + timedelta(minutes=12),
            ),
        ],
        candles=[
            _candle(symbol="BTCUSDT", close_time=base_time + timedelta(minutes=1), close_price="101", minutes=1),
            _candle(symbol="BTCUSDT", close_time=base_time + timedelta(minutes=2), close_price="104", minutes=1),
            _candle(symbol="BTCUSDT", close_time=base_time + timedelta(minutes=3), close_price="103", minutes=1),
            _candle(symbol="BTCUSDT", close_time=base_time + timedelta(minutes=11), close_price="99", minutes=1),
            _candle(symbol="BTCUSDT", close_time=base_time + timedelta(minutes=12), close_price="100", minutes=1),
        ],
    )

    assert analytics.summary.total_closed_trades == 2
    assert analytics.summary.average_mfe_pct == Decimal("2.00")
    assert analytics.summary.average_mae_pct == Decimal("1.47")
    assert analytics.summary.average_captured_move_pct == Decimal("37.50")
    assert analytics.summary.average_giveback_pct == Decimal("12.50")
    assert analytics.summary.average_entry_quality_score == Decimal("50.00")
    assert analytics.summary.average_exit_quality_score == Decimal("54.17")
    assert analytics.summary.longest_no_trade_seconds == 420
    assert analytics.summary.hold_time_distribution.average_seconds == 150
    assert analytics.summary.hold_time_distribution.median_seconds == 150
    assert analytics.summary.hold_time_distribution.p75_seconds == 180
    assert analytics.summary.hold_time_distribution.max_seconds == 180

    assert [detail.order_id for detail in analytics.details] == ["SELL-2", "SELL-1"]
    latest_detail = analytics.details[1]
    assert latest_detail.mfe_pct == Decimal("4.00")
    assert latest_detail.mae_pct == Decimal("0.00")
    assert latest_detail.captured_move_pct == Decimal("75.00")
    assert latest_detail.giveback_pct == Decimal("25.00")
    assert latest_detail.entry_quality_score == Decimal("100.00")
    assert latest_detail.exit_quality_score == Decimal("75.00")


def test_build_trade_quality_analytics_respects_start_date_for_closed_trade_details() -> None:
    base_time = datetime(2024, 3, 9, 16, 0, tzinfo=UTC)
    analytics = build_trade_quality_analytics(
        trades=[
            _trade(
                order_id="BUY-1",
                symbol="BTCUSDT",
                side="BUY",
                fill_price="100",
                realized_pnl="0",
                event_time=base_time,
            ),
            _trade(
                order_id="SELL-1",
                symbol="BTCUSDT",
                side="SELL",
                fill_price="103",
                realized_pnl="3",
                event_time=base_time + timedelta(minutes=3),
            ),
            _trade(
                order_id="BUY-2",
                symbol="BTCUSDT",
                side="BUY",
                fill_price="102",
                realized_pnl="0",
                event_time=base_time + timedelta(days=1),
            ),
            _trade(
                order_id="SELL-2",
                symbol="BTCUSDT",
                side="SELL",
                fill_price="100",
                realized_pnl="-2",
                event_time=base_time + timedelta(days=1, minutes=12),
            ),
        ],
        candles=[
            _candle(
                symbol="BTCUSDT",
                close_time=base_time + timedelta(days=1, minutes=11),
                close_price="99",
                minutes=1,
            ),
            _candle(
                symbol="BTCUSDT",
                close_time=base_time + timedelta(days=1, minutes=12),
                close_price="100",
                minutes=1,
            ),
        ],
        start_date=date(2024, 3, 10),
        end_date=date(2024, 3, 10),
    )

    assert analytics.summary.total_closed_trades == 1
    assert analytics.details[0].order_id == "SELL-2"
    assert analytics.summary.longest_no_trade_seconds == 720
