"""Strategy runner orchestration."""

import logging
import time
from collections.abc import Iterable
from decimal import Decimal

from app.execution.execution_engine import ExecutionEngine
from app.features.feature_store import FeatureEngine
from app.features.models import FeatureSnapshot
from app.market_data.candles import Candle
from app.market_data.models import MarketSnapshot
from app.market_data.orderbook import TopOfBook
from app.paper.broker import PaperBroker
from app.paper.models import FillResult, OrderRequest, Position
from app.risk.limits import RiskEngine
from app.risk.models import RiskDecision, RiskInput
from app.runner.models import RunnerConfig, RunnerCycleResult
from app.storage.repositories import StorageRepository
from app.strategies.models import StrategySignal
from app.strategies.trend_following import TrendFollowingStrategy


class StrategyRunner:
    """Run the deterministic paper-trading pipeline on market snapshots."""

    def __init__(
        self,
        *,
        feature_engine: FeatureEngine,
        strategy: TrendFollowingStrategy,
        risk_engine: RiskEngine,
        execution_engine: ExecutionEngine,
        broker: PaperBroker,
        config: RunnerConfig | None = None,
        logger: logging.Logger | None = None,
        storage_repository: StorageRepository | None = None,
    ) -> None:
        self._feature_engine = feature_engine
        self._strategy = strategy
        self._risk_engine = risk_engine
        self._execution_engine = execution_engine
        self._broker = broker
        self._config = config or RunnerConfig()
        self._logger = logger or logging.getLogger(__name__)
        self._storage_repository = storage_repository
        self._candles_by_symbol: dict[str, list[Candle]] = {}
        self._top_of_book_by_symbol: dict[str, TopOfBook] = {}
        self._last_price_by_symbol: dict[str, Decimal] = {}
        self._day_start_equity: Decimal | None = None

    def _record_snapshot(self, snapshot: MarketSnapshot) -> None:
        """Store the latest market state needed for feature generation and PnL."""

        symbol = snapshot.symbol.upper()
        if snapshot.candle is not None:
            candles = self._candles_by_symbol.setdefault(symbol, [])
            candles.append(snapshot.candle)
            self._candles_by_symbol[symbol] = candles[-self._config.history_limit :]
            self._last_price_by_symbol[symbol] = snapshot.candle.close
        if snapshot.top_of_book is not None:
            self._top_of_book_by_symbol[symbol] = snapshot.top_of_book
            self._last_price_by_symbol[symbol] = (
                snapshot.top_of_book.bid_price + snapshot.top_of_book.ask_price
            ) / Decimal("2")
        elif snapshot.last_price is not None:
            self._last_price_by_symbol[symbol] = snapshot.last_price

    def _current_equity(self) -> Decimal:
        """Return paper equity from balances plus marked-to-market positions."""

        quote_balance = self._broker.get_balance(self._config.quote_asset)
        position_value = Decimal("0")
        for symbol, position in self._broker.positions().items():
            market_price = self._last_price_by_symbol.get(symbol, position.avg_entry_price)
            position_value += position.quantity * market_price
        return quote_balance + position_value

    def _current_pnl(self) -> Decimal:
        """Return current total PnL versus the runner's day-start equity."""

        if self._day_start_equity is None:
            self._day_start_equity = self._current_equity()
        return self._current_equity() - self._day_start_equity

    def _build_feature_snapshot(self, symbol: str) -> FeatureSnapshot:
        """Build a feature snapshot from cached candles and top-of-book data."""

        candles = self._candles_by_symbol.get(symbol, [])
        if not candles:
            raise ValueError(f"no candle history available for {symbol}")
        return self._feature_engine.build_snapshot(
            candles,
            top_of_book=self._top_of_book_by_symbol.get(symbol),
        )

    def _build_risk_input(
        self,
        feature_snapshot: FeatureSnapshot,
        signal: StrategySignal,
        position: Position | None,
    ) -> RiskInput:
        """Create risk input for the current feature snapshot and broker state."""

        entry_price = feature_snapshot.mid_price or feature_snapshot.ema_fast or Decimal("0")
        stop_price = None
        if feature_snapshot.atr is not None and entry_price > Decimal("0"):
            stop_price = entry_price - (feature_snapshot.atr * self._config.stop_atr_multiple)

        if self._day_start_equity is None:
            self._day_start_equity = self._current_equity()

        requested_quantity = self._config.order_quantity
        if signal.side == "SELL":
            requested_quantity = position.quantity if position is not None else Decimal("0")

        return RiskInput(
            signal=signal,
            entry_price=entry_price,
            requested_quantity=requested_quantity,
            equity=self._current_equity(),
            day_start_equity=self._day_start_equity,
            daily_pnl=self._current_pnl(),
            open_positions=len(self._broker.positions()),
            current_position_quantity=position.quantity if position is not None else Decimal("0"),
            stop_price=stop_price,
            volatility=feature_snapshot.atr,
            risk_per_trade=self._config.risk_per_trade,
            max_daily_loss=self._config.max_daily_loss,
            max_open_positions=self._config.max_open_positions,
            min_stop_distance_ratio=self._config.min_stop_distance_ratio,
            quantity_step=self._config.quantity_step,
            mode=self._config.mode,
        )

    def _persist_event(
        self,
        *,
        event_type: str,
        symbol: str,
        message: str,
        payload: dict[str, object],
        event_time,
    ) -> None:
        """Persist a runner event when storage is configured."""

        if self._storage_repository is None:
            return
        self._storage_repository.insert_event(
            event_type=event_type,
            symbol=symbol,
            message=message,
            payload=payload,
            event_time=event_time,
        )

    def process_snapshot(self, snapshot: MarketSnapshot) -> RunnerCycleResult:
        """Process one market snapshot through feature, strategy, risk, and execution."""

        self._record_snapshot(snapshot)
        symbol = snapshot.symbol.upper()
        feature_snapshot = self._build_feature_snapshot(symbol)
        existing_position = self._broker.get_position(symbol)
        signal = self._strategy.evaluate(feature_snapshot, position=existing_position)
        self._logger.info("signal generated | symbol=%s side=%s reasons=%s", symbol, signal.side, signal.reason_codes)
        self._persist_event(
            event_type="signal_generated",
            symbol=symbol,
            message=f"signal={signal.side}",
            payload={"side": signal.side, "reason_codes": signal.reason_codes},
            event_time=feature_snapshot.timestamp,
        )

        risk_decision: RiskDecision | None = None
        execution_result: FillResult | None = None
        if signal.side in {"BUY", "SELL"}:
            risk_input = self._build_risk_input(feature_snapshot, signal, existing_position)
            risk_decision = self._risk_engine.evaluate(risk_input)
            self._logger.info(
                "risk decision | symbol=%s decision=%s quantity=%s reasons=%s",
                symbol,
                risk_decision.decision,
                risk_decision.approved_quantity,
                risk_decision.reason_codes,
            )
            self._persist_event(
                event_type="risk_decision",
                symbol=symbol,
                message=f"decision={risk_decision.decision}",
                payload={
                    "decision": risk_decision.decision,
                    "approved_quantity": str(risk_decision.approved_quantity),
                    "reason_codes": risk_decision.reason_codes,
                },
                event_time=feature_snapshot.timestamp,
            )

            order = OrderRequest(
                symbol=symbol,
                side=signal.side,
                quantity=risk_input.requested_quantity,
                market_price=feature_snapshot.mid_price or feature_snapshot.ema_fast or Decimal("0"),
                timestamp=feature_snapshot.timestamp,
                quote_asset=self._config.quote_asset,
                mode=self._config.mode,
            )
            execution_result = self._execution_engine.execute(order, risk_decision)
            self._logger.info(
                "execution result | symbol=%s side=%s status=%s qty=%s reasons=%s",
                symbol,
                signal.side,
                execution_result.status,
                execution_result.filled_quantity,
                execution_result.reason_codes,
            )
            self._persist_event(
                event_type="execution_result",
                symbol=symbol,
                message=f"status={execution_result.status}",
                payload={
                    "status": execution_result.status,
                    "side": signal.side,
                    "filled_quantity": str(execution_result.filled_quantity),
                    "reason_codes": execution_result.reason_codes,
                },
                event_time=feature_snapshot.timestamp,
            )
            if self._storage_repository is not None and risk_decision is not None:
                self._storage_repository.insert_trade(
                    fill_result=execution_result,
                    risk_decision=risk_decision,
                    approved_quantity=risk_decision.approved_quantity,
                    event_time=feature_snapshot.timestamp,
                )
                if execution_result.status == "executed":
                    self._storage_repository.insert_fill(execution_result, feature_snapshot.timestamp)
                    self._persist_event(
                        event_type="fill",
                        symbol=symbol,
                        message=f"fill_side={execution_result.side}",
                        payload={
                            "order_id": execution_result.order_id,
                            "fill_price": str(execution_result.fill_price),
                            "filled_quantity": str(execution_result.filled_quantity),
                            "realized_pnl": str(execution_result.realized_pnl),
                        },
                        event_time=feature_snapshot.timestamp,
                    )
        else:
            self._logger.info("risk decision | symbol=%s decision=skipped reasons=%s", symbol, ("NON_ACTIONABLE_SIGNAL",))
            self._logger.info("execution result | symbol=%s status=skipped", symbol)
            self._persist_event(
                event_type="risk_decision",
                symbol=symbol,
                message="decision=skipped",
                payload={"decision": "skipped", "reason_codes": ("NON_ACTIONABLE_SIGNAL",)},
                event_time=feature_snapshot.timestamp,
            )
            self._persist_event(
                event_type="execution_result",
                symbol=symbol,
                message="status=skipped",
                payload={"status": "skipped"},
                event_time=feature_snapshot.timestamp,
            )

        current_position = self._broker.get_position(symbol)
        current_pnl = self._current_pnl()
        current_equity = self._current_equity()
        self._logger.info(
            "portfolio state | symbol=%s position=%s pnl=%s",
            symbol,
            current_position,
            current_pnl,
        )
        if self._storage_repository is not None:
            self._storage_repository.insert_position_snapshot(
                current_position,
                feature_snapshot.timestamp,
                symbol,
            )
            self._storage_repository.insert_pnl_snapshot(
                snapshot_time=feature_snapshot.timestamp,
                equity=current_equity,
                total_pnl=current_pnl,
                realized_pnl=self._broker.realized_pnl,
                cash_balance=self._broker.get_balance(self._config.quote_asset),
            )
            self._persist_event(
                event_type="pnl_snapshot",
                symbol=symbol,
                message="portfolio_snapshot",
                payload={
                    "realized_pnl": str(self._broker.realized_pnl),
                    "current_equity": str(current_equity),
                    "current_pnl": str(current_pnl),
                },
                event_time=feature_snapshot.timestamp,
            )

        return RunnerCycleResult(
            market_snapshot=snapshot,
            feature_snapshot=feature_snapshot,
            signal=signal,
            risk_decision=risk_decision,
            execution_result=execution_result,
            current_position=current_position,
            current_pnl=current_pnl,
        )

    def run(
        self,
        snapshots: Iterable[MarketSnapshot],
        *,
        iterations: int | None = None,
        interval_seconds: float | None = None,
    ) -> list[RunnerCycleResult]:
        """Run the strategy loop over market snapshots for N iterations or until exhausted."""

        results: list[RunnerCycleResult] = []
        sleep_seconds = interval_seconds or 0.0

        for iteration, snapshot in enumerate(snapshots, start=1):
            if iterations is not None and iteration > iterations:
                break
            results.append(self.process_snapshot(snapshot))
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

        return results
