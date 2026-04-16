from datetime import UTC, datetime
from decimal import Decimal

from app.features.models import FeatureSnapshot
from app.paper.models import Position
from app.strategies.models import TrendFollowingConfig
from app.strategies.trend_following import TrendFollowingStrategy


def build_snapshot(**overrides: object) -> FeatureSnapshot:
    payload: dict[str, object] = {
        "symbol": "BTCUSDT",
        "timestamp": datetime(2024, 3, 9, 16, 0, 0, tzinfo=UTC),
        "ema_fast": Decimal("101"),
        "ema_slow": Decimal("100"),
        "rsi": Decimal("60"),
        "atr": Decimal("2"),
        "mid_price": Decimal("100"),
        "bid_ask_spread": Decimal("0.10"),
        "order_book_imbalance": Decimal("0.10"),
        "regime": "bullish",
    }
    payload.update(overrides)
    return FeatureSnapshot(**payload)


def build_position(**overrides: object) -> Position:
    payload: dict[str, object] = {
        "symbol": "BTCUSDT",
        "quantity": Decimal("1"),
        "avg_entry_price": Decimal("100"),
        "quote_asset": "USDT",
        "realized_pnl": Decimal("0"),
    }
    payload.update(overrides)
    return Position(**payload)


def test_trend_following_strategy_returns_buy_for_healthy_trend() -> None:
    strategy = TrendFollowingStrategy(
        TrendFollowingConfig(
            min_atr_ratio=Decimal("0.01"),
            max_atr_ratio=Decimal("0.05"),
            max_spread_ratio=Decimal("0.002"),
            min_order_book_imbalance=Decimal("-0.25"),
        )
    )

    signal = strategy.evaluate(build_snapshot())

    assert signal.side == "BUY"
    assert signal.confidence == Decimal("0.60")
    assert signal.reason_codes == ("EMA_BULLISH", "REGIME_TREND", "RISK_FILTERS_PASS")


def test_trend_following_strategy_returns_hold_when_regime_or_ema_do_not_confirm() -> None:
    strategy = TrendFollowingStrategy()

    signal = strategy.evaluate(
        build_snapshot(
            ema_fast=Decimal("99"),
            ema_slow=Decimal("100"),
            regime="neutral",
        )
    )

    assert signal.side == "HOLD"
    assert signal.reason_codes == ("REGIME_NOT_TREND",)


def test_trend_following_strategy_blocks_unhealthy_volatility_or_spread() -> None:
    strategy = TrendFollowingStrategy(
        TrendFollowingConfig(
            min_atr_ratio=Decimal("0.01"),
            max_atr_ratio=Decimal("0.05"),
            max_spread_ratio=Decimal("0.002"),
            min_order_book_imbalance=Decimal("-0.25"),
        )
    )

    low_vol_signal = strategy.evaluate(build_snapshot(atr=Decimal("0.2")))
    wide_spread_signal = strategy.evaluate(build_snapshot(bid_ask_spread=Decimal("0.50")))

    assert low_vol_signal.side == "HOLD"
    assert low_vol_signal.reason_codes == ("VOL_TOO_LOW",)
    assert wide_spread_signal.side == "HOLD"
    assert wide_spread_signal.reason_codes == ("MICROSTRUCTURE_UNHEALTHY",)


def test_trend_following_strategy_returns_sell_on_bearish_cross_with_position() -> None:
    strategy = TrendFollowingStrategy()

    signal = strategy.evaluate(
        build_snapshot(
            ema_fast=Decimal("99"),
            ema_slow=Decimal("100"),
            mid_price=Decimal("99"),
            regime="bearish",
        ),
        position=build_position(),
    )

    assert signal.side == "SELL"
    assert signal.reason_codes == ("EMA_BEARISH_EXIT",)


def test_trend_following_strategy_returns_sell_on_take_profit() -> None:
    strategy = TrendFollowingStrategy(
        TrendFollowingConfig(
            stop_loss_atr_multiple=Decimal("2"),
            take_profit_atr_multiple=Decimal("3"),
        )
    )

    signal = strategy.evaluate(
        build_snapshot(mid_price=Decimal("107"), atr=Decimal("2")),
        position=build_position(avg_entry_price=Decimal("100")),
    )

    assert signal.side == "SELL"
    assert signal.reason_codes == ("TAKE_PROFIT_HIT",)
