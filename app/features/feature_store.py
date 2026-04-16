"""Deterministic feature engine."""

from collections.abc import Sequence

from app.features.indicators import ema, rsi
from app.features.microstructure import bid_ask_spread, mid_price, order_book_imbalance
from app.features.models import FeatureConfig, FeatureSnapshot
from app.features.regime import classify_regime
from app.features.volatility import build_atr
from app.market_data.candles import Candle
from app.market_data.orderbook import TopOfBook


class FeatureEngine:
    """Build typed feature snapshots from normalized market data."""

    def __init__(self, config: FeatureConfig | None = None) -> None:
        self.config = config or FeatureConfig()

    def _validate_candles(self, candles: Sequence[Candle]) -> tuple[str, Candle]:
        """Validate a candle sequence and return the shared symbol and latest candle."""

        if not candles:
            raise ValueError("candles cannot be empty")

        symbol = candles[0].symbol
        latest = candles[-1]

        for previous, candle in zip(candles, candles[1:]):
            if candle.symbol != symbol:
                raise ValueError("all candles must share the same symbol")
            if candle.open_time <= previous.open_time:
                raise ValueError("candles must be ordered by ascending open_time")

        return symbol, latest

    @staticmethod
    def _validate_top_of_book(symbol: str, top_of_book: TopOfBook | None) -> None:
        """Validate that top-of-book data matches the candle symbol when present."""

        if top_of_book is not None and top_of_book.symbol != symbol:
            raise ValueError("top_of_book symbol must match candle symbol")

    def build_snapshot(
        self,
        candles: Sequence[Candle],
        top_of_book: TopOfBook | None = None,
    ) -> FeatureSnapshot:
        """Build a typed feature snapshot from normalized candles and top-of-book data."""

        symbol, latest_candle = self._validate_candles(candles)
        self._validate_top_of_book(symbol, top_of_book)

        closes = [candle.close for candle in candles]
        ema_fast = ema(closes, period=self.config.ema_fast_period)
        ema_slow = ema(closes, period=self.config.ema_slow_period)

        timestamp = latest_candle.event_time
        if top_of_book is not None and top_of_book.event_time > timestamp:
            timestamp = top_of_book.event_time

        return FeatureSnapshot(
            symbol=symbol,
            timestamp=timestamp,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            rsi=rsi(closes, period=self.config.rsi_period),
            atr=build_atr(candles, period=self.config.atr_period),
            mid_price=mid_price(top_of_book) if top_of_book is not None else None,
            bid_ask_spread=bid_ask_spread(top_of_book) if top_of_book is not None else None,
            order_book_imbalance=(
                order_book_imbalance(top_of_book) if top_of_book is not None else None
            ),
            regime=classify_regime(ema_fast=ema_fast, ema_slow=ema_slow),
        )
