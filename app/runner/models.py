"""Runner models."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from app.features.models import FeatureSnapshot
from app.market_data.models import MarketSnapshot
from app.paper.models import FillResult, Position
from app.risk.models import RiskDecision
from app.strategies.models import StrategySignal


@dataclass(slots=True)
class RunnerConfig:
    """Configuration for the paper-only strategy runner."""

    order_quantity: Decimal = Decimal("1")
    stop_atr_multiple: Decimal = Decimal("2")
    risk_per_trade: Decimal = Decimal("0.005")
    max_daily_loss: Decimal = Decimal("0.02")
    max_open_positions: int = 3
    min_stop_distance_ratio: Decimal = Decimal("0.001")
    quantity_step: Decimal = Decimal("0.00000001")
    min_expected_edge_buffer_pct: Decimal = Decimal("0.0015")
    quote_asset: str = "USDT"
    mode: Literal["paper"] = "paper"
    history_limit: int = 200


@dataclass(slots=True)
class TradeReadiness:
    """Current deterministic trade-readiness state for one symbol."""

    selected_symbol: str
    runtime_active: bool
    mode: str
    enough_candle_history: bool
    deterministic_entry_signal: bool
    deterministic_exit_signal: bool
    risk_ready: bool
    risk_blocked: bool
    broker_ready: bool
    next_action: str
    reason_if_not_trading: str | None
    risk_reason_codes: tuple[str, ...]
    expected_edge_pct: Decimal | None = None
    estimated_round_trip_cost_pct: Decimal | None = None


@dataclass(slots=True)
class RunnerCycleResult:
    """Result of one runner cycle over a market snapshot."""

    market_snapshot: MarketSnapshot
    feature_snapshot: FeatureSnapshot
    signal: StrategySignal
    risk_decision: RiskDecision | None
    execution_result: FillResult | None
    current_position: Position | None
    current_pnl: Decimal
