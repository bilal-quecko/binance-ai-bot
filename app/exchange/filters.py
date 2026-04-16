"""Exchange filter utilities."""

from decimal import Decimal

from app.exchange.models import SymbolFilter


def normalize_symbol_filter(symbol: str) -> SymbolFilter:
    """Return a placeholder normalized filter object."""

    return SymbolFilter(symbol=symbol, min_qty=Decimal("0.0"), step_size=Decimal("0.0"))
