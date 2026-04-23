"""FastAPI endpoints for paper-bot symbol discovery and runtime control."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.analysis import (
    HorizonPatternAnalysisService,
    MarketSentimentSnapshot,
    MarketSentimentService,
    PatternAnalysisSnapshot,
    PatternPricePoint,
    SymbolSentimentSnapshot,
    SymbolSentimentService,
    TechnicalAnalysisSnapshot,
    TimeframeTechnicalSummary,
    merge_pattern_points,
    normalize_horizon,
)
from app.ai.evaluation import AIOutcomeEvaluator
from app.bot import BotStatus, PaperBotRuntime, WorkstationState
from app.bot.runtime import PersistenceState
from app.config import Settings, get_settings
from app.data import MarketContextService
from app.exchange.symbol_service import SpotSymbolRecord, SpotSymbolService
from app.fusion import FusionInputs, FusionSignalSnapshot, UnifiedSignalFusionEngine
from app.runner.models import TradeReadiness
from app.storage import StorageRepository
from app.storage.models import MarketCandleSnapshotRecord

router = APIRouter()
LOGGER = logging.getLogger(__name__)

DataState = Literal["ready", "waiting_for_runtime", "waiting_for_history", "degraded_storage"]


class PersistenceHealthResponse(BaseModel):
    """Serialized persistence-health state for the workstation."""

    persistence_state: PersistenceState
    persistence_message: str
    persistence_last_ok_at: datetime | None = None
    recovery_source: str | None = None


class SymbolResponse(BaseModel):
    """Serialized Spot symbol metadata."""

    symbol: str
    base_asset: str
    quote_asset: str
    status: str


class BotStartRequest(BaseModel):
    """Payload for starting the paper bot."""

    symbol: str = Field(min_length=1)


class BotStatusResponse(BaseModel):
    """Serialized paper-bot runtime status."""

    state: str
    mode: str
    symbol: str | None = None
    timeframe: str
    paper_only: bool
    session_id: str | None = None
    started_at: datetime | None = None
    last_event_time: datetime | None = None
    last_error: str | None = None
    recovered_from_prior_session: bool = False
    broker_state_restored: bool = False
    recovery_message: str | None = None
    persistence: PersistenceHealthResponse


class CandleSummaryResponse(BaseModel):
    """Serialized latest candle state."""

    timeframe: str
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    is_closed: bool


class TopOfBookResponse(BaseModel):
    """Serialized best bid/ask state."""

    bid_price: Decimal
    bid_quantity: Decimal
    ask_price: Decimal
    ask_quantity: Decimal
    event_time: datetime


class FeatureSummaryResponse(BaseModel):
    """Serialized feature state for the selected symbol."""

    regime: str | None = None
    ema_fast: Decimal | None = None
    ema_slow: Decimal | None = None
    atr: Decimal | None = None
    mid_price: Decimal | None = None
    bid_ask_spread: Decimal | None = None
    order_book_imbalance: Decimal | None = None
    timestamp: datetime | None = None


class SignalSummaryResponse(BaseModel):
    """Serialized entry or exit signal preview."""

    side: str
    confidence: Decimal
    reason_codes: tuple[str, ...]


class PositionSummaryResponse(BaseModel):
    """Serialized current paper position for the selected symbol."""

    symbol: str
    quantity: Decimal
    avg_entry_price: Decimal
    realized_pnl: Decimal
    quote_asset: str


class LastActionResponse(BaseModel):
    """Serialized latest action for the selected symbol."""

    signal_side: str
    signal_reasons: tuple[str, ...]
    execution_status: str | None = None
    execution_reasons: tuple[str, ...] = ()
    event_time: datetime


class AIFeatureResponse(BaseModel):
    """Serialized AI advisory feature vector."""

    candle_count: int
    close_price: Decimal
    volatility_pct: Decimal | None = None
    momentum: Decimal | None = None
    volume_change_pct: Decimal | None = None
    volume_spike_ratio: Decimal | None = None
    spread_ratio: Decimal | None = None
    microstructure_healthy: bool
    momentum_persistence: Decimal | None = None
    direction_flip_rate: Decimal | None = None
    structure_quality: Decimal | None = None
    recent_false_positive_rate_5m: Decimal | None = None


class AIHorizonResponse(BaseModel):
    """Serialized horizon-specific AI advisory view."""

    horizon: str
    bias: str
    confidence: int
    suggested_action: str
    abstain: bool = False
    confirmation_needed: bool = False
    explanation: str


class AISignalResponse(BaseModel):
    """Serialized AI advisory market read."""

    symbol: str
    timestamp: datetime
    bias: str
    confidence: int
    entry_signal: bool
    exit_signal: bool
    suggested_action: str
    regime: str = "insufficient_data"
    noise_level: str = "unknown"
    abstain: bool = False
    low_confidence: bool = False
    confirmation_needed: bool = False
    preferred_horizon: str | None = None
    weakening_factors: tuple[str, ...] = ()
    explanation: str
    horizons: list[AIHorizonResponse] = []
    features: AIFeatureResponse


class TradeReadinessResponse(BaseModel):
    """Serialized deterministic trade-readiness state."""

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
    reason_if_not_trading: str | None = None
    risk_reason_codes: tuple[str, ...] = ()
    expected_edge_pct: Decimal | None = None
    estimated_round_trip_cost_pct: Decimal | None = None


class TechnicalTimeframeSummaryResponse(BaseModel):
    """Technical trend summary for one derived timeframe."""

    timeframe: str
    trend_direction: str
    trend_strength: str


class TechnicalAnalysisResponse(BaseModel):
    """Symbol-scoped technical analysis payload."""

    symbol: str
    generated_at: datetime | None = None
    data_state: DataState
    status_message: str | None = None
    trend_direction: str | None = None
    trend_strength: str | None = None
    trend_strength_score: int | None = None
    support_levels: list[Decimal] = []
    resistance_levels: list[Decimal] = []
    momentum_state: str | None = None
    volatility_regime: str | None = None
    breakout_readiness: str | None = None
    breakout_bias: str | None = None
    reversal_risk: str | None = None
    multi_timeframe_agreement: str | None = None
    timeframe_summaries: list[TechnicalTimeframeSummaryResponse] = []
    explanation: str | None = None


class PatternAnalysisResponse(BaseModel):
    """Symbol-scoped multi-horizon pattern-analysis payload."""

    symbol: str
    horizon: str
    generated_at: datetime | None = None
    data_state: DataState
    status_message: str | None = None
    coverage_start: datetime | None = None
    coverage_end: datetime | None = None
    coverage_ratio_pct: Decimal = Decimal("0")
    partial_coverage: bool = False
    overall_direction: str | None = None
    net_return_pct: Decimal | None = None
    up_moves: int = 0
    down_moves: int = 0
    flat_moves: int = 0
    up_move_ratio_pct: Decimal | None = None
    down_move_ratio_pct: Decimal | None = None
    realized_volatility_pct: Decimal | None = None
    max_drawdown_pct: Decimal | None = None
    trend_character: str | None = None
    breakout_tendency: str | None = None
    reversal_tendency: str | None = None
    explanation: str | None = None


class MarketSentimentResponse(BaseModel):
    """Symbol-scoped broader-market sentiment payload."""

    symbol: str
    generated_at: datetime | None = None
    data_state: DataState
    status_message: str | None = None
    market_state: str
    sentiment_score: int | None = None
    btc_bias: str | None = None
    eth_bias: str | None = None
    selected_symbol_relative_strength: str = "insufficient_data"
    relative_strength_pct: Decimal | None = None
    market_breadth_state: str = "insufficient_data"
    breadth_advancing_symbols: int = 0
    breadth_declining_symbols: int = 0
    breadth_sample_size: int = 0
    volatility_environment: str = "insufficient_data"
    explanation: str | None = None


class SymbolSentimentResponse(BaseModel):
    """Symbol-scoped sentiment intelligence payload."""

    symbol: str
    generated_at: datetime | None = None
    data_state: DataState
    status_message: str | None = None
    score: int | None = None
    label: str = "insufficient_data"
    confidence: int | None = None
    momentum_state: str = "unknown"
    risk_flag: str = "unknown"
    source_mode: str = "proxy"
    components: list[str] = Field(default_factory=list)
    explanation: str | None = None


class FusionSignalResponse(BaseModel):
    """Unified advisory fusion signal for one selected symbol."""

    symbol: str
    generated_at: datetime | None = None
    data_state: DataState
    status_message: str | None = None
    final_signal: str = "wait"
    confidence: int = 0
    expected_edge_pct: Decimal | None = None
    preferred_horizon: str = "15m"
    risk_grade: str = "high"
    alignment_score: int = 0
    top_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    invalidation_hint: str | None = None


class AISignalHistoryResponse(BaseModel):
    """Paginated AI advisory history for one symbol."""

    items: list[AISignalResponse]
    total: int
    limit: int
    offset: int
    data_state: DataState
    status_message: str | None = None


class AIOutcomeSummaryResponse(BaseModel):
    """Aggregated AI outcome metrics for one evaluation horizon."""

    horizon: str
    sample_size: int
    directional_accuracy_pct: Decimal
    confidence_calibration_pct: Decimal
    actionable_sample_size: int
    abstain_count: int
    abstain_rate_pct: Decimal
    false_positive_count: int
    false_positive_rate_pct: Decimal
    false_reversal_count: int
    false_reversal_rate_pct: Decimal


class AIOutcomeSampleResponse(BaseModel):
    """One evaluated AI advisory sample."""

    symbol: str
    snapshot_time: datetime
    horizon: str
    bias: str
    confidence: int
    entry_signal: bool
    exit_signal: bool
    suggested_action: str
    baseline_close: Decimal
    future_close: Decimal
    return_pct: Decimal
    observed_direction: str
    directional_correct: bool
    false_positive: bool
    false_reversal: bool
    abstained: bool


class AIOutcomeEvaluationResponse(BaseModel):
    """Symbol-scoped AI outcome evaluation payload."""

    symbol: str
    generated_at: datetime
    horizons: list[AIOutcomeSummaryResponse]
    recent_samples: list[AIOutcomeSampleResponse]
    data_state: DataState
    status_message: str | None = None


class WorkstationResponse(BaseModel):
    """Symbol-scoped workstation payload."""

    symbol: str
    data_state: DataState
    status_message: str | None = None
    is_runtime_symbol: bool
    runtime_status: BotStatusResponse
    persistence: PersistenceHealthResponse
    last_price: Decimal | None = None
    current_candle: CandleSummaryResponse | None = None
    top_of_book: TopOfBookResponse | None = None
    feature: FeatureSummaryResponse | None = None
    trade_readiness: TradeReadinessResponse
    ai_signal: AISignalResponse | None = None
    trend_bias: str | None = None
    entry_signal: SignalSummaryResponse | None = None
    exit_signal: SignalSummaryResponse | None = None
    explanation: str | None = None
    current_position: PositionSummaryResponse | None = None
    last_action: LastActionResponse | None = None
    last_market_event: datetime | None = None
    total_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")


def _empty_workstation_state(symbol: str) -> WorkstationState:
    """Return a neutral workstation state for an uninitialized symbol."""

    return WorkstationState(
        symbol=symbol,
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
    )


def _safe_workstation_state(
    runtime: PaperBotRuntime,
    symbol: str,
) -> tuple[WorkstationState, bool, str | None]:
    """Return workstation state without allowing runtime errors to escape the API."""

    try:
        return runtime.workstation_state(symbol), False, None
    except Exception:
        LOGGER.exception("Failed to build workstation state for symbol %s.", symbol)
        return (
            _empty_workstation_state(symbol),
            True,
            "Optional workstation state is temporarily degraded.",
        )


def _safe_technical_analysis(
    runtime: PaperBotRuntime,
    symbol: str,
) -> tuple[TechnicalAnalysisSnapshot | None, bool]:
    """Return technical analysis without allowing runtime failures to escape the API."""

    try:
        return runtime.technical_analysis(symbol), False
    except Exception:
        LOGGER.exception("Failed to build technical analysis for symbol %s.", symbol)
        return None, True


def _safe_pattern_analysis(
    runtime: PaperBotRuntime,
    *,
    symbol: str,
    horizon: str,
    repository: StorageRepository,
) -> tuple[PatternAnalysisSnapshot | None, bool]:
    """Return pattern analysis without allowing runtime errors to escape the API."""

    try:
        persisted_points = [
            _to_pattern_point(record)
            for record in repository.get_market_candle_history(symbol=symbol, timeframe="1m")
        ]
        live_points = [
            PatternPricePoint(
                symbol=candle.symbol,
                timestamp=candle.close_time,
                close_price=candle.close,
            )
            for candle in runtime.candle_history(symbol)
            if candle.is_closed
        ]
        merged_points = merge_pattern_points(
            persisted_points=persisted_points,
            live_points=live_points,
        )
        return (
            HorizonPatternAnalysisService().analyze(
                symbol=symbol,
                horizon=horizon,
                points=merged_points,
                runtime_active=_runtime_matches_symbol(runtime.status(), symbol),
            ),
            False,
        )
    except Exception:
        LOGGER.exception("Failed to build pattern analysis for symbol %s horizon %s.", symbol, horizon)
        return None, True


def _safe_market_sentiment(
    runtime: PaperBotRuntime,
    *,
    symbol: str,
    repository: StorageRepository,
) -> tuple[MarketSentimentSnapshot | None, bool]:
    """Return market sentiment without allowing runtime failures to escape the API."""

    try:
        symbol_points = MarketContextService(
            repository=repository,
            runtime=runtime,
        ).load_market_context(selected_symbol=symbol)
        return (
            MarketSentimentService().analyze(
                symbol=symbol,
                symbol_points=symbol_points,
            ),
            False,
        )
    except Exception:
        LOGGER.exception("Failed to build market sentiment for symbol %s.", symbol)
        return None, True


def _safe_symbol_sentiment(
    service: SymbolSentimentService,
    *,
    symbol: str,
    runtime: PaperBotRuntime,
    repository: StorageRepository,
) -> tuple[SymbolSentimentSnapshot | None, bool]:
    """Return symbol sentiment without allowing source/service errors to escape the API."""

    try:
        benchmark_records = repository.get_market_candle_history(symbol="BTCUSDT", timeframe="1m")
        return (
            service.analyze(
                symbol=symbol,
                candles=runtime.candle_history(symbol),
                benchmark_symbol="BTCUSDT" if benchmark_records else None,
                benchmark_closes=[record.close_price for record in benchmark_records[-24:]],
            ),
            False,
        )
    except Exception:
        LOGGER.exception("Failed to build symbol sentiment for symbol %s.", symbol)
        return None, True


def _safe_fusion_signal(
    *,
    symbol: str,
    runtime: PaperBotRuntime,
    repository: StorageRepository | None,
    sentiment_service: SymbolSentimentService,
) -> tuple[FusionSignalSnapshot | None, bool]:
    """Return a fused advisory signal without allowing optional dependencies to escape the API."""

    try:
        workstation_state, _, _ = _safe_workstation_state(runtime, symbol)
        technical_analysis, _ = _safe_technical_analysis(runtime, symbol)
        if repository is not None:
            pattern_analysis, _ = _safe_pattern_analysis(
                runtime,
                symbol=symbol,
                horizon="7d",
                repository=repository,
            )
            symbol_sentiment, _ = _safe_symbol_sentiment(
                sentiment_service,
                symbol=symbol,
                runtime=runtime,
                repository=repository,
            )
        else:
            pattern_analysis = HorizonPatternAnalysisService().analyze(
                symbol=symbol,
                horizon="7d",
                points=[
                    PatternPricePoint(symbol=candle.symbol, timestamp=candle.close_time, close_price=candle.close)
                    for candle in runtime.candle_history(symbol)
                    if candle.is_closed
                ],
                runtime_active=_runtime_matches_symbol(runtime.status(), symbol),
            )
            symbol_sentiment = sentiment_service.analyze(
                symbol=symbol,
                candles=runtime.candle_history(symbol),
                benchmark_symbol=None,
                benchmark_closes=(),
            )
        return (
            UnifiedSignalFusionEngine().build_signal(
                FusionInputs(
                    symbol=symbol,
                    technical_analysis=technical_analysis,
                    pattern_analysis=pattern_analysis,
                    ai_signal=workstation_state.ai_signal,
                    symbol_sentiment=symbol_sentiment,
                    trade_readiness=workstation_state.trade_readiness,
                    current_position_quantity=(
                        workstation_state.current_position.quantity
                        if workstation_state.current_position is not None
                        else Decimal("0")
                    ),
                )
            ),
            False,
        )
    except Exception:
        LOGGER.exception("Failed to build fusion signal for symbol %s.", symbol)
        return None, True


def _empty_ai_signal_history_response(
    limit: int,
    offset: int,
    *,
    data_state: DataState,
    status_message: str | None,
) -> AISignalHistoryResponse:
    """Return a typed empty AI history response."""

    return AISignalHistoryResponse(
        items=[],
        total=0,
        limit=limit,
        offset=offset,
        data_state=data_state,
        status_message=status_message,
    )


def _empty_ai_outcome_evaluation_response(
    symbol: str,
    *,
    data_state: DataState,
    status_message: str | None,
) -> AIOutcomeEvaluationResponse:
    """Return a typed empty AI outcome evaluation payload."""

    return AIOutcomeEvaluationResponse(
        symbol=symbol,
        generated_at=datetime.now(tz=UTC),
        horizons=[
            AIOutcomeSummaryResponse(
                horizon=horizon,
                sample_size=0,
                directional_accuracy_pct=Decimal("0"),
                confidence_calibration_pct=Decimal("0"),
                actionable_sample_size=0,
                abstain_count=0,
                abstain_rate_pct=Decimal("0"),
                false_positive_count=0,
                false_positive_rate_pct=Decimal("0"),
                false_reversal_count=0,
                false_reversal_rate_pct=Decimal("0"),
            )
            for horizon in ("5m", "15m", "1h")
        ],
        recent_samples=[],
        data_state=data_state,
        status_message=status_message,
    )


def _runtime_matches_symbol(status: BotStatus, symbol: str) -> bool:
    """Return whether the live runtime is currently attached to the requested symbol."""

    return status.symbol == symbol and status.state in {"running", "paused"}


def _derive_workstation_data_state(
    *,
    state: WorkstationState,
    status: BotStatus,
    storage_degraded: bool,
    storage_message: str | None,
    state_failed: bool,
    state_failure_message: str | None,
) -> tuple[DataState, str]:
    """Derive the workstation readiness state for one symbol."""

    runtime_attached = state.is_runtime_symbol and _runtime_matches_symbol(status, state.symbol)
    if state_failed or (storage_degraded and runtime_attached):
        return (
            "degraded_storage",
            state_failure_message
            or storage_message
            or "Optional workstation history or storage is temporarily degraded.",
        )
    if not runtime_attached:
        return (
            "waiting_for_runtime",
            f"Start or attach the live runtime for {state.symbol} to populate symbol-scoped workstation data.",
        )
    if state.market_snapshot is None or state.feature_snapshot is None or state.ai_signal is None:
        return (
            "waiting_for_history",
            f"Live data is connected for {state.symbol}, but more candle history is needed before all signal fields are ready.",
        )
    return ("ready", f"Live runtime, feature state, and advisory signal are ready for {state.symbol}.")


def _derive_history_data_state(
    *,
    symbol: str,
    status: BotStatus,
    has_items: bool,
    storage_degraded: bool,
    storage_message: str | None,
) -> tuple[DataState, str]:
    """Derive a symbol-scoped AI history state."""

    if storage_degraded:
        return (
            "degraded_storage",
            storage_message or "Persisted AI history is temporarily unavailable.",
        )
    if has_items:
        return ("ready", f"Persisted AI history is available for {symbol}.")
    if _runtime_matches_symbol(status, symbol):
        return (
            "waiting_for_history",
            f"The runtime is active for {symbol}, but persisted AI history has not accumulated yet.",
        )
    return (
        "waiting_for_runtime",
        f"Start the runtime for {symbol} to generate persisted AI history.",
    )


def _derive_evaluation_data_state(
    *,
    symbol: str,
    status: BotStatus,
    has_samples: bool,
    storage_degraded: bool,
    storage_message: str | None,
) -> tuple[DataState, str]:
    """Derive a symbol-scoped AI evaluation state."""

    if storage_degraded:
        return (
            "degraded_storage",
            storage_message or "AI outcome validation storage is temporarily unavailable.",
        )
    if has_samples:
        return ("ready", f"AI outcome validation has enough samples for {symbol}.")
    if _runtime_matches_symbol(status, symbol):
        return (
            "waiting_for_history",
            f"AI outcome validation for {symbol} needs more closed-candle history after each advisory snapshot.",
        )
    return (
        "waiting_for_runtime",
        f"Start the runtime for {symbol} to accumulate advisory outcomes.",
    )


def _derive_technical_analysis_data_state(
    *,
    symbol: str,
    status: BotStatus,
    analysis: TechnicalAnalysisSnapshot | None,
    analysis_failed: bool,
) -> tuple[DataState, str]:
    """Derive a symbol-scoped technical-analysis readiness state."""

    if analysis_failed:
        return (
            "degraded_storage",
            f"Technical analysis for {symbol} is temporarily unavailable.",
        )
    if not _runtime_matches_symbol(status, symbol):
        return (
            "waiting_for_runtime",
            f"Start or attach the live runtime for {symbol} to build technical analysis.",
        )
    if analysis is None or analysis.data_state == "incomplete":
        return (
            "waiting_for_history",
            analysis.status_message
            if analysis is not None
            else f"Technical analysis for {symbol} needs more closed-candle history.",
        )
    return ("ready", analysis.status_message or f"Technical analysis is ready for {symbol}.")


def _derive_pattern_analysis_data_state(
    *,
    symbol: str,
    horizon: str,
    status: BotStatus,
    analysis: PatternAnalysisSnapshot | None,
    analysis_failed: bool,
    storage_degraded: bool,
    storage_message: str | None,
) -> tuple[DataState, str]:
    """Derive a symbol-scoped pattern-analysis readiness state."""

    if analysis_failed or storage_degraded:
        return (
            "degraded_storage",
            storage_message or f"Pattern analysis for {symbol} is temporarily unavailable.",
        )
    if analysis is None:
        return (
            "waiting_for_runtime" if not _runtime_matches_symbol(status, symbol) else "waiting_for_history",
            (
                f"Start the runtime for {symbol} to accumulate {horizon.upper()} pattern history."
                if not _runtime_matches_symbol(status, symbol)
                else f"Pattern analysis for {symbol} needs more closed candles for {horizon.upper()}."
            ),
        )
    return (analysis.data_state, analysis.status_message or f"Pattern analysis is ready for {symbol}.")


def _derive_market_sentiment_data_state(
    *,
    symbol: str,
    status: BotStatus,
    analysis: MarketSentimentSnapshot | None,
    analysis_failed: bool,
    storage_degraded: bool,
    storage_message: str | None,
) -> tuple[DataState, str]:
    """Derive a symbol-scoped market-sentiment readiness state."""

    if analysis_failed or storage_degraded:
        return (
            "degraded_storage",
            storage_message or f"Market sentiment for {symbol} is temporarily unavailable.",
        )
    if analysis is None:
        return (
            "waiting_for_runtime" if not _runtime_matches_symbol(status, symbol) else "waiting_for_history",
            (
                f"Start the runtime for {symbol} to accumulate broader market context."
                if not _runtime_matches_symbol(status, symbol)
                else f"Market sentiment for {symbol} still needs more broader market history."
            ),
        )
    if analysis.data_state == "incomplete":
        return (
            "waiting_for_runtime" if not _runtime_matches_symbol(status, symbol) else "waiting_for_history",
            analysis.status_message
            or (
                f"Start the runtime for {symbol} to build broader market context."
                if not _runtime_matches_symbol(status, symbol)
                else f"Market sentiment for {symbol} needs more history."
            ),
        )
    return ("ready", analysis.status_message or f"Market sentiment is ready for {symbol}.")


def _derive_symbol_sentiment_data_state(
    *,
    symbol: str,
    status: BotStatus,
    analysis: SymbolSentimentSnapshot | None,
    analysis_failed: bool,
) -> tuple[DataState, str]:
    """Derive a symbol-scoped sentiment state without fabricating evidence."""

    if analysis_failed:
        return (
            "degraded_storage",
            f"Symbol sentiment for {symbol} is temporarily unavailable.",
        )
    if analysis is None:
        return (
            "degraded_storage",
            f"Symbol sentiment for {symbol} could not be built.",
        )
    if analysis.data_state == "incomplete":
        if not _runtime_matches_symbol(status, symbol):
            return (
                "waiting_for_runtime",
                f"Start the runtime for {symbol} to accumulate symbol-scoped sentiment inputs.",
            )
        return (
            "waiting_for_history",
            analysis.status_message or f"Symbol sentiment for {symbol} still needs more live history.",
        )
    return (
        "ready",
        analysis.status_message or f"Symbol sentiment is ready for {symbol}.",
    )


def _derive_fusion_data_state(
    *,
    symbol: str,
    status: BotStatus,
    analysis: FusionSignalSnapshot | None,
    analysis_failed: bool,
) -> tuple[DataState, str]:
    """Derive a fusion data state without raising on optional input gaps."""

    if analysis_failed:
        return ("degraded_storage", f"Final fusion signal for {symbol} is temporarily unavailable.")
    if analysis is None:
        return ("degraded_storage", f"Final fusion signal for {symbol} could not be built.")
    if analysis.data_state == "incomplete":
        if not _runtime_matches_symbol(status, symbol):
            return (
                "waiting_for_runtime",
                f"Start the runtime for {symbol} to build the final fused signal.",
            )
        return (
            "waiting_for_history",
            analysis.status_message or f"Fusion signal for {symbol} still needs more analysis history.",
        )
    return ("ready", analysis.status_message or f"Fusion signal is ready for {symbol}.")


def get_symbol_service(request: Request) -> SpotSymbolService:
    """Return the shared symbol service instance from FastAPI app state."""

    return request.app.state.symbol_service


def get_symbol_sentiment_service(request: Request) -> SymbolSentimentService:
    """Return the shared symbol-sentiment service instance from app state."""

    return request.app.state.symbol_sentiment_service


def get_bot_runtime(request: Request) -> PaperBotRuntime:
    """Return the shared live paper-bot runtime instance from app state."""

    return request.app.state.bot_runtime


def get_settings_dependency() -> Settings:
    """Return application settings for bot control routes."""

    return get_settings()


def _to_symbol_response(record: SpotSymbolRecord) -> SymbolResponse:
    """Convert a symbol record to an API response."""

    return SymbolResponse(
        symbol=record.symbol,
        base_asset=record.base_asset,
        quote_asset=record.quote_asset,
        status=record.status,
    )


def _to_persistence_response(runtime: PaperBotRuntime) -> PersistenceHealthResponse:
    """Convert runtime persistence state to an API response."""

    return PersistenceHealthResponse(
        persistence_state=runtime.persistence_state(),
        persistence_message=runtime.persistence_status_message(),
        persistence_last_ok_at=runtime.persistence_last_ok_at(),
        recovery_source=runtime.persistence_recovery_source(),
    )


def _to_status_response(
    status: BotStatus,
    *,
    persistence: PersistenceHealthResponse,
) -> BotStatusResponse:
    """Convert runtime status to an API response."""

    return BotStatusResponse(
        state=status.state,
        mode=status.mode,
        symbol=status.symbol,
        timeframe=status.timeframe,
        paper_only=status.paper_only,
        session_id=status.session_id,
        started_at=status.started_at,
        last_event_time=status.last_event_time,
        last_error=status.last_error,
        recovered_from_prior_session=status.recovered_from_prior_session,
        broker_state_restored=status.broker_state_restored,
        recovery_message=status.recovery_message,
        persistence=persistence,
    )


def _default_trade_readiness_response(symbol: str, status: BotStatus) -> TradeReadinessResponse:
    """Return a neutral deterministic readiness payload for one symbol."""

    runtime_active = status.symbol == symbol and status.state in {"running", "paused"}
    return TradeReadinessResponse(
        selected_symbol=symbol,
        runtime_active=runtime_active,
        mode=status.mode,
        enough_candle_history=False,
        deterministic_entry_signal=False,
        deterministic_exit_signal=False,
        risk_ready=False,
        risk_blocked=False,
        broker_ready=runtime_active and status.paper_only,
        next_action=(
            "resume_runtime"
            if status.recovered_from_prior_session and status.symbol == symbol and status.mode == "paused"
            else ("start_runtime" if not runtime_active else "wait_for_history")
        ),
        reason_if_not_trading=(
            status.recovery_message
            if status.recovered_from_prior_session and status.symbol == symbol and status.mode == "paused"
            else (
                f"Start the live runtime for {symbol} before auto paper trading can act."
                if not runtime_active
                else f"Waiting for enough closed candle history to build deterministic signals for {symbol}."
            )
        ),
        risk_reason_codes=(),
    )


def _to_trade_readiness_response(
    readiness: TradeReadiness | None,
    *,
    symbol: str,
    status: BotStatus,
) -> TradeReadinessResponse:
    """Convert deterministic readiness to an API response with recovery-aware messaging."""

    if readiness is None:
        return _default_trade_readiness_response(symbol, status)

    next_action = readiness.next_action
    reason_if_not_trading = readiness.reason_if_not_trading
    if (
        status.recovered_from_prior_session
        and status.symbol == symbol
        and status.mode == "paused"
    ):
        next_action = "resume_runtime"
        reason_if_not_trading = status.recovery_message

    return TradeReadinessResponse(
        selected_symbol=readiness.selected_symbol,
        runtime_active=readiness.runtime_active,
        mode=readiness.mode,
        enough_candle_history=readiness.enough_candle_history,
        deterministic_entry_signal=readiness.deterministic_entry_signal,
        deterministic_exit_signal=readiness.deterministic_exit_signal,
        risk_ready=readiness.risk_ready,
        risk_blocked=readiness.risk_blocked,
        broker_ready=readiness.broker_ready,
        next_action=next_action,
        reason_if_not_trading=reason_if_not_trading,
        risk_reason_codes=readiness.risk_reason_codes,
        expected_edge_pct=readiness.expected_edge_pct,
        estimated_round_trip_cost_pct=readiness.estimated_round_trip_cost_pct,
    )


def _to_ai_signal_response(
    *,
    symbol: str,
    timestamp: datetime,
    bias: str,
    confidence: int,
    entry_signal: bool,
    exit_signal: bool,
    suggested_action: str,
    explanation: str,
    candle_count: int,
    close_price: Decimal,
    volatility_pct: Decimal | None,
    momentum: Decimal | None,
    volume_change_pct: Decimal | None,
    volume_spike_ratio: Decimal | None,
    spread_ratio: Decimal | None,
    microstructure_healthy: bool,
    momentum_persistence: Decimal | None = None,
    direction_flip_rate: Decimal | None = None,
    structure_quality: Decimal | None = None,
    recent_false_positive_rate_5m: Decimal | None = None,
    regime: str = "insufficient_data",
    noise_level: str = "unknown",
    abstain: bool = False,
    low_confidence: bool = False,
    confirmation_needed: bool = False,
    preferred_horizon: str | None = None,
    weakening_factors: tuple[str, ...] = (),
    horizons: list[AIHorizonResponse] | None = None,
) -> AISignalResponse:
    """Build a stable AI advisory API response."""

    return AISignalResponse(
        symbol=symbol,
        timestamp=timestamp,
        bias=bias,
        confidence=confidence,
        entry_signal=entry_signal,
        exit_signal=exit_signal,
        suggested_action=suggested_action,
        regime=regime,
        noise_level=noise_level,
        abstain=abstain,
        low_confidence=low_confidence,
        confirmation_needed=confirmation_needed,
        preferred_horizon=preferred_horizon,
        weakening_factors=weakening_factors,
        explanation=explanation,
        horizons=horizons or [],
        features=AIFeatureResponse(
            candle_count=candle_count,
            close_price=close_price,
            volatility_pct=volatility_pct,
            momentum=momentum,
            volume_change_pct=volume_change_pct,
            volume_spike_ratio=volume_spike_ratio,
            spread_ratio=spread_ratio,
            microstructure_healthy=microstructure_healthy,
            momentum_persistence=momentum_persistence,
            direction_flip_rate=direction_flip_rate,
            structure_quality=structure_quality,
            recent_false_positive_rate_5m=recent_false_positive_rate_5m,
        ),
    )


def _to_technical_analysis_response(
    *,
    symbol: str,
    analysis: TechnicalAnalysisSnapshot | None,
    data_state: DataState,
    status_message: str | None,
) -> TechnicalAnalysisResponse:
    """Build a stable technical-analysis API response."""

    if analysis is None:
        return TechnicalAnalysisResponse(
            symbol=symbol,
            data_state=data_state,
            status_message=status_message,
        )

    return TechnicalAnalysisResponse(
        symbol=analysis.symbol,
        generated_at=analysis.timestamp,
        data_state=data_state,
        status_message=status_message,
        trend_direction=analysis.trend_direction,
        trend_strength=analysis.trend_strength,
        trend_strength_score=analysis.trend_strength_score,
        support_levels=analysis.support_levels,
        resistance_levels=analysis.resistance_levels,
        momentum_state=analysis.momentum_state,
        volatility_regime=analysis.volatility_regime,
        breakout_readiness=analysis.breakout_readiness,
        breakout_bias=analysis.breakout_bias,
        reversal_risk=analysis.reversal_risk,
        multi_timeframe_agreement=analysis.multi_timeframe_agreement,
        timeframe_summaries=[
            _to_technical_timeframe_response(summary)
            for summary in analysis.timeframe_summaries
        ],
        explanation=analysis.explanation,
    )


def _to_technical_timeframe_response(
    summary: TimeframeTechnicalSummary,
) -> TechnicalTimeframeSummaryResponse:
    """Convert a timeframe technical summary into an API response."""

    return TechnicalTimeframeSummaryResponse(
        timeframe=summary.timeframe,
        trend_direction=summary.trend_direction,
        trend_strength=summary.trend_strength,
    )


def _to_pattern_point(record: MarketCandleSnapshotRecord) -> PatternPricePoint:
    """Convert a persisted close-price record into a pattern-analysis point."""

    return PatternPricePoint(
        symbol=record.symbol,
        timestamp=record.close_time,
        close_price=record.close_price,
    )


def _to_pattern_analysis_response(
    *,
    symbol: str,
    horizon: str,
    analysis: PatternAnalysisSnapshot | None,
    data_state: DataState,
    status_message: str | None,
) -> PatternAnalysisResponse:
    """Build a stable pattern-analysis API response."""

    if analysis is None:
        return PatternAnalysisResponse(
            symbol=symbol,
            horizon=horizon,
            data_state=data_state,
            status_message=status_message,
        )

    return PatternAnalysisResponse(
        symbol=analysis.symbol,
        horizon=analysis.horizon,
        generated_at=analysis.generated_at,
        data_state=data_state,
        status_message=status_message,
        coverage_start=analysis.coverage_start,
        coverage_end=analysis.coverage_end,
        coverage_ratio_pct=analysis.coverage_ratio_pct,
        partial_coverage=analysis.partial_coverage,
        overall_direction=analysis.overall_direction,
        net_return_pct=analysis.net_return_pct,
        up_moves=analysis.up_moves,
        down_moves=analysis.down_moves,
        flat_moves=analysis.flat_moves,
        up_move_ratio_pct=analysis.up_move_ratio_pct,
        down_move_ratio_pct=analysis.down_move_ratio_pct,
        realized_volatility_pct=analysis.realized_volatility_pct,
        max_drawdown_pct=analysis.max_drawdown_pct,
        trend_character=analysis.trend_character,
        breakout_tendency=analysis.breakout_tendency,
        reversal_tendency=analysis.reversal_tendency,
        explanation=analysis.explanation,
    )


def _to_market_sentiment_response(
    *,
    symbol: str,
    analysis: MarketSentimentSnapshot | None,
    data_state: DataState,
    status_message: str | None,
) -> MarketSentimentResponse:
    """Build a stable market-sentiment API response."""

    return MarketSentimentResponse(
        symbol=symbol,
        generated_at=analysis.generated_at if analysis is not None else None,
        data_state=data_state,
        status_message=status_message,
        market_state=analysis.market_state if analysis is not None else "insufficient_data",
        sentiment_score=analysis.sentiment_score if analysis is not None else None,
        btc_bias=analysis.btc_bias if analysis is not None else None,
        eth_bias=analysis.eth_bias if analysis is not None else None,
        selected_symbol_relative_strength=(
            analysis.selected_symbol_relative_strength if analysis is not None else "insufficient_data"
        ),
        relative_strength_pct=analysis.relative_strength_pct if analysis is not None else None,
        market_breadth_state=analysis.market_breadth_state if analysis is not None else "insufficient_data",
        breadth_advancing_symbols=analysis.breadth_advancing_symbols if analysis is not None else 0,
        breadth_declining_symbols=analysis.breadth_declining_symbols if analysis is not None else 0,
        breadth_sample_size=analysis.breadth_sample_size if analysis is not None else 0,
        volatility_environment=analysis.volatility_environment if analysis is not None else "insufficient_data",
        explanation=analysis.explanation if analysis is not None else None,
    )


def _to_symbol_sentiment_response(
    *,
    symbol: str,
    analysis: SymbolSentimentSnapshot | None,
    data_state: DataState,
    status_message: str | None,
) -> SymbolSentimentResponse:
    """Build a stable symbol-sentiment API response."""

    return SymbolSentimentResponse(
        symbol=symbol,
        generated_at=analysis.generated_at if analysis is not None else None,
        data_state=data_state,
        status_message=status_message,
        score=analysis.score if analysis is not None else None,
        label=analysis.label if analysis is not None else "insufficient_data",
        confidence=analysis.confidence if analysis is not None else None,
        momentum_state=analysis.momentum_state if analysis is not None else "unknown",
        risk_flag=analysis.risk_flag if analysis is not None else "unknown",
        source_mode=analysis.source_mode if analysis is not None else "proxy",
        components=[component.explanation for component in analysis.components] if analysis is not None else [],
        explanation=analysis.explanation if analysis is not None else None,
    )


def _to_fusion_signal_response(
    *,
    symbol: str,
    analysis: FusionSignalSnapshot | None,
    data_state: DataState,
    status_message: str | None,
) -> FusionSignalResponse:
    """Build a stable unified fusion API response."""

    return FusionSignalResponse(
        symbol=symbol,
        generated_at=analysis.generated_at if analysis is not None else None,
        data_state=data_state,
        status_message=status_message,
        final_signal=analysis.final_signal if analysis is not None else "wait",
        confidence=analysis.confidence if analysis is not None else 0,
        expected_edge_pct=analysis.expected_edge_pct if analysis is not None else None,
        preferred_horizon=analysis.preferred_horizon if analysis is not None else "15m",
        risk_grade=analysis.risk_grade if analysis is not None else "high",
        alignment_score=analysis.alignment_score if analysis is not None else 0,
        top_reasons=list(analysis.top_reasons) if analysis is not None else [],
        warnings=list(analysis.warnings) if analysis is not None else [],
        invalidation_hint=analysis.invalidation_hint if analysis is not None else None,
    )


def _to_ai_outcome_evaluation_response(
    *,
    symbol: str,
    generated_at: datetime,
    horizons,
    recent_samples,
    data_state: DataState,
    status_message: str | None,
) -> AIOutcomeEvaluationResponse:
    """Build a stable AI outcome evaluation API response."""

    return AIOutcomeEvaluationResponse(
        symbol=symbol,
        generated_at=generated_at,
        data_state=data_state,
        status_message=status_message,
        horizons=[
            AIOutcomeSummaryResponse(
                horizon=item.horizon,
                sample_size=item.sample_size,
                directional_accuracy_pct=item.directional_accuracy_pct,
                confidence_calibration_pct=item.confidence_calibration_pct,
                actionable_sample_size=item.actionable_sample_size,
                abstain_count=item.abstain_count,
                abstain_rate_pct=item.abstain_rate_pct,
                false_positive_count=item.false_positive_count,
                false_positive_rate_pct=item.false_positive_rate_pct,
                false_reversal_count=item.false_reversal_count,
                false_reversal_rate_pct=item.false_reversal_rate_pct,
            )
            for item in horizons
        ],
        recent_samples=[
            AIOutcomeSampleResponse(
                symbol=item.symbol,
                snapshot_time=item.snapshot_time,
                horizon=item.horizon,
                bias=item.bias,
                confidence=item.confidence,
                entry_signal=item.entry_signal,
                exit_signal=item.exit_signal,
                suggested_action=item.suggested_action,
                baseline_close=item.baseline_close,
                future_close=item.future_close,
                return_pct=item.return_pct,
                observed_direction=item.observed_direction,
                directional_correct=item.directional_correct,
                false_positive=item.false_positive,
                false_reversal=item.false_reversal,
                abstained=item.abstained,
            )
            for item in recent_samples
        ],
    )


def _to_workstation_response(
    *,
    state: WorkstationState,
    runtime: PaperBotRuntime,
    status: BotStatus,
    data_state: DataState,
    status_message: str | None,
) -> WorkstationResponse:
    """Convert runtime workstation state into an API response."""

    market_snapshot = state.market_snapshot
    candle = market_snapshot.candle if market_snapshot is not None else None
    top_of_book = market_snapshot.top_of_book if market_snapshot is not None else None
    feature_snapshot = state.feature_snapshot
    ai_signal = state.ai_signal
    entry_signal = state.entry_signal
    exit_signal = state.exit_signal
    last_cycle_result = state.last_cycle_result

    trend_bias: str | None = None
    if feature_snapshot is not None:
        if feature_snapshot.regime == "bullish":
            trend_bias = "Bullish trend"
        elif feature_snapshot.regime == "bearish":
            trend_bias = "Bearish trend"
        elif feature_snapshot.regime == "neutral":
            trend_bias = "Neutral"

    explanation_parts: list[str] = []
    if entry_signal is not None:
        explanation_parts.append(f"Entry {entry_signal.side}: {', '.join(entry_signal.reason_codes) or 'waiting'}")
    if exit_signal is not None:
        explanation_parts.append(f"Exit {exit_signal.side}: {', '.join(exit_signal.reason_codes) or 'waiting'}")

    last_action = None
    if last_cycle_result is not None:
        execution_result = last_cycle_result.execution_result
        last_action = LastActionResponse(
            signal_side=last_cycle_result.signal.side,
            signal_reasons=last_cycle_result.signal.reason_codes,
            execution_status=execution_result.status if execution_result is not None else None,
            execution_reasons=execution_result.reason_codes if execution_result is not None else (),
            event_time=last_cycle_result.feature_snapshot.timestamp,
        )

    return WorkstationResponse(
        symbol=state.symbol,
        data_state=data_state,
        status_message=status_message,
        is_runtime_symbol=state.is_runtime_symbol,
        runtime_status=_to_status_response(status, persistence=_to_persistence_response(runtime)),
        persistence=_to_persistence_response(runtime),
        last_price=market_snapshot.last_price if market_snapshot is not None else None,
        current_candle=(
            CandleSummaryResponse(
                timeframe=candle.timeframe,
                open_time=candle.open_time,
                close_time=candle.close_time,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
                is_closed=candle.is_closed,
            )
            if candle is not None
            else None
        ),
        top_of_book=(
            TopOfBookResponse(
                bid_price=top_of_book.bid_price,
                bid_quantity=top_of_book.bid_quantity,
                ask_price=top_of_book.ask_price,
                ask_quantity=top_of_book.ask_quantity,
                event_time=top_of_book.event_time,
            )
            if top_of_book is not None
            else None
        ),
        feature=(
            FeatureSummaryResponse(
                regime=feature_snapshot.regime,
                ema_fast=feature_snapshot.ema_fast,
                ema_slow=feature_snapshot.ema_slow,
                atr=feature_snapshot.atr,
                mid_price=feature_snapshot.mid_price,
                bid_ask_spread=feature_snapshot.bid_ask_spread,
                order_book_imbalance=feature_snapshot.order_book_imbalance,
                timestamp=feature_snapshot.timestamp,
            )
            if feature_snapshot is not None
            else None
        ),
        trade_readiness=_to_trade_readiness_response(
            state.trade_readiness,
            symbol=state.symbol,
            status=status,
        ),
        ai_signal=(
            _to_ai_signal_response(
                symbol=ai_signal.symbol,
                timestamp=ai_signal.feature_vector.timestamp,
                bias=ai_signal.bias,
                confidence=ai_signal.confidence,
                entry_signal=ai_signal.entry_signal,
                exit_signal=ai_signal.exit_signal,
                suggested_action=ai_signal.suggested_action,
                explanation=ai_signal.explanation,
                candle_count=ai_signal.feature_vector.candle_count,
                close_price=ai_signal.feature_vector.close_price,
                volatility_pct=ai_signal.feature_vector.volatility_pct,
                momentum=ai_signal.feature_vector.momentum,
                volume_change_pct=ai_signal.feature_vector.volume_change_pct,
                volume_spike_ratio=ai_signal.feature_vector.volume_spike_ratio,
                spread_ratio=ai_signal.feature_vector.spread_ratio,
                microstructure_healthy=ai_signal.feature_vector.microstructure_healthy,
                momentum_persistence=ai_signal.feature_vector.momentum_persistence,
                direction_flip_rate=ai_signal.feature_vector.direction_flip_rate,
                structure_quality=ai_signal.feature_vector.structure_quality,
                recent_false_positive_rate_5m=ai_signal.feature_vector.recent_false_positive_rate_5m,
                regime=ai_signal.regime,
                noise_level=ai_signal.noise_level,
                abstain=ai_signal.abstain,
                low_confidence=ai_signal.low_confidence,
                confirmation_needed=ai_signal.confirmation_needed,
                preferred_horizon=ai_signal.preferred_horizon,
                weakening_factors=ai_signal.weakening_factors,
                horizons=[
                    AIHorizonResponse(
                        horizon=item.horizon,
                        bias=item.bias,
                        confidence=item.confidence,
                        suggested_action=item.suggested_action,
                        abstain=item.abstain,
                        confirmation_needed=item.confirmation_needed,
                        explanation=item.explanation,
                    )
                    for item in ai_signal.horizon_signals
                ],
            )
            if ai_signal is not None
            else None
        ),
        trend_bias=trend_bias,
        entry_signal=(
            SignalSummaryResponse(
                side=entry_signal.side,
                confidence=entry_signal.confidence,
                reason_codes=entry_signal.reason_codes,
            )
            if entry_signal is not None
            else None
        ),
        exit_signal=(
            SignalSummaryResponse(
                side=exit_signal.side,
                confidence=exit_signal.confidence,
                reason_codes=exit_signal.reason_codes,
            )
            if exit_signal is not None
            else None
        ),
        explanation=" | ".join(explanation_parts) if explanation_parts else None,
        current_position=(
            PositionSummaryResponse(
                symbol=state.current_position.symbol,
                quantity=state.current_position.quantity,
                avg_entry_price=state.current_position.avg_entry_price,
                realized_pnl=state.current_position.realized_pnl,
                quote_asset=state.current_position.quote_asset,
            )
            if state.current_position is not None
            else None
        ),
        last_action=last_action,
        last_market_event=market_snapshot.event_time if market_snapshot is not None else None,
        total_pnl=state.total_pnl,
        realized_pnl=state.realized_pnl,
    )


@router.get("/symbols", response_model=list[SymbolResponse])
async def get_symbols(
    symbol_service: Annotated[SpotSymbolService, Depends(get_symbol_service)],
    query: str = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> list[SymbolResponse]:
    """Return searchable tradable Spot symbols for paper mode."""

    records = await symbol_service.search_symbols(query=query, limit=limit)
    return [_to_symbol_response(record) for record in records]


@router.get("/bot/status", response_model=BotStatusResponse)
def get_bot_status(
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
) -> BotStatusResponse:
    """Return the current paper-bot runtime status."""

    return _to_status_response(runtime.status(), persistence=_to_persistence_response(runtime))


@router.post("/bot/start", response_model=BotStatusResponse)
async def start_bot(
    payload: BotStartRequest,
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
) -> BotStatusResponse:
    """Start live Binance Spot market-data driven paper trading."""

    try:
        status = await runtime.start(payload.symbol)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_status_response(status, persistence=_to_persistence_response(runtime))


@router.post("/bot/stop", response_model=BotStatusResponse)
async def stop_bot(
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
) -> BotStatusResponse:
    """Stop the live paper bot."""

    return _to_status_response(await runtime.stop(), persistence=_to_persistence_response(runtime))


@router.post("/bot/pause", response_model=BotStatusResponse)
async def pause_bot(
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
) -> BotStatusResponse:
    """Pause the live paper bot while keeping market-data ingestion alive."""

    try:
        status = await runtime.pause()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_status_response(status, persistence=_to_persistence_response(runtime))


@router.post("/bot/resume", response_model=BotStatusResponse)
async def resume_bot(
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
) -> BotStatusResponse:
    """Resume the live paper bot after a pause."""

    try:
        status = await runtime.resume()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_status_response(status, persistence=_to_persistence_response(runtime))


@router.post("/bot/reset", response_model=BotStatusResponse)
async def reset_bot_session(
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
    settings: Annotated[Settings, Depends(get_settings_dependency)],
) -> BotStatusResponse:
    """Stop the paper bot and clear persisted paper-session data."""

    status = await runtime.reset_session()
    repository = StorageRepository(settings.database_url)
    try:
        repository.clear_all()
    finally:
        repository.close()
    return _to_status_response(status, persistence=_to_persistence_response(runtime))


@router.get("/bot/workstation", response_model=WorkstationResponse)
def get_workstation(
    symbol: Annotated[str, Query(min_length=1)],
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
) -> WorkstationResponse:
    """Return the current single-symbol workstation state."""

    normalized_symbol = symbol.strip().upper()
    status = runtime.status()
    state, state_failed, state_failure_message = _safe_workstation_state(runtime, normalized_symbol)
    data_state, status_message = _derive_workstation_data_state(
        state=state,
        status=status,
        storage_degraded=runtime.storage_degraded(),
        storage_message=runtime.storage_status_message(),
        state_failed=state_failed,
        state_failure_message=state_failure_message,
    )
    return _to_workstation_response(
        state=state,
        runtime=runtime,
        status=status,
        data_state=data_state,
        status_message=status_message,
    )


@router.get("/bot/technical-analysis", response_model=TechnicalAnalysisResponse)
def get_technical_analysis(
    symbol: Annotated[str, Query(min_length=1)],
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
) -> TechnicalAnalysisResponse:
    """Return symbol-scoped technical analysis for the workstation."""

    normalized_symbol = symbol.strip().upper()
    status = runtime.status()
    analysis, analysis_failed = _safe_technical_analysis(runtime, normalized_symbol)
    data_state, status_message = _derive_technical_analysis_data_state(
        symbol=normalized_symbol,
        status=status,
        analysis=analysis,
        analysis_failed=analysis_failed,
    )
    return _to_technical_analysis_response(
        symbol=normalized_symbol,
        analysis=analysis,
        data_state=data_state,
        status_message=status_message,
    )


@router.get("/bot/pattern-analysis", response_model=PatternAnalysisResponse)
def get_pattern_analysis(
    symbol: Annotated[str, Query(min_length=1)],
    horizon: str = Query(default="7d"),
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)] = None,
    settings: Annotated[Settings, Depends(get_settings_dependency)] = None,
) -> PatternAnalysisResponse:
    """Return symbol-scoped multi-horizon pattern analysis."""

    normalized_symbol = symbol.strip().upper()
    try:
        normalized_horizon = normalize_horizon(horizon)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    runtime_status = runtime.status()
    try:
        repository = StorageRepository(settings.database_url)
    except Exception:
        LOGGER.exception(
            "Failed to open storage while reading pattern analysis for %s horizon %s.",
            normalized_symbol,
            normalized_horizon,
        )
        return _to_pattern_analysis_response(
            symbol=normalized_symbol,
            horizon=normalized_horizon,
            analysis=None,
            data_state="degraded_storage",
            status_message="Pattern-analysis storage is unavailable.",
        )
    try:
        analysis, analysis_failed = _safe_pattern_analysis(
            runtime,
            symbol=normalized_symbol,
            horizon=normalized_horizon,
            repository=repository,
        )
        data_state, status_message = _derive_pattern_analysis_data_state(
            symbol=normalized_symbol,
            horizon=normalized_horizon,
            status=runtime_status,
            analysis=analysis,
            analysis_failed=analysis_failed,
            storage_degraded=repository.optional_storage_degraded,
            storage_message=repository.optional_storage_message,
        )
    finally:
        repository.close()
    return _to_pattern_analysis_response(
        symbol=normalized_symbol,
        horizon=normalized_horizon,
        analysis=analysis,
        data_state=data_state,
        status_message=status_message,
    )


@router.get("/bot/market-sentiment", response_model=MarketSentimentResponse)
def get_market_sentiment(
    symbol: Annotated[str, Query(min_length=1)],
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
    settings: Annotated[Settings, Depends(get_settings_dependency)],
) -> MarketSentimentResponse:
    """Return symbol-scoped broader-market sentiment for the workstation."""

    normalized_symbol = symbol.strip().upper()
    runtime_status = runtime.status()
    try:
        repository = StorageRepository(settings.database_url)
    except Exception:
        LOGGER.exception("Failed to open storage while reading market sentiment for %s.", normalized_symbol)
        return _to_market_sentiment_response(
            symbol=normalized_symbol,
            analysis=None,
            data_state="degraded_storage",
            status_message="Market-sentiment storage is unavailable.",
        )
    try:
        analysis, analysis_failed = _safe_market_sentiment(
            runtime,
            symbol=normalized_symbol,
            repository=repository,
        )
        data_state, status_message = _derive_market_sentiment_data_state(
            symbol=normalized_symbol,
            status=runtime_status,
            analysis=analysis,
            analysis_failed=analysis_failed,
            storage_degraded=repository.optional_storage_degraded,
            storage_message=repository.optional_storage_message,
        )
    finally:
        repository.close()
    return _to_market_sentiment_response(
        symbol=normalized_symbol,
        analysis=analysis,
        data_state=data_state,
        status_message=status_message,
    )


@router.get("/bot/symbol-sentiment", response_model=SymbolSentimentResponse)
def get_symbol_sentiment(
    symbol: Annotated[str, Query(min_length=1)],
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
    settings: Annotated[Settings, Depends(get_settings_dependency)],
    service: Annotated[SymbolSentimentService, Depends(get_symbol_sentiment_service)],
) -> SymbolSentimentResponse:
    """Return symbol-scoped sentiment intelligence for the workstation."""

    normalized_symbol = symbol.strip().upper()
    runtime_status = runtime.status()
    try:
        repository = StorageRepository(settings.database_url)
    except Exception:
        LOGGER.exception("Failed to open storage while reading symbol sentiment for %s.", normalized_symbol)
        return _to_symbol_sentiment_response(
            symbol=normalized_symbol,
            analysis=None,
            data_state="degraded_storage",
            status_message="Symbol sentiment storage is unavailable.",
        )
    try:
        analysis, analysis_failed = _safe_symbol_sentiment(
            service,
            symbol=normalized_symbol,
            runtime=runtime,
            repository=repository,
        )
        data_state, status_message = _derive_symbol_sentiment_data_state(
            symbol=normalized_symbol,
            status=runtime_status,
            analysis=analysis,
            analysis_failed=analysis_failed,
        )
    finally:
        repository.close()
    return _to_symbol_sentiment_response(
        symbol=normalized_symbol,
        analysis=analysis,
        data_state=data_state,
        status_message=status_message,
    )


@router.get("/bot/fusion-signal", response_model=FusionSignalResponse)
def get_fusion_signal(
    symbol: Annotated[str, Query(min_length=1)],
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
    settings: Annotated[Settings, Depends(get_settings_dependency)],
    sentiment_service: Annotated[SymbolSentimentService, Depends(get_symbol_sentiment_service)],
) -> FusionSignalResponse:
    """Return the unified advisory fusion signal for one symbol."""

    normalized_symbol = symbol.strip().upper()
    runtime_status = runtime.status()
    repository: StorageRepository | None = None
    try:
        repository = StorageRepository(settings.database_url)
    except Exception:
        LOGGER.exception("Failed to open storage while reading fusion signal for %s.", normalized_symbol)

    try:
        analysis, analysis_failed = _safe_fusion_signal(
            symbol=normalized_symbol,
            runtime=runtime,
            repository=repository,
            sentiment_service=sentiment_service,
        )
        data_state, status_message = _derive_fusion_data_state(
            symbol=normalized_symbol,
            status=runtime_status,
            analysis=analysis,
            analysis_failed=analysis_failed,
        )
    finally:
        if repository is not None:
            repository.close()
    return _to_fusion_signal_response(
        symbol=normalized_symbol,
        analysis=analysis,
        data_state=data_state,
        status_message=status_message,
    )


@router.get("/bot/ai-signal", response_model=AISignalResponse | None)
def get_ai_signal(
    symbol: Annotated[str, Query(min_length=1)],
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
    settings: Annotated[Settings, Depends(get_settings_dependency)],
) -> AISignalResponse | None:
    """Return the AI advisory signal for the selected symbol when available."""

    normalized_symbol = symbol.strip().upper()
    state, _, _ = _safe_workstation_state(runtime, normalized_symbol)
    if state.ai_signal is None:
        try:
            repository = StorageRepository(settings.database_url)
        except Exception:
            LOGGER.exception("Failed to open storage while reading AI signal for %s.", normalized_symbol)
            return None
        try:
            latest_snapshot = repository.get_latest_ai_signal(normalized_symbol)
        except Exception:
            LOGGER.exception("Failed to read AI signal history for %s.", normalized_symbol)
            latest_snapshot = None
        finally:
            repository.close()
        if latest_snapshot is None:
            return None
        return _to_ai_signal_response(
            symbol=latest_snapshot.symbol,
            timestamp=latest_snapshot.timestamp,
            bias=latest_snapshot.bias,
            confidence=latest_snapshot.confidence,
            entry_signal=latest_snapshot.entry_signal,
            exit_signal=latest_snapshot.exit_signal,
            suggested_action=latest_snapshot.suggested_action,
            explanation=latest_snapshot.explanation,
            candle_count=latest_snapshot.feature_summary.candle_count,
            close_price=latest_snapshot.feature_summary.close_price,
            volatility_pct=latest_snapshot.feature_summary.volatility_pct,
            momentum=latest_snapshot.feature_summary.momentum,
            volume_change_pct=latest_snapshot.feature_summary.volume_change_pct,
            volume_spike_ratio=latest_snapshot.feature_summary.volume_spike_ratio,
            spread_ratio=latest_snapshot.feature_summary.spread_ratio,
            microstructure_healthy=latest_snapshot.feature_summary.microstructure_healthy,
            momentum_persistence=latest_snapshot.feature_summary.momentum_persistence,
            direction_flip_rate=latest_snapshot.feature_summary.direction_flip_rate,
            structure_quality=latest_snapshot.feature_summary.structure_quality,
            recent_false_positive_rate_5m=latest_snapshot.feature_summary.recent_false_positive_rate_5m,
            regime=latest_snapshot.feature_summary.regime or "insufficient_data",
            noise_level=latest_snapshot.feature_summary.noise_level or "unknown",
            abstain=latest_snapshot.feature_summary.abstain,
            low_confidence=latest_snapshot.feature_summary.low_confidence,
            confirmation_needed=latest_snapshot.feature_summary.confirmation_needed,
            preferred_horizon=latest_snapshot.feature_summary.preferred_horizon,
            weakening_factors=latest_snapshot.feature_summary.weakening_factors,
            horizons=[
                AIHorizonResponse(
                    horizon=horizon,
                    bias=str(data.get("bias", "sideways")),
                    confidence=int(data.get("confidence", latest_snapshot.confidence)),
                    suggested_action=str(data.get("suggested_action", latest_snapshot.suggested_action)),
                    abstain=bool(data.get("abstain", False)),
                    confirmation_needed=bool(data.get("confirmation_needed", False)),
                    explanation=str(data.get("explanation", latest_snapshot.explanation)),
                )
                for horizon, data in (latest_snapshot.feature_summary.horizons or {}).items()
            ],
        )
    workstation_status = runtime.status()
    workstation_data_state, workstation_status_message = _derive_workstation_data_state(
        state=state,
        status=workstation_status,
        storage_degraded=runtime.storage_degraded(),
        storage_message=runtime.storage_status_message(),
        state_failed=False,
        state_failure_message=None,
    )
    workstation = _to_workstation_response(
        state=state,
        runtime=runtime,
        status=workstation_status,
        data_state=workstation_data_state,
        status_message=workstation_status_message,
    )
    return workstation.ai_signal


@router.get("/bot/ai-signal/history", response_model=AISignalHistoryResponse)
def get_ai_signal_history(
    symbol: Annotated[str, Query(min_length=1)],
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
    settings: Annotated[Settings, Depends(get_settings_dependency)],
    start_date: date | None = None,
    end_date: date | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AISignalHistoryResponse:
    """Return paginated AI advisory history for one symbol."""

    normalized_symbol = symbol.strip().upper()
    runtime_status = runtime.status()
    try:
        repository = StorageRepository(settings.database_url)
    except Exception:
        LOGGER.exception("Failed to open storage while reading AI history for %s.", normalized_symbol)
        return _empty_ai_signal_history_response(
            limit=limit,
            offset=offset,
            data_state="degraded_storage",
            status_message="Persisted AI history storage is unavailable.",
        )
    try:
        items = repository.get_ai_signal_history(
            symbol=normalized_symbol,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )
        total = repository.count_ai_signal_history(
            symbol=normalized_symbol,
            start_date=start_date,
            end_date=end_date,
        )
    except Exception:
        LOGGER.exception("Failed to read AI history for %s.", normalized_symbol)
        repository.close()
        return _empty_ai_signal_history_response(
            limit=limit,
            offset=offset,
            data_state="degraded_storage",
            status_message="Persisted AI history is temporarily unavailable.",
        )
    data_state, status_message = _derive_history_data_state(
        symbol=normalized_symbol,
        status=runtime_status,
        has_items=total > 0,
        storage_degraded=repository.optional_storage_degraded,
        storage_message=repository.optional_storage_message,
    )
    repository.close()
    return AISignalHistoryResponse(
        items=[
            _to_ai_signal_response(
                symbol=item.symbol,
                timestamp=item.timestamp,
                bias=item.bias,
                confidence=item.confidence,
                entry_signal=item.entry_signal,
                exit_signal=item.exit_signal,
                suggested_action=item.suggested_action,
                explanation=item.explanation,
                candle_count=item.feature_summary.candle_count,
                close_price=item.feature_summary.close_price,
                volatility_pct=item.feature_summary.volatility_pct,
                momentum=item.feature_summary.momentum,
                volume_change_pct=item.feature_summary.volume_change_pct,
                volume_spike_ratio=item.feature_summary.volume_spike_ratio,
                spread_ratio=item.feature_summary.spread_ratio,
                microstructure_healthy=item.feature_summary.microstructure_healthy,
                momentum_persistence=item.feature_summary.momentum_persistence,
                direction_flip_rate=item.feature_summary.direction_flip_rate,
                structure_quality=item.feature_summary.structure_quality,
                recent_false_positive_rate_5m=item.feature_summary.recent_false_positive_rate_5m,
                regime=item.feature_summary.regime or "insufficient_data",
                noise_level=item.feature_summary.noise_level or "unknown",
                abstain=item.feature_summary.abstain,
                low_confidence=item.feature_summary.low_confidence,
                confirmation_needed=item.feature_summary.confirmation_needed,
                preferred_horizon=item.feature_summary.preferred_horizon,
                weakening_factors=item.feature_summary.weakening_factors,
                horizons=[
                    AIHorizonResponse(
                        horizon=horizon,
                        bias=str(data.get("bias", "sideways")),
                        confidence=int(data.get("confidence", item.confidence)),
                        suggested_action=str(data.get("suggested_action", item.suggested_action)),
                        abstain=bool(data.get("abstain", False)),
                        confirmation_needed=bool(data.get("confirmation_needed", False)),
                        explanation=str(data.get("explanation", item.explanation)),
                    )
                    for horizon, data in (item.feature_summary.horizons or {}).items()
                ],
            )
            for item in items
        ],
        total=total,
        limit=limit,
        offset=offset,
        data_state=data_state,
        status_message=status_message,
    )


@router.get("/bot/ai-signal/evaluation", response_model=AIOutcomeEvaluationResponse)
def get_ai_signal_evaluation(
    symbol: Annotated[str, Query(min_length=1)],
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
    settings: Annotated[Settings, Depends(get_settings_dependency)],
) -> AIOutcomeEvaluationResponse:
    """Return symbol-scoped AI advisory outcome validation metrics."""

    normalized_symbol = symbol.strip().upper()
    runtime_status = runtime.status()
    try:
        repository = StorageRepository(settings.database_url)
    except Exception:
        LOGGER.exception("Failed to open storage while evaluating AI outcomes for %s.", normalized_symbol)
        return _empty_ai_outcome_evaluation_response(
            normalized_symbol,
            data_state="degraded_storage",
            status_message="AI outcome validation storage is unavailable.",
        )
    try:
        evaluation = AIOutcomeEvaluator(repository).evaluate(symbol=normalized_symbol)
    except Exception:
        LOGGER.exception("Failed to evaluate AI outcomes for %s.", normalized_symbol)
        repository.close()
        return _empty_ai_outcome_evaluation_response(
            normalized_symbol,
            data_state="degraded_storage",
            status_message="AI outcome validation is temporarily unavailable.",
        )
    data_state, status_message = _derive_evaluation_data_state(
        symbol=normalized_symbol,
        status=runtime_status,
        has_samples=any(item.sample_size > 0 for item in evaluation.horizons),
        storage_degraded=repository.optional_storage_degraded,
        storage_message=repository.optional_storage_message,
    )
    repository.close()
    return _to_ai_outcome_evaluation_response(
        symbol=evaluation.symbol,
        generated_at=evaluation.generated_at,
        horizons=evaluation.horizons,
        recent_samples=evaluation.recent_samples,
        data_state=data_state,
        status_message=status_message,
    )
