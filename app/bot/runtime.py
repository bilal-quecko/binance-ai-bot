"""Live paper-bot runtime management for one Binance Spot symbol."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from app.ai import AISignalService, AISignalSnapshot
from app.config import Settings
from app.execution.execution_engine import ExecutionEngine
from app.exchange.binance_ws import BinanceWebSocketClient
from app.features.feature_store import FeatureEngine
from app.features.models import FeatureSnapshot
from app.features.models import FeatureConfig
from app.market_data.stream_manager import StreamManager
from app.market_data.models import MarketSnapshot
from app.paper.broker import PaperBroker
from app.paper.models import Position
from app.risk.limits import RiskEngine
from app.runner import RunnerConfig, StrategyRunner
from app.runner.models import RunnerCycleResult
from app.storage import StorageRepository
from app.strategies.models import StrategySignal
from app.strategies.models import TrendFollowingConfig
from app.strategies.trend_following import TrendFollowingStrategy


BotState = Literal["stopped", "running", "paused", "error"]


@dataclass(slots=True)
class BotStatus:
    """Current runtime status for the paper bot."""

    state: BotState = "stopped"
    symbol: str | None = None
    timeframe: str = "1m"
    paper_only: bool = True
    started_at: datetime | None = None
    last_event_time: datetime | None = None
    last_error: str | None = None


@dataclass(slots=True)
class WorkstationState:
    """Current symbol-scoped workstation state for the frontend."""

    symbol: str
    is_runtime_symbol: bool
    market_snapshot: MarketSnapshot | None
    feature_snapshot: FeatureSnapshot | None
    ai_signal: AISignalSnapshot | None
    entry_signal: StrategySignal | None
    exit_signal: StrategySignal | None
    current_position: Position | None
    last_cycle_result: RunnerCycleResult | None
    total_pnl: Decimal
    realized_pnl: Decimal


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
        self._task: asyncio.Task[None] | None = None
        self._runner: StrategyRunner | None = None
        self._storage_repository: StorageRepository | None = None
        self._status = BotStatus(timeframe=self._default_timeframe())
        self._lock = asyncio.Lock()
        self._last_processed_candle_open_time: dict[str, datetime] = {}

    def _default_timeframe(self) -> str:
        """Return the primary runner timeframe."""

        return self._settings.timeframe_list[0] if self._settings.timeframe_list else "1m"

    def status(self) -> BotStatus:
        """Return a copy of the current runtime status."""

        return BotStatus(
            state=self._status.state,
            symbol=self._status.symbol,
            timeframe=self._status.timeframe,
            paper_only=self._status.paper_only,
            started_at=self._status.started_at,
            last_event_time=self._status.last_event_time,
            last_error=self._status.last_error,
        )

    def _reset_runtime_state(self) -> None:
        """Reset in-memory runtime state after stop/reset."""

        self._runner = None
        self._storage_repository = None
        self._last_processed_candle_open_time = {}

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
                entry_signal=None,
                exit_signal=None,
                current_position=None,
                last_cycle_result=None,
                total_pnl=Decimal("0"),
                realized_pnl=Decimal("0"),
            )

        feature_snapshot = self._runner.get_feature_snapshot(normalized_symbol)
        ai_signal = self._persist_ai_signal_if_needed(normalized_symbol, feature_snapshot)

        return WorkstationState(
            symbol=normalized_symbol,
            is_runtime_symbol=True,
            market_snapshot=self._runner.get_latest_market_snapshot(normalized_symbol),
            feature_snapshot=feature_snapshot,
            ai_signal=ai_signal,
            entry_signal=self._runner.preview_entry_signal(normalized_symbol),
            exit_signal=self._runner.preview_exit_signal(normalized_symbol),
            current_position=self._runner.get_current_position(normalized_symbol),
            last_cycle_result=self._runner.get_last_cycle_result(normalized_symbol),
            total_pnl=self._runner.current_pnl(),
            realized_pnl=self._runner.realized_pnl(),
        )

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
        return self._ai_signal_service.build_signal(
            symbol=symbol,
            candles=candles,
            feature_snapshot=feature_snapshot,
            top_of_book=self._runner.get_top_of_book(symbol),
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
        was_inserted = self._storage_repository.insert_ai_signal_snapshot(ai_signal)
        if was_inserted:
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
        return ai_signal

    def _build_streams(self, symbol: str, timeframe: str) -> list[str]:
        """Build required Binance Spot market-data streams for one symbol."""

        normalized_symbol = symbol.lower()
        return [
            f"{normalized_symbol}@kline_{timeframe}",
            f"{normalized_symbol}@bookTicker",
            f"{normalized_symbol}@aggTrade",
        ]

    def _build_runner(self) -> StrategyRunner:
        """Construct a fresh paper-only strategy runner."""

        broker = PaperBroker(initial_balances={"USDT": Decimal("10000")})
        execution_engine = ExecutionEngine(broker)
        feature_engine = FeatureEngine(
            FeatureConfig(
                ema_fast_period=3,
                ema_slow_period=5,
                rsi_period=3,
                atr_period=3,
            )
        )
        strategy = TrendFollowingStrategy(TrendFollowingConfig())
        risk_engine = RiskEngine()
        self._storage_repository = StorageRepository(self._settings.database_url)
        return StrategyRunner(
            feature_engine=feature_engine,
            strategy=strategy,
            risk_engine=risk_engine,
            execution_engine=execution_engine,
            broker=broker,
            storage_repository=self._storage_repository,
            config=RunnerConfig(
                order_quantity=Decimal("1"),
                risk_per_trade=Decimal(str(self._settings.risk_per_trade)),
                max_daily_loss=Decimal(str(self._settings.max_daily_loss)),
                max_open_positions=self._settings.max_open_positions,
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
                self._runner.ingest_snapshot(snapshot)

                if self._status.state == "paused":
                    continue
                if snapshot.symbol.upper() != symbol:
                    continue
                if snapshot.candle is None or not snapshot.candle.is_closed:
                    continue
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
                self._last_processed_candle_open_time[symbol] = snapshot.candle.open_time
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive production path
            self._status.state = "error"
            self._status.last_error = str(exc)
            self._logger.exception("paper bot runtime failed")
        finally:
            if self._storage_repository is not None:
                self._storage_repository.close()
            self._reset_runtime_state()
            if self._status.state != "error":
                self._status.state = "stopped"

    async def start(self, symbol: str) -> BotStatus:
        """Start live paper trading for a single Spot symbol."""

        if self._settings.app_mode != "paper":
            raise RuntimeError("The live paper bot runtime is available only in paper mode.")

        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("A symbol is required to start the paper bot.")

        async with self._lock:
            if self._task is not None and not self._task.done():
                raise RuntimeError("The paper bot is already running. Stop it before starting a new symbol.")

            self._runner = self._build_runner()
            self._last_processed_candle_open_time = {}
            self._status = BotStatus(
                state="running",
                symbol=normalized_symbol,
                timeframe=self._default_timeframe(),
                paper_only=True,
                started_at=datetime.now(tz=UTC),
                last_error=None,
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
            return self.status()

    async def pause(self) -> BotStatus:
        """Pause strategy processing while keeping market-data ingestion active."""

        async with self._lock:
            if self._task is None or self._task.done():
                raise RuntimeError("Cannot pause because the paper bot is not running.")
            self._status.state = "paused"
            return self.status()

    async def resume(self) -> BotStatus:
        """Resume strategy processing after a pause."""

        async with self._lock:
            if self._task is None or self._task.done():
                raise RuntimeError("Cannot resume because the paper bot is not running.")
            self._status.state = "running"
            return self.status()

    async def close(self) -> None:
        """Stop any running task and release runtime resources."""

        await self.stop()

    async def reset_session(self) -> BotStatus:
        """Stop the runtime and clear symbol-specific session state."""

        await self.stop()
        self._reset_runtime_state()
        self._status = BotStatus(timeframe=self._default_timeframe())
        return self.status()
