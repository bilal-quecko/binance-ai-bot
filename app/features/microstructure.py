"""Microstructure feature helpers."""

from decimal import Decimal

from app.market_data.orderbook import TopOfBook


def mid_price(top_of_book: TopOfBook) -> Decimal:
    """Return the midpoint price from the best bid and ask."""

    return (top_of_book.bid_price + top_of_book.ask_price) / Decimal("2")


def bid_ask_spread(top_of_book: TopOfBook) -> Decimal:
    """Return the absolute bid/ask spread."""

    return top_of_book.ask_price - top_of_book.bid_price


def order_book_imbalance(top_of_book: TopOfBook) -> Decimal | None:
    """Return the top-of-book quantity imbalance."""

    total_quantity = top_of_book.bid_quantity + top_of_book.ask_quantity
    if total_quantity == Decimal("0"):
        return None
    return (top_of_book.bid_quantity - top_of_book.ask_quantity) / total_quantity
