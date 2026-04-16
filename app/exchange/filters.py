"""Exchange filter utilities."""

from decimal import Decimal
from typing import Any, Mapping, Sequence

from app.exchange.models import (
    LotSizeFilter,
    MarketLotSizeFilter,
    NotionalFilter,
    PriceFilter,
    SymbolFilters,
)


def _to_decimal(value: Any) -> Decimal:
    """Convert a Binance numeric value into a `Decimal`."""

    return Decimal(str(value))


def _to_bool(value: Any) -> bool:
    """Convert Binance boolean-like values into a `bool`."""

    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == "true"
    return bool(value)


def parse_symbol_filters(symbol: str, raw_filters: Sequence[Mapping[str, Any]]) -> SymbolFilters:
    """Parse Binance symbol filters into typed models."""

    parsed = SymbolFilters(symbol=symbol)

    for raw_filter in raw_filters:
        filter_type = str(raw_filter.get("filterType", ""))

        if filter_type == "PRICE_FILTER":
            parsed.price = PriceFilter(
                min_price=_to_decimal(raw_filter["minPrice"]),
                max_price=_to_decimal(raw_filter["maxPrice"]),
                tick_size=_to_decimal(raw_filter["tickSize"]),
            )
        elif filter_type == "LOT_SIZE":
            parsed.lot_size = LotSizeFilter(
                min_qty=_to_decimal(raw_filter["minQty"]),
                max_qty=_to_decimal(raw_filter["maxQty"]),
                step_size=_to_decimal(raw_filter["stepSize"]),
            )
        elif filter_type == "MARKET_LOT_SIZE":
            parsed.market_lot_size = MarketLotSizeFilter(
                min_qty=_to_decimal(raw_filter["minQty"]),
                max_qty=_to_decimal(raw_filter["maxQty"]),
                step_size=_to_decimal(raw_filter["stepSize"]),
            )
        elif filter_type == "MIN_NOTIONAL":
            parsed.notional = NotionalFilter(
                filter_type="MIN_NOTIONAL",
                min_notional=_to_decimal(raw_filter["minNotional"]),
                apply_min_to_market=_to_bool(raw_filter.get("applyToMarket", False)),
                avg_price_mins=int(raw_filter.get("avgPriceMins", 0)),
            )
        elif filter_type == "NOTIONAL":
            parsed.notional = NotionalFilter(
                filter_type="NOTIONAL",
                min_notional=_to_decimal(raw_filter["minNotional"]),
                max_notional=_to_decimal(raw_filter["maxNotional"]),
                apply_min_to_market=_to_bool(raw_filter.get("applyMinToMarket", False)),
                apply_max_to_market=_to_bool(raw_filter.get("applyMaxToMarket", False)),
                avg_price_mins=int(raw_filter.get("avgPriceMins", 0)),
            )

    return parsed


def normalize_symbol_filter(symbol: str, raw_filters: Sequence[Mapping[str, Any]]) -> SymbolFilters:
    """Backward-compatible alias for normalized typed symbol filters."""

    return parse_symbol_filters(symbol=symbol, raw_filters=raw_filters)
