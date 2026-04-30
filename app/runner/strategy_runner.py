"""Strategy runner orchestration."""

import logging
import time
from collections.abc import Iterable
from datetime import datetime
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
from app.runner.models import ManualTradeResult, RunnerConfig, RunnerCycleResult, TradeReadiness
from app.storage.repositories import StorageRepository
from app.strategies.models import StrategySignal, TrendFollowingConfig
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
        self._latest_market_snapshot_by_symbol: dict[str, MarketSnapshot] = {}
        self._last_cycle_result_by_symbol: dict[str, RunnerCycleResult] = {}
        self._day_start_equity: Decimal | None = None

    def _upsert_candle(self, symbol: str, candle: Candle) -> None:
        """Store candle history in ascending open_time order and ignore stale klines."""

        candles = self._candles_by_symbol.setdefault(symbol, [])
        if not candles:
            candles.append(candle)
            self._candles_by_symbol[symbol] = candles
            return

        latest_candle = candles[-1]
        if candle.open_time > latest_candle.open_time:
            candles.append(candle)
        elif candle.open_time == latest_candle.open_time:
            if candle.event_time >= latest_candle.event_time:
                candles[-1] = candle
        else:
            return

        self._candles_by_symbol[symbol] = candles[-self._config.history_limit :]

    def _record_snapshot(self, snapshot: MarketSnapshot) -> None:
        """Store the latest market state needed for feature generation and PnL."""

        symbol = snapshot.symbol.upper()
        current_snapshot = self._latest_market_snapshot_by_symbol.get(symbol)
        current_timestamp = (
            (current_snapshot.event_time or current_snapshot.received_at)
            if current_snapshot is not None
            else None
        )
        next_timestamp = snapshot.event_time or snapshot.received_at
        if current_timestamp is None or next_timestamp is None or next_timestamp >= current_timestamp:
            self._latest_market_snapshot_by_symbol[symbol] = snapshot
        if snapshot.candle is not None:
            self._upsert_candle(symbol, snapshot.candle)
            self._last_price_by_symbol[symbol] = snapshot.candle.close
        if snapshot.top_of_book is not None:
            self._top_of_book_by_symbol[symbol] = snapshot.top_of_book
            self._last_price_by_symbol[symbol] = (
                snapshot.top_of_book.bid_price + snapshot.top_of_book.ask_price
            ) / Decimal("2")
        elif snapshot.last_price is not None:
            self._last_price_by_symbol[symbol] = snapshot.last_price

    def ingest_snapshot(self, snapshot: MarketSnapshot) -> None:
        """Ingest market data into the runner cache without executing a cycle."""

        self._record_snapshot(snapshot)

    def get_latest_market_snapshot(self, symbol: str) -> MarketSnapshot | None:
        """Return the latest cached market snapshot for a symbol."""

        return self._latest_market_snapshot_by_symbol.get(symbol.upper())

    def get_candle_history(self, symbol: str) -> list[Candle]:
        """Return the cached candle history for a symbol."""

        return list(self._candles_by_symbol.get(symbol.upper(), []))

    def get_top_of_book(self, symbol: str) -> TopOfBook | None:
        """Return the latest top-of-book snapshot for a symbol."""

        return self._top_of_book_by_symbol.get(symbol.upper())

    def get_feature_snapshot(self, symbol: str) -> FeatureSnapshot | None:
        """Return the latest derived feature snapshot for a symbol when available."""

        normalized_symbol = symbol.upper()
        candles = self._candles_by_symbol.get(normalized_symbol, [])
        if len(candles) < max(self._feature_engine.config.ema_slow_period, self._feature_engine.config.atr_period):
            return None
        return self._build_feature_snapshot(normalized_symbol)

    def preview_entry_signal(self, symbol: str) -> StrategySignal | None:
        """Return the current entry-side strategy preview for a symbol."""

        feature_snapshot = self.get_feature_snapshot(symbol)
        if feature_snapshot is None:
            return None
        return self._strategy.evaluate(feature_snapshot, position=None)

    def preview_exit_signal(self, symbol: str) -> StrategySignal | None:
        """Return the current exit-side strategy preview for a symbol."""

        feature_snapshot = self.get_feature_snapshot(symbol)
        if feature_snapshot is None:
            return None
        position = self._broker.get_position(symbol.upper())
        if position is None or position.quantity <= Decimal("0"):
            return StrategySignal(
                symbol=symbol.upper(),
                side="HOLD",
                confidence=self._strategy.config.hold_confidence,
                reason_codes=("NO_POSITION",),
            )
        return self._strategy.evaluate(feature_snapshot, position=position)

    def preview_risk_decision(self, symbol: str) -> RiskDecision | None:
        """Return the current risk decision preview for the next actionable signal."""

        normalized_symbol = symbol.upper()
        feature_snapshot = self.get_feature_snapshot(normalized_symbol)
        if feature_snapshot is None:
            return None
        position = self._broker.get_position(normalized_symbol)
        actionable_signal = (
            self._strategy.evaluate(feature_snapshot, position=position)
            if position is not None and position.quantity > Decimal("0")
            else self._strategy.evaluate(feature_snapshot, position=None)
        )
        if actionable_signal.side not in {"BUY", "SELL"}:
            return None
        return self._risk_engine.evaluate(
            self._build_risk_input(feature_snapshot, actionable_signal, position)
        )

    def preview_trade_readiness(
        self,
        symbol: str,
        *,
        runtime_active: bool,
        mode: str,
    ) -> TradeReadiness:
        """Return deterministic trade-readiness state for one symbol."""

        normalized_symbol = symbol.upper()
        broker_ready = self._config.mode == "paper"
        if not runtime_active:
            return TradeReadiness(
                selected_symbol=normalized_symbol,
                runtime_active=False,
                mode=mode,
                trading_profile=self._config.trading_profile,
                enough_candle_history=False,
                deterministic_entry_signal=False,
                deterministic_exit_signal=False,
                risk_ready=False,
                risk_blocked=False,
                broker_ready=broker_ready,
                next_action="start_runtime",
                reason_if_not_trading=f"Start the live runtime for {normalized_symbol} before auto paper trading can act.",
                blocking_reasons=("Start the live runtime to receive live candles and order-book data.",),
                signal_reason_codes=(),
                risk_reason_codes=(),
            )

        feature_snapshot = self.get_feature_snapshot(normalized_symbol)
        if feature_snapshot is None:
            return TradeReadiness(
                selected_symbol=normalized_symbol,
                runtime_active=True,
                mode=mode,
                trading_profile=self._config.trading_profile,
                enough_candle_history=False,
                deterministic_entry_signal=False,
                deterministic_exit_signal=False,
                risk_ready=False,
                risk_blocked=False,
                broker_ready=broker_ready,
                next_action="wait_for_history",
                reason_if_not_trading=f"Waiting for enough closed candle history to build deterministic signals for {normalized_symbol}.",
                blocking_reasons=("Need more closed candles before deterministic entries and exits can activate.",),
                signal_reason_codes=(),
                risk_reason_codes=(),
            )

        position = self._broker.get_position(normalized_symbol)
        entry_signal = self._strategy.evaluate(feature_snapshot, position=None)
        exit_signal = self.preview_exit_signal(normalized_symbol)
        actionable_signal = (
            exit_signal
            if exit_signal is not None and exit_signal.side == "SELL"
            else entry_signal
        )
        risk_decision = None
        if actionable_signal.side in {"BUY", "SELL"}:
            risk_decision = self._risk_engine.evaluate(
                self._build_risk_input(feature_snapshot, actionable_signal, position)
            )

        deterministic_entry_signal = entry_signal.side == "BUY"
        deterministic_exit_signal = exit_signal is not None and exit_signal.side == "SELL"
        risk_ready = risk_decision is not None and risk_decision.decision in {"approve", "resize"}
        risk_blocked = risk_decision is not None and risk_decision.decision == "reject"
        signal_reason_codes = actionable_signal.reason_codes
        blocking_reasons: tuple[str, ...] = ()

        next_action = "wait"
        reason_if_not_trading: str | None = None
        if deterministic_exit_signal:
            if risk_ready and mode == "auto_paper":
                next_action = "exit"
            elif risk_blocked:
                next_action = "blocked"
                blocking_reasons = self._humanize_risk_reasons(risk_decision.reason_codes, normalized_symbol)
                reason_if_not_trading = blocking_reasons[0] if blocking_reasons else None
            else:
                next_action = "resume_auto_trade"
                blocking_reasons = ("An exit setup is active, but auto paper trading is paused.",)
                reason_if_not_trading = blocking_reasons[0]
        elif deterministic_entry_signal:
            if risk_ready and mode == "auto_paper":
                next_action = "enter"
            elif risk_blocked:
                next_action = "blocked"
                blocking_reasons = self._humanize_risk_reasons(risk_decision.reason_codes, normalized_symbol)
                reason_if_not_trading = blocking_reasons[0] if blocking_reasons else None
            else:
                next_action = "resume_auto_trade"
                blocking_reasons = ("An entry setup is active, but auto paper trading is paused.",)
                reason_if_not_trading = blocking_reasons[0]
        elif position is not None and position.quantity > Decimal("0"):
            next_action = "hold"
            blocking_reasons = self._humanize_signal_reasons(exit_signal.reason_codes if exit_signal is not None else ("POSITION_OPEN",))
            reason_if_not_trading = (
                blocking_reasons[0]
                if blocking_reasons
                else "A paper position is open, and deterministic exit conditions are not active yet."
            )
        else:
            next_action = "wait"
            blocking_reasons = self._humanize_signal_reasons(entry_signal.reason_codes)
            reason_if_not_trading = (
                blocking_reasons[0] if blocking_reasons else "Deterministic entry conditions are not active yet."
            )

        return TradeReadiness(
            selected_symbol=normalized_symbol,
            runtime_active=True,
            mode=mode,
            trading_profile=self._config.trading_profile,
            enough_candle_history=True,
            deterministic_entry_signal=deterministic_entry_signal,
            deterministic_exit_signal=deterministic_exit_signal,
            risk_ready=risk_ready,
            risk_blocked=risk_blocked,
            broker_ready=broker_ready,
            next_action=next_action,
            reason_if_not_trading=reason_if_not_trading,
            blocking_reasons=blocking_reasons,
            signal_reason_codes=signal_reason_codes,
            risk_reason_codes=risk_decision.reason_codes if risk_decision is not None else (),
            expected_edge_pct=risk_decision.expected_edge_pct if risk_decision is not None else None,
            estimated_round_trip_cost_pct=(
                risk_decision.estimated_round_trip_cost_pct if risk_decision is not None else None
            ),
        )

    def get_current_position(self, symbol: str) -> Position | None:
        """Return the current broker position for a symbol."""

        return self._broker.get_position(symbol.upper())

    def get_open_positions(self) -> dict[str, Position]:
        """Return all current broker positions for recovery snapshots."""

        return self._broker.positions()

    def get_balances(self) -> dict[str, Decimal]:
        """Return current broker balances for recovery snapshots."""

        return self._broker.balances()

    def get_last_cycle_result(self, symbol: str) -> RunnerCycleResult | None:
        """Return the latest processed cycle result for a symbol."""

        return self._last_cycle_result_by_symbol.get(symbol.upper())

    def update_profile(
        self,
        *,
        strategy_config: TrendFollowingConfig,
        runner_config: RunnerConfig,
    ) -> None:
        """Apply updated strategy and runner tuning without losing cached state."""

        self._strategy.config = strategy_config
        self._config = runner_config

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

    def current_pnl(self) -> Decimal:
        """Return the current marked-to-market PnL."""

        return self._current_pnl()

    def realized_pnl(self) -> Decimal:
        """Return the broker's cumulative realized PnL."""

        return self._broker.realized_pnl

    def _build_feature_snapshot(self, symbol: str) -> FeatureSnapshot:
        """Build a feature snapshot from cached candles and top-of-book data."""

        candles = self._candles_by_symbol.get(symbol, [])
        if not candles:
            raise ValueError(f"no candle history available for {symbol}")
        return self._feature_engine.build_snapshot(
            candles,
            top_of_book=self._top_of_book_by_symbol.get(symbol),
        )

    @staticmethod
    def _humanize_signal_reasons(reason_codes: tuple[str, ...]) -> tuple[str, ...]:
        """Return trader-facing explanations for strategy-side wait reasons."""

        messages: dict[str, str] = {
            "MISSING_EMA": "Need more candles before trend signals can activate.",
            "REGIME_NOT_TREND": "Trend is not confirmed yet.",
            "MISSING_ATR_CONTEXT": "Need more volatility context before entries can activate.",
            "VOL_TOO_LOW": "Price movement is too quiet to justify a paper entry yet.",
            "VOL_TOO_HIGH": "Volatility is unstable, so the setup stays on hold.",
            "MICROSTRUCTURE_UNHEALTHY": "Spread or order-book quality is not healthy enough yet.",
            "EMA_NOT_BULLISH": "Fast EMA is not clearly above the slow EMA yet.",
            "POSITION_OPEN": "An open paper position exists, so the bot is waiting for an exit setup.",
            "NO_POSITION": "No open position, so no exit setup exists.",
            "EMA_BEARISH_EXIT": "Fast EMA has crossed below the slow EMA, so an exit is active.",
            "STOP_LOSS_HIT": "Price has reached the stop-loss threshold for the open position.",
            "TAKE_PROFIT_HIT": "Price has reached the take-profit threshold for the open position.",
        }
        return tuple(messages.get(code, code.replace("_", " ").capitalize()) for code in reason_codes)

    @staticmethod
    def _humanize_risk_reasons(reason_codes: tuple[str, ...], symbol: str) -> tuple[str, ...]:
        """Return trader-facing explanations for risk-engine blocks."""

        messages: dict[str, str] = {
            "EDGE_BELOW_COSTS": f"Expected edge for {symbol} is still too small after fees and slippage.",
            "EXPECTED_EDGE_TOO_SMALL": "Projected reward is not strong enough for the current paper costs.",
            "DAILY_LOSS_LIMIT": "Daily loss protection is active, so new entries are blocked.",
            "OPEN_POSITION_LIMIT": "The configured open-position limit is already reached.",
            "STOP_DISTANCE_TOO_TIGHT": "The protective stop is too tight relative to current price movement.",
            "SIZE_BELOW_MINIMUM": "Risk sizing produced a quantity that is too small to execute.",
            "NO_POSITION_TO_EXIT": "No open position exists, so there is nothing to close.",
            "INVALID_STOP_OR_VOLATILITY": "Volatility context is still incomplete, so the order stays blocked.",
            "INVALID_ORDER_REQUEST": "The current paper order request is incomplete.",
            "INVALID_EQUITY_CONTEXT": "Paper account equity context is not ready yet.",
            "RESIZED_FOR_RISK": "Risk sizing reduced the order to fit the current risk budget.",
            "RESIZED_TO_POSITION": "Exit size was reduced to the current open position.",
        }
        return tuple(messages.get(code, code.replace("_", " ").capitalize()) for code in reason_codes)

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

        expected_edge_pct: Decimal | None = None
        if (
            signal.side == "BUY"
            and feature_snapshot.atr is not None
            and entry_price > Decimal("0")
            and hasattr(self._strategy, "config")
        ):
            take_profit_multiple = self._strategy.config.take_profit_atr_multiple
            expected_edge_pct = (
                (feature_snapshot.atr * take_profit_multiple) / entry_price
            )
        estimated_round_trip_cost_pct = (
            (self._broker.fee_rate * Decimal("2")) + (self._broker.slippage_pct * Decimal("2"))
        )

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
            expected_edge_pct=expected_edge_pct,
            estimated_round_trip_cost_pct=estimated_round_trip_cost_pct,
            min_expected_edge_buffer_pct=self._config.min_expected_edge_buffer_pct,
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
        enriched_payload = {
            **payload,
            "execution_source": str(payload.get("execution_source", "auto")),
            "trading_profile": self._config.trading_profile,
            "session_id": self._config.session_id,
            "tuning_version_id": self._config.tuning_version_id,
        }
        self._storage_repository.insert_event(
            event_type=event_type,
            symbol=symbol,
            message=message,
            payload=enriched_payload,
            event_time=event_time,
        )

    def _market_price_for_symbol(self, symbol: str, feature_snapshot: FeatureSnapshot | None) -> Decimal:
        """Return the best available paper market price for a symbol."""

        latest_market_snapshot = self.get_latest_market_snapshot(symbol)
        if feature_snapshot is not None and feature_snapshot.mid_price is not None:
            return feature_snapshot.mid_price
        if latest_market_snapshot is not None and latest_market_snapshot.last_price is not None:
            return latest_market_snapshot.last_price
        if feature_snapshot is not None and feature_snapshot.ema_fast is not None:
            return feature_snapshot.ema_fast
        return Decimal("0")

    def _persist_position_and_pnl(self, symbol: str, event_time: datetime) -> tuple[Position | None, Decimal]:
        """Persist the latest paper position and PnL state after an execution path."""

        current_position = self._broker.get_position(symbol)
        current_pnl = self._current_pnl()
        current_equity = self._current_equity()
        if self._storage_repository is not None:
            self._storage_repository.insert_position_snapshot(
                current_position,
                event_time,
                symbol,
            )
            self._storage_repository.insert_pnl_snapshot(
                snapshot_time=event_time,
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
                event_time=event_time,
            )
        return current_position, current_pnl

    def execute_manual_trade(
        self,
        symbol: str,
        *,
        action: str,
        side: str,
    ) -> ManualTradeResult:
        """Execute a manual paper trade through the existing execution pipeline."""

        normalized_symbol = symbol.upper()
        feature_snapshot = self.get_feature_snapshot(normalized_symbol)
        if feature_snapshot is None:
            return ManualTradeResult(
                symbol=normalized_symbol,
                action=action,  # type: ignore[arg-type]
                requested_side=side,  # type: ignore[arg-type]
                status="rejected",
                message="Need more candles before manual paper trading can use the safe execution path.",
                reason_codes=("WAITING_FOR_HISTORY",),
                current_position=self._broker.get_position(normalized_symbol),
                current_pnl=self._current_pnl(),
            )

        latest_market_snapshot = self.get_latest_market_snapshot(normalized_symbol)
        if latest_market_snapshot is None:
            return ManualTradeResult(
                symbol=normalized_symbol,
                action=action,  # type: ignore[arg-type]
                requested_side=side,  # type: ignore[arg-type]
                status="rejected",
                message="Waiting for a live market snapshot before paper execution can price the order.",
                reason_codes=("WAITING_FOR_LIVE_SNAPSHOT",),
                current_position=self._broker.get_position(normalized_symbol),
                current_pnl=self._current_pnl(),
            )

        existing_position = self._broker.get_position(normalized_symbol)
        signal = StrategySignal(
            symbol=normalized_symbol,
            side=side,  # type: ignore[arg-type]
            confidence=Decimal("1.00"),
            reason_codes=("MANUAL_PAPER_TRADE",),
        )
        risk_input = self._build_risk_input(feature_snapshot, signal, existing_position)
        risk_decision = self._risk_engine.evaluate(risk_input)
        event_time = feature_snapshot.timestamp
        market_price = self._market_price_for_symbol(normalized_symbol, feature_snapshot)
        order = OrderRequest(
            symbol=normalized_symbol,
            side=side,  # type: ignore[arg-type]
            quantity=risk_input.requested_quantity,
            market_price=market_price,
            timestamp=event_time,
            quote_asset=self._config.quote_asset,
            mode=self._config.mode,
        )
        execution_result = self._execution_engine.execute(order, risk_decision)
        self._persist_event(
            event_type="manual_trade_request",
            symbol=normalized_symbol,
            message=f"manual_action={action}",
            payload={
                "side": side,
                "risk_decision": risk_decision.decision,
                "reason_codes": risk_decision.reason_codes,
                "execution_source": "manual",
                "trading_profile": self._config.trading_profile,
                "session_id": self._config.session_id,
            },
            event_time=event_time,
        )
        if self._storage_repository is not None:
            self._storage_repository.insert_trade(
                fill_result=execution_result,
                risk_decision=risk_decision,
                approved_quantity=risk_decision.approved_quantity,
                event_time=event_time,
                execution_source="manual",
                trading_profile=self._config.trading_profile,
                session_id=self._config.session_id,
                tuning_version_id=self._config.tuning_version_id,
            )
            if execution_result.status == "executed":
                self._storage_repository.insert_fill(
                    execution_result,
                    event_time,
                    execution_source="manual",
                    trading_profile=self._config.trading_profile,
                    session_id=self._config.session_id,
                    tuning_version_id=self._config.tuning_version_id,
                )
            else:
                self._persist_event(
                    event_type="trade_blocked",
                    symbol=normalized_symbol,
                    message=f"blocked={(execution_result.reason_codes or risk_decision.reason_codes)[0]}",
                    payload={
                        "reason_codes": execution_result.reason_codes or risk_decision.reason_codes,
                        "execution_source": "manual",
                        "trading_profile": self._config.trading_profile,
                        "session_id": self._config.session_id,
                    },
                    event_time=event_time,
                )
        current_position, current_pnl = self._persist_position_and_pnl(normalized_symbol, event_time)
        self._last_cycle_result_by_symbol[normalized_symbol] = RunnerCycleResult(
            market_snapshot=latest_market_snapshot,
            feature_snapshot=feature_snapshot,
            signal=signal,
            risk_decision=risk_decision,
            execution_result=execution_result,
            current_position=current_position,
            current_pnl=current_pnl,
        )
        if execution_result.status == "executed":
            message = (
                "Manual paper buy executed."
                if side == "BUY"
                else "Manual paper close executed."
            )
        elif risk_decision.decision == "reject":
            humanized = self._humanize_risk_reasons(risk_decision.reason_codes, normalized_symbol)
            message = humanized[0] if humanized else "Manual paper trade was blocked."
        else:
            message = "Manual paper trade did not execute."
        return ManualTradeResult(
            symbol=normalized_symbol,
            action=action,  # type: ignore[arg-type]
            requested_side=side,  # type: ignore[arg-type]
            status=execution_result.status,
            message=message,
            reason_codes=execution_result.reason_codes or risk_decision.reason_codes,
            risk_decision=risk_decision,
            fill_result=execution_result,
            current_position=current_position,
            current_pnl=current_pnl,
        )

    def process_snapshot(self, snapshot: MarketSnapshot) -> RunnerCycleResult:
        """Process one market snapshot through feature, strategy, risk, and execution."""

        self._record_snapshot(snapshot)
        symbol = snapshot.symbol.upper()
        if self._storage_repository is not None and snapshot.candle is not None:
            self._storage_repository.insert_market_candle_snapshot(snapshot.candle)
            self._storage_repository.upsert_historical_candles(
                [snapshot.candle],
                source="live_runtime",
            )
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
                    execution_source="auto",
                    trading_profile=self._config.trading_profile,
                session_id=self._config.session_id,
                tuning_version_id=self._config.tuning_version_id,
            )
                if execution_result.status == "executed":
                    self._storage_repository.insert_fill(
                        execution_result,
                        feature_snapshot.timestamp,
                        execution_source="auto",
                        trading_profile=self._config.trading_profile,
                    session_id=self._config.session_id,
                    tuning_version_id=self._config.tuning_version_id,
                )
                    self._persist_event(
                        event_type="fill",
                        symbol=symbol,
                        message=f"fill_side={execution_result.side}",
                        payload={
                            "order_id": execution_result.order_id,
                            "fill_price": str(execution_result.fill_price),
                            "filled_quantity": str(execution_result.filled_quantity),
                            "realized_pnl": str(execution_result.realized_pnl),
                            "execution_source": "auto",
                            "trading_profile": self._config.trading_profile,
                            "session_id": self._config.session_id,
                        },
                        event_time=feature_snapshot.timestamp,
                    )
                else:
                    blocker_reasons = execution_result.reason_codes or risk_decision.reason_codes
                    if blocker_reasons:
                        self._persist_event(
                            event_type="trade_blocked",
                            symbol=symbol,
                            message=f"blocked={blocker_reasons[0]}",
                            payload={
                                "reason_codes": blocker_reasons,
                                "execution_source": "auto",
                                "trading_profile": self._config.trading_profile,
                                "session_id": self._config.session_id,
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
            blocker_reasons = signal.reason_codes or ("NON_ACTIONABLE_SIGNAL",)
            self._persist_event(
                event_type="trade_blocked",
                symbol=symbol,
                message=f"blocked={blocker_reasons[0]}",
                payload={
                    "reason_codes": blocker_reasons,
                    "execution_source": "auto",
                    "trading_profile": self._config.trading_profile,
                    "session_id": self._config.session_id,
                },
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

        result = RunnerCycleResult(
            market_snapshot=snapshot,
            feature_snapshot=feature_snapshot,
            signal=signal,
            risk_decision=risk_decision,
            execution_result=execution_result,
            current_position=current_position,
            current_pnl=current_pnl,
        )
        self._last_cycle_result_by_symbol[symbol] = result
        return result

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
