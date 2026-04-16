from datetime import UTC, datetime
from decimal import Decimal

from app.market_data.candles import Candle, parse_kline_payload
from app.market_data.orderbook import TopOfBook, parse_book_ticker_payload
from app.market_data.trades import TradeTick, parse_trade_payload


def test_parse_trade_payload_normalizes_decimals_and_times() -> None:
    payload = {
        "e": "trade",
        "E": 1710000000123,
        "s": "BTCUSDT",
        "t": 12345,
        "p": "68000.12",
        "q": "0.015",
        "T": 1710000000111,
        "m": True,
    }

    trade = parse_trade_payload(payload)

    assert isinstance(trade, TradeTick)
    assert trade.symbol == "BTCUSDT"
    assert trade.trade_id == 12345
    assert trade.price == Decimal("68000.12")
    assert trade.quantity == Decimal("0.015")
    assert trade.event_time == datetime(2024, 3, 9, 16, 0, 0, 123000, tzinfo=UTC)
    assert trade.trade_time == datetime(2024, 3, 9, 16, 0, 0, 111000, tzinfo=UTC)
    assert trade.is_buyer_maker is True


def test_parse_book_ticker_payload_normalizes_best_bid_and_ask() -> None:
    payload = {
        "u": 400900217,
        "s": "ETHUSDT",
        "b": "3500.10",
        "B": "4.5",
        "a": "3500.20",
        "A": "3.1",
        "E": 1710000000456,
    }

    top_of_book = parse_book_ticker_payload(payload)

    assert isinstance(top_of_book, TopOfBook)
    assert top_of_book.symbol == "ETHUSDT"
    assert top_of_book.bid_price == Decimal("3500.10")
    assert top_of_book.bid_quantity == Decimal("4.5")
    assert top_of_book.ask_price == Decimal("3500.20")
    assert top_of_book.ask_quantity == Decimal("3.1")
    assert top_of_book.event_time == datetime(2024, 3, 9, 16, 0, 0, 456000, tzinfo=UTC)


def test_parse_kline_payload_normalizes_candle() -> None:
    payload = {
        "e": "kline",
        "E": 1710000000789,
        "s": "BTCUSDT",
        "k": {
            "t": 1710000000000,
            "T": 1710000059999,
            "i": "1m",
            "o": "67950.00",
            "c": "68010.50",
            "h": "68025.00",
            "l": "67940.10",
            "v": "12.345",
            "n": 105,
            "x": False,
            "q": "839999.99",
        },
    }

    candle = parse_kline_payload(payload)

    assert isinstance(candle, Candle)
    assert candle.symbol == "BTCUSDT"
    assert candle.timeframe == "1m"
    assert candle.open == Decimal("67950.00")
    assert candle.high == Decimal("68025.00")
    assert candle.low == Decimal("67940.10")
    assert candle.close == Decimal("68010.50")
    assert candle.volume == Decimal("12.345")
    assert candle.quote_volume == Decimal("839999.99")
    assert candle.trade_count == 105
    assert candle.is_closed is False
    assert candle.open_time == datetime(2024, 3, 9, 16, 0, 0, tzinfo=UTC)
    assert candle.close_time == datetime(2024, 3, 9, 16, 0, 59, 999000, tzinfo=UTC)
    assert candle.event_time == datetime(2024, 3, 9, 16, 0, 0, 789000, tzinfo=UTC)
