"""Market data stream normalization and snapshot tracking."""

from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

from app.exchange.binance_ws import BinanceWebSocketClient
from app.market_data.candles import Candle, parse_kline_payload
from app.market_data.models import MarketSnapshot
from app.market_data.orderbook import TopOfBook, parse_book_ticker_payload
from app.market_data.trades import TradeTick, parse_trade_payload


class StreamManager:
    """Normalize raw websocket payloads into reconnect-safe market snapshots."""

    def __init__(
        self,
        websocket_client: BinanceWebSocketClient | None = None,
        *,
        stale_after: timedelta = timedelta(seconds=5),
        time_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._websocket_client = websocket_client
        self._stale_after = stale_after
        self._time_provider = time_provider or self._utcnow
        self._snapshots: dict[str, MarketSnapshot] = {}

    @staticmethod
    def _utcnow() -> datetime:
        """Return the current UTC time."""

        return datetime.now(tz=UTC)

    @staticmethod
    def _unwrap_payload(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return the raw Binance event from either direct or combined stream payloads."""

        data = payload.get("data")
        if isinstance(data, Mapping):
            return data
        return payload

    def _received_at(self, received_at: datetime | None) -> datetime:
        """Resolve an event receive time."""

        return received_at or self._time_provider()

    def _merge_snapshot(
        self,
        *,
        symbol: str,
        trade: TradeTick | None = None,
        top_of_book: TopOfBook | None = None,
        candle: Candle | None = None,
        event_time: datetime,
        received_at: datetime,
    ) -> MarketSnapshot:
        """Merge a normalized event into the latest market snapshot."""

        current = self._snapshots.get(symbol, MarketSnapshot(symbol=symbol))
        last_price = current.last_price
        if trade is not None:
            last_price = trade.price
        elif candle is not None:
            last_price = candle.close

        snapshot = MarketSnapshot(
            symbol=symbol,
            trade=trade or current.trade,
            top_of_book=top_of_book or current.top_of_book,
            candle=candle or current.candle,
            last_price=last_price,
            bid_price=top_of_book.bid_price if top_of_book is not None else current.bid_price,
            ask_price=top_of_book.ask_price if top_of_book is not None else current.ask_price,
            event_time=event_time,
            received_at=received_at,
            is_stale=False,
        )
        self._snapshots[symbol] = snapshot
        return snapshot

    def normalize_trade(
        self,
        payload: Mapping[str, Any],
        *,
        received_at: datetime | None = None,
    ) -> MarketSnapshot:
        """Normalize a trade payload into the latest snapshot state."""

        trade = parse_trade_payload(self._unwrap_payload(payload))
        return self._merge_snapshot(
            symbol=trade.symbol,
            trade=trade,
            event_time=trade.event_time,
            received_at=self._received_at(received_at),
        )

    def normalize_top_of_book(
        self,
        payload: Mapping[str, Any],
        *,
        received_at: datetime | None = None,
    ) -> MarketSnapshot:
        """Normalize a book ticker payload into the latest snapshot state."""

        top_of_book = parse_book_ticker_payload(self._unwrap_payload(payload))
        return self._merge_snapshot(
            symbol=top_of_book.symbol,
            top_of_book=top_of_book,
            event_time=top_of_book.event_time,
            received_at=self._received_at(received_at),
        )

    def normalize_candle(
        self,
        payload: Mapping[str, Any],
        *,
        received_at: datetime | None = None,
    ) -> MarketSnapshot:
        """Normalize a kline payload into the latest snapshot state."""

        candle = parse_kline_payload(self._unwrap_payload(payload))
        return self._merge_snapshot(
            symbol=candle.symbol,
            candle=candle,
            event_time=candle.event_time,
            received_at=self._received_at(received_at),
        )

    def normalize_payload(
        self,
        payload: Mapping[str, Any],
        *,
        received_at: datetime | None = None,
    ) -> MarketSnapshot | None:
        """Normalize a supported websocket payload into a market snapshot."""

        event = str(self._unwrap_payload(payload).get("e", ""))
        if event in {"trade", "aggTrade"}:
            return self.normalize_trade(payload, received_at=received_at)
        if event == "bookTicker":
            return self.normalize_top_of_book(payload, received_at=received_at)
        if event == "kline":
            return self.normalize_candle(payload, received_at=received_at)
        return None

    def get_snapshot(self, symbol: str, *, now: datetime | None = None) -> MarketSnapshot | None:
        """Return the latest snapshot for a symbol with stale-data status applied."""

        snapshot = self._snapshots.get(symbol.upper())
        if snapshot is None:
            return None

        is_stale = self.is_stale(symbol, now=now)
        if snapshot.is_stale == is_stale:
            return snapshot

        updated = replace(snapshot, is_stale=is_stale)
        self._snapshots[symbol.upper()] = updated
        return updated

    def is_stale(self, symbol: str, *, now: datetime | None = None) -> bool:
        """Return whether the latest snapshot for a symbol is stale."""

        snapshot = self._snapshots.get(symbol.upper())
        if snapshot is None or snapshot.received_at is None:
            return True

        reference_time = now or self._time_provider()
        return reference_time - snapshot.received_at > self._stale_after

    def stale_symbols(self, *, now: datetime | None = None) -> list[str]:
        """Return the symbols whose latest snapshots are stale."""

        return [
            symbol
            for symbol in sorted(self._snapshots)
            if self.is_stale(symbol, now=now)
        ]

    async def stream(
        self,
        streams: Sequence[str],
        *,
        websocket_client: BinanceWebSocketClient | None = None,
    ) -> AsyncIterator[MarketSnapshot]:
        """Yield normalized snapshots from the configured websocket client."""

        client = websocket_client or self._websocket_client
        if client is None:
            raise ValueError("A Binance websocket client is required to stream market data.")

        async for payload in client.messages(streams):
            snapshot = self.normalize_payload(payload)
            if snapshot is not None:
                yield snapshot
