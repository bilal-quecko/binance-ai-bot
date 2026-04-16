"""Exchange models."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal


@dataclass(slots=True)
class PriceFilter:
    """Typed Binance `PRICE_FILTER` values for a symbol."""

    min_price: Decimal
    max_price: Decimal
    tick_size: Decimal


@dataclass(slots=True)
class LotSizeFilter:
    """Typed Binance `LOT_SIZE` values for a symbol."""

    min_qty: Decimal
    max_qty: Decimal
    step_size: Decimal


@dataclass(slots=True)
class MarketLotSizeFilter:
    """Typed Binance `MARKET_LOT_SIZE` values for a symbol."""

    min_qty: Decimal
    max_qty: Decimal
    step_size: Decimal


@dataclass(slots=True)
class NotionalFilter:
    """Typed Binance `MIN_NOTIONAL` or `NOTIONAL` values for a symbol."""

    filter_type: Literal["MIN_NOTIONAL", "NOTIONAL"]
    min_notional: Decimal
    apply_min_to_market: bool
    avg_price_mins: int
    max_notional: Decimal | None = None
    apply_max_to_market: bool | None = None


@dataclass(slots=True)
class SymbolFilters:
    """Normalized typed symbol filter set."""

    symbol: str
    price: PriceFilter | None = None
    lot_size: LotSizeFilter | None = None
    notional: NotionalFilter | None = None
    market_lot_size: MarketLotSizeFilter | None = None


@dataclass(slots=True)
class ExchangeSymbol:
    """Typed Binance exchange symbol metadata."""

    symbol: str
    status: str
    base_asset: str
    quote_asset: str
    base_asset_precision: int
    quote_asset_precision: int
    order_types: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    filters: SymbolFilters = field(default_factory=lambda: SymbolFilters(symbol=""))


@dataclass(slots=True)
class ExchangeInfo:
    """Typed Binance exchange info response."""

    timezone: str
    server_time: int
    symbols: list[ExchangeSymbol] = field(default_factory=list)


@dataclass(slots=True)
class AccountBalance:
    """Typed Binance account balance entry."""

    asset: str
    free: Decimal
    locked: Decimal


@dataclass(slots=True)
class AccountInfo:
    """Typed Binance account information response."""

    maker_commission: int
    taker_commission: int
    buyer_commission: int
    seller_commission: int
    can_trade: bool
    can_withdraw: bool
    can_deposit: bool
    account_type: str
    update_time: int
    permissions: list[str] = field(default_factory=list)
    balances: list[AccountBalance] = field(default_factory=list)
