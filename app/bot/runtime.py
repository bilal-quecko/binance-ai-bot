"""Live paper-bot runtime management for one Binance Spot symbol."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4
from typing import Literal

from app.analysis import TechnicalAnalysisService, TechnicalAnalysisSnapshot
from app.analysis.market_sentiment import MarketSentimentService, MarketSentimentSnapshot
from app.ai.evaluation import AIOutcomeEvaluator
from app.ai.models import AISignalSnapshot
from app.ai.service import AISignalService
from app.config import Settings
from app.data import MarketContextService
from app.execution.execution_engine import ExecutionEngine
from app.exchange.binance_ws import BinanceWebSocketClient
from app.features.feature_store import FeatureEngine
from app.features.models import FeatureSnapshot
from app.features.models import FeatureConfig
from app.market_data.candles import Candle
from app.market_data.stream_manager import StreamManager
from app.market_data.models import MarketSnapshot
from app.monitoring.profile_calibration import PROFILE_THRESHOLDS
from app.paper.broker import PaperBroker
from app.paper.models import Position
from app.risk.limits import RiskEngine
from app.runner import RunnerConfig, StrategyRunner, TradingProfile
from app.runner.models import ManualTradeResult, RunnerCycleResult, TradeReadiness
from app.storage import StorageRepository
from app.storage.models import PaperBrokerStateRecord, ProfileTuningSetRecord
from app.strategies.models import StrategySignal
from app.strategies.models import TrendFollowingConfig
from app.strategies.trend_following import TrendFollowingStrategy


BotState = Literal["stopped", "running", "paused", "error"]
BotMode = Literal["auto_paper", "paused", "stopped", "error"]
PersistenceState = Literal[
    "healthy",
    "degraded_in_memory_only",
    "recovered_from_persistence",
    "unavailable",
]


@dataclass(slots=True)
class BotStatus:
    """Current runtime status for the paper bot."""

    state: BotState = "stopped"
    mode: BotMode = "stopped"
    symbol: str | None = None
    timeframe: str = "1m"
    paper_only: bool = True
    session_id: str | None = None
    started_at: datetime | None = None
    last_event_time: datetime | None = None
    last_error: str | None = None
    recovered_from_prior_session: bool = False
    broker_state_restored: bool = False
    recovery_message: str | None = None
    trading_profile: TradingProfile = "balanced"
    tuning_version_id: str | None = None
    baseline_tuning_version_id: str | None = None


@dataclass(slots=True)
class WorkstationState:
    """Current symbol-scoped workstation state for the frontend."""

    symbol: str
    is_runtime_symbol: bool
    market_snapshot: MarketSnapshot | None
    feature_snapshot: FeatureSnapshot | None
    ai_signal: AISignalSnapshot | None
    trade_readiness: TradeReadiness | None
    entry_signal: StrategySignal | None
    exit_signal: StrategySignal | None
    current_position: Position | None
    last_cycle_result: RunnerCycleResult | None
    total_pnl: Decimal
    realized_pnl: Decimal
    recovery_message: str | None = None


class PaperBotRuntime:
    """Manage one live Binance Spot market-data loop feeding the paper runner."""

    def __init__(
        self,
        *,
        settings: Settings,
        websocket_client: BinanceWebSocketClient,
        logger: logging.Logger | None = None,
        stream_manager: StreamManager | None = None,
    ) -> None:
        self._settings = settings
        self._websocket_client = websocket_client
        self._logger = logger or logging.getLogger(__name__)
        self._stream_manager = stream_manager or StreamManager(websocket_client=websocket_client)
        self._ai_signal_service = AISignalService()
        self._market_sentiment_service = MarketSentimentService()
        self._technical_analysis_service = TechnicalAnalysisService()
        self._task: asyncio.Task[None] | None = None
        self._runner: StrategyRunner | None = None
        self._storage_repository = StorageRepository(self._settings.database_url)
        self._status = BotStatus(timeframe=self._default_timeframe())
        self._lock = asyncio.Lock()
        self._last_processed_candle_open_time: dict[str, datetime] = {}
        self._persistence_last_ok_at: datetime | None = None
        self._restore_from_storage()

    def _default_timeframe(self) -> str:
        """Return the primary runner timeframe."""

        return self._settings.timeframe_list[0] if self._settings.timeframe_list else "1m"

    def status(self) -> BotStatus:
        """Return a copy of the current runtime status."""

        return BotStatus(
            state=self._status.state,
            mode=self._status.mode,
            symbol=self._status.symbol,
            timeframe=self._status.timeframe,
            paper_only=self._status.paper_only,
            session_id=self._status.session_id,
            started_at=self._status.started_at,
            last_event_time=self._status.last_event_time,
            last_error=self._status.last_error,
            recovered_from_prior_session=self._status.recovered_from_prior_session,
            broker_state_restored=self._status.broker_state_restored,
            recovery_message=self._status.recovery_message,
            trading_profile=self._status.trading_profile,
            tuning_version_id=self._status.tuning_version_id,
            baseline_tuning_version_id=self._status.baseline_tuning_version_id,
        )

    def storage_degraded(self) -> bool:
        """Return whether optional workstation storage is currently degraded."""

        return bool(
            self._storage_repository is not None
            and self._storage_repository.optional_storage_degraded
        )

    def storage_status_message(self) -> str | None:
        """Return the latest optional storage degradation message, if any."""

        if self._storage_repository is None:
            return None
        return self._storage_repository.optional_storage_message

    def persistence_last_ok_at(self) -> datetime | None:
        """Return the latest successful persistence timestamp, if known."""

        return self._persistence_last_ok_at

    def persistence_recovery_source(self) -> str | None:
        """Return the recovery source label for the current session, if any."""

        if self._status.recovered_from_prior_session and self._status.broker_state_restored:
            return "sqlite_runtime_session+paper_broker_state"
        if self._status.recovered_from_prior_session:
            return "sqlite_runtime_session"
        if self._status.broker_state_restored:
            return "sqlite_paper_broker_state"
        return None

    def persistence_state(self) -> PersistenceState:
        """Return the current persistence-health state for the workstation."""

        has_recovered_state = self._status.recovered_from_prior_session or self._status.broker_state_restored
        runtime_active = self._status.state in {"running", "paused"}
        if self.storage_degraded():
            if runtime_active or has_recovered_state:
                return "degraded_in_memory_only"
            return "unavailable"
        if has_recovered_state:
            return "recovered_from_persistence"
        return "healthy"

    def persistence_status_message(self) -> str:
        """Return a user-readable persistence-health explanation."""

        state = self.persistence_state()
        if state == "degraded_in_memory_only":
            return self.storage_status_message() or (
                "Persistence is degraded. The paper runtime is still active, but current state is only safe in memory."
            )
        if state == "recovered_from_persistence":
            return self._status.recovery_message or (
                "Recovered prior runtime and broker state from persisted storage. Review the restored session before resuming."
            )
        if state == "unavailable":
            return self.storage_status_message() or (
                "Persistence is unavailable. No recoverable session state is currently available."
            )
        return "Runtime state and paper broker state are persisting normally."

    def _mark_persistence_ok(self) -> None:
        """Record the latest successful persistence timestamp."""

        self._persistence_last_ok_at = datetime.now(tz=UTC)

    def _reset_runtime_state(self) -> None:
        """Reset in-memory runtime state after stop/reset."""

        self._runner = None
        self._last_processed_candle_open_time = {}

    def _persist_runtime_state(self) -> None:
        """Persist backend-owned runtime session state for restart recovery."""

        try:
            self._storage_repository.upsert_runtime_session_state(
                state=self._status.state,
                mode=self._status.mode,
                symbol=self._status.symbol,
                session_id=self._status.session_id,
                started_at=self._status.started_at,
                last_event_time=self._status.last_event_time,
                last_error=self._status.last_error,
                trading_profile=self._status.trading_profile,
                tuning_version_id=self._status.tuning_version_id,
                baseline_tuning_version_id=self._status.baseline_tuning_version_id,
            )
            self._mark_persistence_ok()
        except Exception:
            self._storage_repository.record_persistence_warning(
                "Persistence is temporarily unavailable. Live paper state is still running in memory."
            )
            self._logger.exception("Failed to persist runtime session state.")

    def _persist_broker_state(self) -> None:
        """Persist paper broker balances and positions for restart recovery."""

        if self._runner is None:
            return
        try:
            self._storage_repository.upsert_paper_broker_state(
                balances=self._runner.get_balances(),
                positions=self._runner.get_open_positions(),
                realized_pnl=self._runner.realized_pnl(),
                snapshot_time=datetime.now(tz=UTC),
            )
            self._mark_persistence_ok()
        except Exception:
            self._storage_repository.record_persistence_warning(
                "Paper broker persistence is temporarily unavailable. Open paper positions remain active in memory."
            )
            self._logger.exception("Failed to persist paper broker state.")

    def _build_broker_from_state(self, state: PaperBrokerStateRecord) -> PaperBroker:
        """Build an in-memory paper broker from persisted recovery state."""

        positions = {
            position.symbol: Position(
                symbol=position.symbol,
                quantity=position.quantity,
                avg_entry_price=position.avg_entry_price,
                quote_asset=position.quote_asset,
                realized_pnl=position.realized_pnl,
            )
            for position in state.positions
        }
        return PaperBroker(
            initial_balances=state.balances,
            initial_positions=positions,
            initial_realized_pnl=state.realized_pnl,
        )

    def _restore_from_storage(self) -> None:
        """Restore persisted runtime session and broker state on backend startup."""

        session_state = self._storage_repository.get_runtime_session_state()
        broker_state = self._storage_repository.get_paper_broker_state()
        if broker_state is not None:
            self._runner = self._build_runner(broker=self._build_broker_from_state(broker_state))

        if session_state is None:
            return

        restored_state = session_state.state
        restored_mode = session_state.mode
        recovery_message = None
        if restored_state in {"running", "paused"}:
            restored_state = "paused"
            restored_mode = "paused"
            recovery_message = (
                "Recovered a prior paper session after backend restart. Manual resume is required before auto trading continues."
            )
        self._status = BotStatus(
            state=restored_state,  # type: ignore[arg-type]
            mode=restored_mode,  # type: ignore[arg-type]
            symbol=session_state.symbol,
            timeframe=self._default_timeframe(),
            paper_only=True,
            session_id=session_state.session_id,
            started_at=session_state.started_at,
            last_event_time=session_state.last_event_time,
            last_error=session_state.last_error,
            recovered_from_prior_session=True,
            broker_state_restored=broker_state is not None,
            recovery_message=recovery_message,
            trading_profile=session_state.trading_profile,
            tuning_version_id=session_state.tuning_version_id,
            baseline_tuning_version_id=session_state.baseline_tuning_version_id,
        )
        if self._runner is not None:
            restored_thresholds = self._thresholds_for_version(
                profile=self._status.trading_profile,
                version_id=self._status.tuning_version_id,
            )
            self._runner.update_profile(
                strategy_config=self._strategy_config_for_profile(
                    self._status.trading_profile,
                    thresholds=restored_thresholds,
                ),
                runner_config=self._runner_config_for_profile(
                    self._status.trading_profile,
                    thresholds=restored_thresholds,
                ),
            )
        self._persist_runtime_state()

    def _broker_has_recovered_state(self) -> bool:
        """Return whether the current runner holds recovered paper broker state."""

        if self._runner is None:
            return False
        return bool(self._runner.get_open_positions())

    def _base_tuning_thresholds(self, profile: TradingProfile) -> dict[str, Decimal]:
        """Return the default tunable thresholds for one profile."""

        return dict(PROFILE_THRESHOLDS[profile])

    def _load_tuning_thresholds(
        self,
        *,
        profile: TradingProfile,
        config_json: str | None,
    ) -> dict[str, Decimal]:
        """Return profile tuning thresholds merged onto the built-in defaults."""

        thresholds = self._base_tuning_thresholds(profile)
        if not config_json:
            return thresholds
        try:
            raw_config = json.loads(config_json)
        except json.JSONDecodeError:
            self._logger.warning("Ignoring invalid tuning config for profile %s.", profile)
            return thresholds
        if not isinstance(raw_config, dict):
            return thresholds
        for key in thresholds:
            value = raw_config.get(key)
            if value is None:
                continue
            try:
                thresholds[key] = Decimal(str(value))
            except Exception:  # pragma: no cover - defensive config parsing
                self._logger.warning("Ignoring invalid tuning threshold %s=%r.", key, value)
        return thresholds

    def _resolve_active_tuning(
        self,
        *,
        symbol: str,
        profile: TradingProfile,
    ) -> tuple[dict[str, Decimal], str | None, str | None]:
        """Return thresholds and version ids for the next paper session."""

        pending = self._storage_repository.get_latest_profile_tuning_set(
            symbol=symbol,
            profile=profile,
            status="pending",
        )
        active_tuning = pending
        if pending is not None:
            applied_at = datetime.now(tz=UTC)
            self._storage_repository.mark_profile_tuning_applied(
                pending.version_id,
                applied_at=applied_at,
            )
            active_tuning = ProfileTuningSetRecord(
                version_id=pending.version_id,
                symbol=pending.symbol,
                profile=pending.profile,
                status="applied",
                config_json=pending.config_json,
                baseline_config_json=pending.baseline_config_json,
                created_at=pending.created_at,
                applied_at=applied_at,
                baseline_version_id=pending.baseline_version_id,
                reason=pending.reason,
            )
        if active_tuning is None:
            active_tuning = self._storage_repository.get_latest_profile_tuning_set(
                symbol=symbol,
                profile=profile,
                status="applied",
            )
        if active_tuning is None:
            return self._base_tuning_thresholds(profile), None, None
        return (
            self._load_tuning_thresholds(
                profile=profile,
                config_json=active_tuning.config_json,
            ),
            active_tuning.version_id,
            active_tuning.baseline_version_id,
        )

    def _thresholds_for_version(
        self,
        *,
        profile: TradingProfile,
        version_id: str | None,
    ) -> dict[str, Decimal]:
        """Return thresholds for one persisted tuning version."""

        if version_id is None:
            return self._base_tuning_thresholds(profile)
        tuning_set = self._storage_repository.get_profile_tuning_set_by_version(version_id)
        if tuning_set is None:
            return self._base_tuning_thresholds(profile)
        return self._load_tuning_thresholds(
            profile=profile,
            config_json=tuning_set.config_json,
        )

    def _strategy_config_for_profile(
        self,
        profile: TradingProfile,
        *,
        thresholds: dict[str, Decimal] | None = None,
    ) -> TrendFollowingConfig:
        """Return deterministic strategy thresholds for one trading profile."""

        resolved_thresholds = thresholds or self._base_tuning_thresholds(profile)
        if profile == "conservative":
            return TrendFollowingConfig(
                min_atr_ratio=resolved_thresholds["min_atr_ratio"],
                max_atr_ratio=Decimal("0.0300"),
                max_spread_ratio=resolved_thresholds["max_spread_ratio"],
                min_order_book_imbalance=resolved_thresholds["min_order_book_imbalance"],
                stop_loss_atr_multiple=resolved_thresholds["stop_loss_atr_multiple"],
                take_profit_atr_multiple=resolved_thresholds["take_profit_atr_multiple"],
            )
        if profile == "aggressive":
            return TrendFollowingConfig(
                min_atr_ratio=resolved_thresholds["min_atr_ratio"],
                max_atr_ratio=Decimal("0.0600"),
                max_spread_ratio=resolved_thresholds["max_spread_ratio"],
                min_order_book_imbalance=resolved_thresholds["min_order_book_imbalance"],
                stop_loss_atr_multiple=resolved_thresholds["stop_loss_atr_multiple"],
                take_profit_atr_multiple=resolved_thresholds["take_profit_atr_multiple"],
            )
        return TrendFollowingConfig(
            min_atr_ratio=resolved_thresholds["min_atr_ratio"],
            max_atr_ratio=Decimal("0.0400"),
            max_spread_ratio=resolved_thresholds["max_spread_ratio"],
            min_order_book_imbalance=resolved_thresholds["min_order_book_imbalance"],
            stop_loss_atr_multiple=resolved_thresholds["stop_loss_atr_multiple"],
            take_profit_atr_multiple=resolved_thresholds["take_profit_atr_multiple"],
        )

    def _runner_config_for_profile(
        self,
        profile: TradingProfile,
        *,
        thresholds: dict[str, Decimal] | None = None,
    ) -> RunnerConfig:
        """Return runner/risk tuning for one paper-trading profile."""

        resolved_thresholds = thresholds or self._base_tuning_thresholds(profile)
        risk_per_trade = Decimal(str(self._settings.risk_per_trade))
        if profile == "conservative":
            risk_per_trade = min(risk_per_trade, Decimal("0.0040"))
        elif profile == "aggressive":
            risk_per_trade = max(risk_per_trade, Decimal("0.0075"))

        return RunnerConfig(
            order_quantity=Decimal("1"),
            stop_atr_multiple=resolved_thresholds["stop_loss_atr_multiple"],
            risk_per_trade=risk_per_trade,
            max_daily_loss=Decimal(str(self._settings.max_daily_loss)),
            max_open_positions=self._settings.max_open_positions,
            min_stop_distance_ratio=resolved_thresholds["min_stop_distance_ratio"],
            min_expected_edge_buffer_pct=resolved_thresholds["min_expected_edge_buffer_pct"],
            trading_profile=profile,
            session_id=self._status.session_id,
            tuning_version_id=self._status.tuning_version_id,
        )

    def workstation_state(self, symbol: str) -> WorkstationState:
        """Return the current workstation view for a symbol."""

        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol or self._runner is None or self._status.symbol != normalized_symbol:
            return WorkstationState(
                symbol=normalized_symbol,
                is_runtime_symbol=False,
                market_snapshot=None,
                feature_snapshot=None,
                ai_signal=None,
                trade_readiness=None,
                entry_signal=None,
                exit_signal=None,
                current_position=None,
                last_cycle_result=None,
                total_pnl=Decimal("0"),
                realized_pnl=Decimal("0"),
                recovery_message=self._status.recovery_message,
            )

        feature_snapshot = self._runner.get_feature_snapshot(normalized_symbol)
        try:
            ai_signal = self._persist_ai_signal_if_needed(normalized_symbol, feature_snapshot)
        except Exception:
            self._logger.exception(
                "Failed to build or persist AI signal for workstation symbol %s.",
                normalized_symbol,
            )
            ai_signal = None

        return WorkstationState(
            symbol=normalized_symbol,
            is_runtime_symbol=True,
            market_snapshot=self._runner.get_latest_market_snapshot(normalized_symbol),
            feature_snapshot=feature_snapshot,
            ai_signal=ai_signal,
            trade_readiness=self._runner.preview_trade_readiness(
                normalized_symbol,
                runtime_active=self._status.state in {"running", "paused"},
                mode=self._status.mode,
            ),
            entry_signal=self._runner.preview_entry_signal(normalized_symbol),
            exit_signal=self._runner.preview_exit_signal(normalized_symbol),
            current_position=self._runner.get_current_position(normalized_symbol),
            last_cycle_result=self._runner.get_last_cycle_result(normalized_symbol),
            total_pnl=self._runner.current_pnl(),
            realized_pnl=self._runner.realized_pnl(),
            recovery_message=self._status.recovery_message,
        )

    def technical_analysis(self, symbol: str) -> TechnicalAnalysisSnapshot | None:
        """Return the current technical analysis for one symbol."""

        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol or self._runner is None or self._status.symbol != normalized_symbol:
            return None
        return self._technical_analysis_service.analyze(
            symbol=normalized_symbol,
            candles=self._runner.get_candle_history(normalized_symbol),
            feature_snapshot=self._runner.get_feature_snapshot(normalized_symbol),
        )

    def candle_history(self, symbol: str) -> list[Candle]:
        """Return recent live candle history for one symbol."""

        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol or self._runner is None:
            return []
        return self._runner.get_candle_history(normalized_symbol)

    def _build_ai_signal(
        self,
        symbol: str,
        feature_snapshot: FeatureSnapshot | None,
    ) -> AISignalSnapshot | None:
        """Build an AI advisory snapshot from the current runner cache."""

        if self._runner is None or feature_snapshot is None:
            return None
        candles = self._runner.get_candle_history(symbol)
        if not candles:
            return None
        technical_analysis = self._technical_analysis_service.analyze(
            symbol=symbol,
            candles=candles,
            feature_snapshot=feature_snapshot,
        )
        market_sentiment = self._build_market_sentiment(symbol)
        recent_false_positive_rate_5m = None
        recent_false_reversal_rate_5m = None
        if self._storage_repository is not None:
            evaluation = AIOutcomeEvaluator(self._storage_repository).evaluate(symbol=symbol)
            summary_5m = next(
                (summary for summary in evaluation.horizons if summary.horizon == "5m"),
                None,
            )
            if summary_5m is not None and summary_5m.sample_size > 0:
                recent_false_positive_rate_5m = summary_5m.false_positive_rate_pct
                recent_false_reversal_rate_5m = summary_5m.false_reversal_rate_pct
        return self._ai_signal_service.build_signal(
            symbol=symbol,
            candles=candles,
            feature_snapshot=feature_snapshot,
            top_of_book=self._runner.get_top_of_book(symbol),
            technical_analysis=technical_analysis,
            market_sentiment=market_sentiment,
            recent_false_positive_rate_5m=recent_false_positive_rate_5m,
            recent_false_reversal_rate_5m=recent_false_reversal_rate_5m,
        )

    def _build_market_sentiment(self, symbol: str) -> MarketSentimentSnapshot | None:
        """Build broader-market sentiment from persisted and live market context."""

        if self._storage_repository is None:
            return None
        symbol_points = MarketContextService(
            repository=self._storage_repository,
            runtime=self,
        ).load_market_context(selected_symbol=symbol)
        return self._market_sentiment_service.analyze(
            symbol=symbol,
            symbol_points=symbol_points,
        )

    def _persist_ai_signal_if_needed(
        self,
        symbol: str,
        feature_snapshot: FeatureSnapshot | None,
    ) -> AISignalSnapshot | None:
        """Persist a materially changed AI advisory snapshot for the active symbol."""

        ai_signal = self._build_ai_signal(symbol, feature_snapshot)
        if ai_signal is None or self._storage_repository is None:
            return ai_signal
        try:
            was_inserted = self._storage_repository.insert_ai_signal_snapshot(ai_signal)
            if was_inserted:
                self._mark_persistence_ok()
                self._storage_repository.insert_event(
                    event_type="ai_signal_snapshot",
                    symbol=symbol,
                    message=f"bias={ai_signal.bias} action={ai_signal.suggested_action}",
                    payload={
                        "bias": ai_signal.bias,
                        "confidence": ai_signal.confidence,
                        "entry_signal": ai_signal.entry_signal,
                        "exit_signal": ai_signal.exit_signal,
                        "suggested_action": ai_signal.suggested_action,
                    },
                    event_time=ai_signal.feature_vector.timestamp,
                )
        except Exception:
            self._storage_repository.record_persistence_warning(
                "AI advisory persistence is temporarily unavailable. Live analysis remains available in memory."
            )
            self._logger.exception("Failed to persist AI signal snapshot for %s.", symbol)
        return ai_signal

    def _build_streams(self, symbol: str, timeframe: str) -> list[str]:
        """Build required Binance Spot market-data streams for one symbol."""

        normalized_symbol = symbol.lower()
        return [
            f"{normalized_symbol}@kline_{timeframe}",
            f"{normalized_symbol}@bookTicker",
            f"{normalized_symbol}@aggTrade",
        ]

    def _build_runner(
        self,
        broker: PaperBroker | None = None,
        *,
        thresholds: dict[str, Decimal] | None = None,
    ) -> StrategyRunner:
        """Construct a fresh paper-only strategy runner."""

        runtime_broker = broker or PaperBroker(initial_balances={"USDT": Decimal("10000")})
        execution_engine = ExecutionEngine(runtime_broker)
        feature_engine = FeatureEngine(
            FeatureConfig(
                ema_fast_period=3,
                ema_slow_period=5,
                rsi_period=3,
                atr_period=3,
            )
        )
        strategy = TrendFollowingStrategy(
            self._strategy_config_for_profile(
                self._status.trading_profile,
                thresholds=thresholds,
            )
        )
        risk_engine = RiskEngine()
        return StrategyRunner(
            feature_engine=feature_engine,
            strategy=strategy,
            risk_engine=risk_engine,
            execution_engine=execution_engine,
            broker=runtime_broker,
            storage_repository=self._storage_repository,
            config=self._runner_config_for_profile(
                self._status.trading_profile,
                thresholds=thresholds,
            ),
        )

    async def _run(self, symbol: str, timeframe: str) -> None:
        """Background task that ingests live Binance snapshots into the paper runner."""

        assert self._runner is not None

        try:
            async for snapshot in self._stream_manager.stream(
                self._build_streams(symbol, timeframe),
                websocket_client=self._websocket_client,
            ):
                self._status.last_event_time = snapshot.event_time or snapshot.received_at
                self._persist_runtime_state()
                self._runner.ingest_snapshot(snapshot)

                if self._status.state == "paused":
                    continue
                if snapshot.symbol.upper() != symbol:
                    continue
                if snapshot.candle is None or not snapshot.candle.is_closed:
                    continue
                if self._storage_repository is not None:
                    try:
                        self._storage_repository.insert_market_candle_snapshot(snapshot.candle)
                        self._mark_persistence_ok()
                    except Exception:
                        self._storage_repository.record_persistence_warning(
                            "Candle history persistence is temporarily unavailable. Live paper logic continues in memory."
                        )
                        self._logger.exception(
                            "Failed to persist market candle snapshot for %s.",
                            snapshot.candle.symbol,
                        )
                last_processed_open_time = self._last_processed_candle_open_time.get(symbol)
                if (
                    last_processed_open_time is not None
                    and snapshot.candle.open_time <= last_processed_open_time
                ):
                    self._logger.info(
                        "ignoring duplicate or out-of-order closed candle | symbol=%s open_time=%s last_processed=%s",
                        symbol,
                        snapshot.candle.open_time.isoformat(),
                        last_processed_open_time.isoformat(),
                    )
                    continue

                cycle_result = self._runner.process_snapshot(snapshot)
                if cycle_result is not None:
                    self._persist_ai_signal_if_needed(symbol, cycle_result.feature_snapshot)
                    self._persist_broker_state()
                self._last_processed_candle_open_time[symbol] = snapshot.candle.open_time
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive production path
            self._status.state = "error"
            self._status.mode = "error"
            self._status.last_error = str(exc)
            self._logger.exception("paper bot runtime failed")
        finally:
            self._task = None
            if self._status.state != "error":
                self._status.state = "stopped"
                self._status.mode = "stopped"
            if self._status.session_id is not None:
                self._storage_repository.finish_paper_session_run(
                    session_id=self._status.session_id,
                    ended_at=datetime.now(tz=UTC),
                )
            self._persist_runtime_state()

    async def start(self, symbol: str, trading_profile: TradingProfile = "balanced") -> BotStatus:
        """Start live paper trading for a single Spot symbol."""

        if self._settings.app_mode != "paper":
            raise RuntimeError("The live paper bot runtime is available only in paper mode.")

        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("A symbol is required to start the paper bot.")

        async with self._lock:
            if self._task is not None and not self._task.done():
                raise RuntimeError("The paper bot is already running. Stop it before starting a new symbol.")

            tuning_thresholds, tuning_version_id, baseline_tuning_version_id = self._resolve_active_tuning(
                symbol=normalized_symbol,
                profile=trading_profile,
            )

            self._status = BotStatus(
                state="running",
                mode="auto_paper",
                symbol=normalized_symbol,
                timeframe=self._default_timeframe(),
                paper_only=True,
                session_id=uuid4().hex,
                started_at=datetime.now(tz=UTC),
                last_error=None,
                recovered_from_prior_session=False,
                broker_state_restored=self._broker_has_recovered_state(),
                recovery_message=None,
                trading_profile=trading_profile,
                tuning_version_id=tuning_version_id,
                baseline_tuning_version_id=baseline_tuning_version_id,
            )
            if self._runner is None:
                try:
                    self._runner = self._build_runner(thresholds=tuning_thresholds)
                except TypeError:
                    self._runner = self._build_runner()
            else:
                self._runner.update_profile(
                    strategy_config=self._strategy_config_for_profile(
                        trading_profile,
                        thresholds=tuning_thresholds,
                    ),
                    runner_config=self._runner_config_for_profile(
                        trading_profile,
                        thresholds=tuning_thresholds,
                    ),
                )
            self._last_processed_candle_open_time = {}
            self._persist_runtime_state()
            self._persist_broker_state()
            self._storage_repository.start_paper_session_run(
                session_id=self._status.session_id or uuid4().hex,
                symbol=normalized_symbol,
                trading_profile=trading_profile,
                tuning_version_id=tuning_version_id,
                baseline_tuning_version_id=baseline_tuning_version_id,
                started_at=self._status.started_at or datetime.now(tz=UTC),
            )
            self._task = asyncio.create_task(
                self._run(normalized_symbol, self._status.timeframe),
                name=f"paper-bot-{normalized_symbol.lower()}",
            )
            return self.status()

    async def stop(self) -> BotStatus:
        """Stop the live paper bot background task."""

        async with self._lock:
            task = self._task
            self._task = None
            if task is not None and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            self._status.state = "stopped"
            self._status.mode = "stopped"
            self._persist_runtime_state()
            self._persist_broker_state()
            if self._status.session_id is not None:
                self._storage_repository.finish_paper_session_run(
                    session_id=self._status.session_id,
                    ended_at=datetime.now(tz=UTC),
                )
            return self.status()

    async def pause(self) -> BotStatus:
        """Pause strategy processing while keeping market-data ingestion active."""

        async with self._lock:
            if self._task is None or self._task.done():
                raise RuntimeError("Cannot pause because the paper bot is not running.")
            self._status.state = "paused"
            self._status.mode = "paused"
            self._persist_runtime_state()
            return self.status()

    async def resume(self) -> BotStatus:
        """Resume strategy processing after a pause."""

        async with self._lock:
            if self._task is None or self._task.done():
                raise RuntimeError("Cannot resume because the paper bot is not running.")
            self._status.state = "running"
            self._status.mode = "auto_paper"
            self._persist_runtime_state()
            return self.status()

    async def close(self) -> None:
        """Stop any running task and release runtime resources."""

        await self.stop()
        self._storage_repository.close()

    async def reset_session(self) -> BotStatus:
        """Stop the runtime and clear symbol-specific session state."""

        await self.stop()
        self._reset_runtime_state()
        self._storage_repository.clear_runtime_session_state()
        self._storage_repository.clear_paper_broker_state()
        self._status = BotStatus(timeframe=self._default_timeframe())
        self._persist_runtime_state()
        return self.status()

    async def manual_buy_market(self, symbol: str) -> ManualTradeResult:
        """Execute a manual paper-market buy for the active symbol."""

        return await self._execute_manual_trade(symbol, action="buy_market", side="BUY")

    async def manual_close_position(self, symbol: str) -> ManualTradeResult:
        """Execute a manual paper close for the active symbol."""

        return await self._execute_manual_trade(symbol, action="close_position", side="SELL")

    async def _execute_manual_trade(
        self,
        symbol: str,
        *,
        action: str,
        side: str,
    ) -> ManualTradeResult:
        """Run a manual paper trade through the runner and execution engine."""

        normalized_symbol = symbol.strip().upper()
        async with self._lock:
            if not normalized_symbol:
                return ManualTradeResult(
                    symbol="",
                    action=action,  # type: ignore[arg-type]
                    requested_side=side,  # type: ignore[arg-type]
                    status="rejected",
                    message="Select a symbol before sending a manual paper trade.",
                    reason_codes=("MISSING_SYMBOL",),
                )
            if self._settings.app_mode != "paper":
                return ManualTradeResult(
                    symbol=normalized_symbol,
                    action=action,  # type: ignore[arg-type]
                    requested_side=side,  # type: ignore[arg-type]
                    status="rejected",
                    message="Manual paper trades are only available in paper mode.",
                    reason_codes=("PAPER_ONLY",),
                )
            if self._runner is None or self._status.symbol != normalized_symbol or self._status.state == "stopped":
                return ManualTradeResult(
                    symbol=normalized_symbol,
                    action=action,  # type: ignore[arg-type]
                    requested_side=side,  # type: ignore[arg-type]
                    status="rejected",
                    message=f"Start the live runtime for {normalized_symbol} before sending manual paper trades.",
                    reason_codes=("START_RUNTIME_FIRST",),
                )

            result = self._runner.execute_manual_trade(
                normalized_symbol,
                action=action,
                side=side,
            )
            self._persist_broker_state()
            return result
