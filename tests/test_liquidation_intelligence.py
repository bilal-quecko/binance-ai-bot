from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.api.bot_api import BackfillStatusResponse, FusionSignalResponse, _build_trading_assistant_response
from app.data.binance_liquidation_feed import BinanceLiquidationEvent
from app.market_data.candles import Candle
from app.monitoring.liquidation_intelligence import (
    LiquidationIntelligenceSnapshot,
    aggregate_liquidation_events,
    interpret_liquidation_events,
)
from app.monitoring.liquidity_zones import (
    LiquidityZone,
    LiquidityZoneSnapshot,
    NearestLiquidityTarget,
)


BASE_TIME = datetime(2024, 3, 9, 12, 0, tzinfo=UTC)


def _event(*, side: str, notional: str, price: str = "100", seconds_ago: int = 0) -> BinanceLiquidationEvent:
    event_time = BASE_TIME - timedelta(seconds=seconds_ago)
    return BinanceLiquidationEvent(
        symbol="BTCUSDT",
        event_time=event_time,
        side=side,
        order_type="LIMIT",
        time_in_force="IOC",
        original_quantity=Decimal("1"),
        price=Decimal(price),
        average_price=Decimal(price),
        order_status="FILLED",
        last_filled_quantity=Decimal("1"),
        accumulated_filled_quantity=Decimal("1"),
        trade_time=event_time,
        notional_value=Decimal(notional),
    )


def _candles(*, start: str, step: str) -> list[Candle]:
    base = Decimal(start)
    move = Decimal(step)
    candles: list[Candle] = []
    for index in range(8):
        close = base + (move * Decimal(index))
        candles.append(
            Candle(
                symbol="BTCUSDT",
                timeframe="1m",
                open=close,
                high=close + Decimal("0.2"),
                low=close - Decimal("0.2"),
                close=close,
                volume=Decimal("100"),
                quote_volume=Decimal("1000000"),
                open_time=BASE_TIME - timedelta(minutes=8 - index),
                close_time=BASE_TIME - timedelta(minutes=8 - index, seconds=-59),
                event_time=BASE_TIME - timedelta(minutes=8 - index, seconds=-59),
                trade_count=100,
                is_closed=True,
            )
        )
    return candles


def _zones(*, sweep_risk: str, downside: str = "99", upside: str = "101") -> LiquidityZoneSnapshot:
    return LiquidityZoneSnapshot(
        upside_liquidity_zone=LiquidityZone(level=Decimal(upside), strength="high", reason="test upside"),
        downside_liquidity_zone=LiquidityZone(level=Decimal(downside), strength="high", reason="test downside"),
        nearest_liquidity_target=NearestLiquidityTarget(direction="down", level=Decimal(downside), distance_pct=Decimal("1"), strength="high"),
        sweep_risk=sweep_risk,  # type: ignore[arg-type]
        trade_timing_adjustment="wait_for_confirmation",
        tp_sl_alignment="needs_review",
        explanation="test zones",
    )


def test_aggregate_liquidation_events_normalizes_volume_and_frequency() -> None:
    aggregate = aggregate_liquidation_events(
        events=[_event(side="SELL", notional="1000"), _event(side="BUY", notional="3000")],
        window_seconds=60,
    )

    assert aggregate.liquidation_volume_long == Decimal("1000.0000")
    assert aggregate.liquidation_volume_short == Decimal("3000.0000")
    assert aggregate.imbalance_ratio == Decimal("50.0000")
    assert aggregate.event_frequency == Decimal("2.0000")


def test_cascade_down_detection() -> None:
    snapshot = interpret_liquidation_events(
        symbol="BTCUSDT",
        events=[
            _event(side="SELL", notional="90000", price="99.6"),
            _event(side="SELL", notional="40000", price="99.2", seconds_ago=20),
        ],
        candles=_candles(start="102", step="-0.5"),
        now=BASE_TIME,
    )

    assert snapshot.liquidation_signal == "cascade_down"
    assert snapshot.dominant_side == "longs_liquidated"
    assert snapshot.liquidation_intensity == "high"


def test_cascade_up_detection() -> None:
    snapshot = interpret_liquidation_events(
        symbol="BTCUSDT",
        events=[
            _event(side="BUY", notional="90000", price="101.2"),
            _event(side="BUY", notional="40000", price="101.6", seconds_ago=20),
        ],
        candles=_candles(start="98", step="0.5"),
        now=BASE_TIME,
    )

    assert snapshot.liquidation_signal == "cascade_up"
    assert snapshot.dominant_side == "shorts_liquidated"


def test_exhaustion_detection_when_spike_stalls_price() -> None:
    snapshot = interpret_liquidation_events(
        symbol="BTCUSDT",
        events=[_event(side="SELL", notional="25000", price="100", seconds_ago=index * 4) for index in range(5)],
        candles=_candles(start="100", step="0.01"),
        now=BASE_TIME,
    )

    assert snapshot.liquidation_signal == "exhaustion"


def test_sweep_confirmation_uses_liquidity_zones() -> None:
    snapshot = interpret_liquidation_events(
        symbol="BTCUSDT",
        events=[_event(side="SELL", notional="60000", price="99.1")],
        candles=_candles(start="101", step="-0.2"),
        liquidity_zones=_zones(sweep_risk="downside_sweep", downside="99"),
        now=BASE_TIME,
    )

    assert snapshot.liquidation_signal == "sweep_confirmation"


def test_noise_and_no_event_fallback() -> None:
    no_events = interpret_liquidation_events(symbol="BTCUSDT", events=(), candles=(), now=BASE_TIME)
    noise = interpret_liquidation_events(
        symbol="BTCUSDT",
        events=[_event(side="SELL", notional="100", price="100")],
        candles=_candles(start="100", step="0.1"),
        now=BASE_TIME,
    )

    assert no_events.liquidation_signal == "none"
    assert noise.liquidation_signal == "noise"


def test_trading_assistant_waits_when_liquidation_cascade_opposes_buy(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.bot_api._load_liquidation_intelligence",
        lambda **_: LiquidationIntelligenceSnapshot(
            liquidation_signal="cascade_down",
            liquidation_intensity="high",
            dominant_side="longs_liquidated",
            interpretation_confidence="high",
            explanation="Downside cascade.",
        ),
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
        candles=_candles(start="100", step="0.2"),
    )

    assert assistant.decision == "wait"
    assert assistant.liquidation_signal == "cascade_down"
    assert "force-order" in (assistant.why_not_trade or "")
