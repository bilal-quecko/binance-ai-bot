"""FastAPI endpoints for paper-bot symbol discovery and runtime control."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
import json
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
    RegimeAnalysisService,
    RegimeAnalysisSnapshot,
    SymbolSentimentSnapshot,
    SymbolSentimentService,
    TechnicalAnalysisService,
    TechnicalAnalysisSnapshot,
    TimeframeTechnicalSummary,
    normalize_horizon,
)
from app.ai.evaluation import AIOutcomeEvaluator
from app.ai.service import AISignalService
from app.bot import BotStatus, PaperBotRuntime, WorkstationState
from app.bot.runtime import PersistenceState
from app.config import Settings, get_settings
from app.data import MarketContextService
from app.features.feature_store import FeatureEngine
from app.features.models import FeatureConfig, FeatureSnapshot
from app.exchange.symbol_service import SpotSymbolRecord, SpotSymbolService
from app.fusion import FusionInputs, FusionSignalSnapshot, UnifiedSignalFusionEngine
from app.market_data.candles import Candle
from app.runner.models import ManualTradeResult, TradeReadiness, TradingProfile
from app.services import HistoricalBackfillService
from app.storage import StorageRepository
from app.storage.candle_repository import CandleBackfillStatus, CandleRepository, merge_candles
from app.storage.models import (
    HistoricalCandleRecord,
    MarketCandleSnapshotRecord,
    SignalValidationSnapshotRecord,
)
from app.monitoring.similar_setups import (
    SimilarSetupReport,
    build_similar_setup_report,
    descriptor_from_snapshot,
)
from app.monitoring.signal_validation import (
    VALIDATION_HORIZONS,
    SignalValidationReport,
    build_signal_validation_report,
)
from app.monitoring.trade_eligibility import (
    TradeEligibilityInput,
    TradeEligibilityResult,
    evaluate_trade_eligibility,
)

router = APIRouter()
LOGGER = logging.getLogger(__name__)

DataState = Literal["ready", "waiting_for_runtime", "waiting_for_history", "degraded_storage"]
ChartTimeframe = Literal["1m", "5m", "15m", "1h"]


@dataclass(slots=True)
class SignalAnalysisContext:
    """Shared per-request signal-analysis inputs for one selected symbol."""

    symbol: str
    candles: list[Candle]
    feature_snapshot: FeatureSnapshot | None
    technical_analysis: TechnicalAnalysisSnapshot | None
    market_sentiment: MarketSentimentSnapshot | None
    symbol_sentiment: SymbolSentimentSnapshot | None
    benchmark_candles: list[Candle]


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
    trading_profile: TradingProfile = "balanced"


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
    trading_profile: TradingProfile = "balanced"
    tuning_version_id: str | None = None
    baseline_tuning_version_id: str | None = None
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


class CandleHistoryResponse(BaseModel):
    """Symbol-scoped candle-history payload for the workstation chart."""

    symbol: str
    timeframe: ChartTimeframe
    source_timeframe: str
    derived_from_lower_timeframe: bool
    data_state: DataState
    status_message: str | None = None
    candles: list[CandleSummaryResponse] = Field(default_factory=list)
    current_price: Decimal | None = None


class BackfillStatusResponse(BaseModel):
    """Historical backfill coverage state for one selected symbol."""

    symbol: str
    requested_interval: ChartTimeframe
    requested_lookback_days: int
    available_from: datetime | None = None
    available_to: datetime | None = None
    candle_count: int
    coverage_pct: Decimal
    status: str
    message: str
    last_backfilled_at: datetime | None = None
    effective_interval: ChartTimeframe | None = None


class SimilarSetupHorizonResponse(BaseModel):
    """Compact similar-setup horizon metrics for workstation reads."""

    horizon: str
    sample_size: int
    win_rate_pct: Decimal | None = None
    expectancy_pct: Decimal | None = None
    average_favorable_move_pct: Decimal | None = None
    average_adverse_move_pct: Decimal | None = None


class SimilarSetupSummaryResponse(BaseModel):
    """Compact similar historical setup outcome payload."""

    status: str
    reliability_label: str
    matching_sample_size: int
    best_horizon: str | None = None
    horizons: list[SimilarSetupHorizonResponse] = Field(default_factory=list)
    explanation: str
    matched_attributes: list[str] = Field(default_factory=list)


class TradingAssistantResponse(BaseModel):
    """Beginner-friendly symbol decision summary."""

    symbol: str
    decision: Literal["buy", "sell_exit", "wait", "avoid"]
    confidence_label: Literal["low", "medium", "high"]
    confidence_score: int
    risk_label: Literal["low", "medium", "high"]
    best_timeframe: Literal["5m", "15m", "1h", "unknown"]
    simple_reason: str
    why_not_trade: str | None = None
    suggested_entry_zone: str | None = None
    suggested_stop_loss: Decimal | None = None
    suggested_take_profit: Decimal | None = None
    data_state: DataState
    backfill_status: BackfillStatusResponse
    similar_setup: SimilarSetupSummaryResponse | None = None


class TradeEligibilityResponse(BaseModel):
    """Advisory-only paper automation eligibility result."""

    symbol: str
    status: Literal["eligible", "not_eligible", "watch_only", "insufficient_data"]
    evidence_strength: Literal["insufficient", "weak", "mixed", "promising", "strong"]
    reason: str
    required_confirmations: list[str] = Field(default_factory=list)
    minimum_confidence_threshold: int
    preferred_horizon: str | None = None
    conditions_to_avoid: list[str] = Field(default_factory=list)
    blocker_summary: str
    similar_setup_summary: str
    regime_summary: str
    fee_slippage_summary: str
    warnings: list[str] = Field(default_factory=list)
    paper_only: bool = True
    advisory_only: bool = True
    live_trading_enabled: bool = False
    futures_enabled: bool = False


class OpportunityResponse(BaseModel):
    """Advisory opportunity-scan result for one Spot symbol."""

    symbol: str
    score: int
    suggested_action: Literal["watch", "possible_buy", "avoid"]
    confidence: Literal["low", "medium", "high"]
    volatility_label: str
    momentum_label: str
    liquidity_label: str
    risk_label: Literal["low", "medium", "high"]
    reason: str
    data_state: DataState


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
    trading_profile: TradingProfile = "balanced"
    enough_candle_history: bool
    deterministic_entry_signal: bool
    deterministic_exit_signal: bool
    risk_ready: bool
    risk_blocked: bool
    broker_ready: bool
    next_action: str
    reason_if_not_trading: str | None = None
    blocking_reasons: tuple[str, ...] = ()
    signal_reason_codes: tuple[str, ...] = ()
    risk_reason_codes: tuple[str, ...] = ()
    expected_edge_pct: Decimal | None = None
    estimated_round_trip_cost_pct: Decimal | None = None


class ManualTradeRequest(BaseModel):
    """Manual paper-trade request payload."""

    symbol: str = Field(min_length=1)


class ManualTradeResponse(BaseModel):
    """Serialized manual paper-trade result."""

    symbol: str
    action: str
    requested_side: str
    status: str
    message: str
    reason_codes: tuple[str, ...] = ()
    approved_quantity: Decimal | None = None
    filled_quantity: Decimal | None = None
    fill_price: Decimal | None = None
    current_position_quantity: Decimal = Decimal("0")
    current_position_open: bool = False
    current_pnl: Decimal = Decimal("0")


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


class RegimeAnalysisResponse(BaseModel):
    """Symbol-scoped deterministic regime analysis payload."""

    symbol: str
    horizon: str
    generated_at: datetime | None = None
    data_state: DataState
    status_message: str | None = None
    regime_label: str | None = None
    confidence: int = 0
    supporting_evidence: list[str] = Field(default_factory=list)
    risk_warnings: list[str] = Field(default_factory=list)
    preferred_trading_behavior: str | None = None
    avoid_conditions: list[str] = Field(default_factory=list)


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


def _build_signal_analysis_context(
    *,
    runtime: PaperBotRuntime,
    repository: StorageRepository,
    symbol: str,
    sentiment_service: SymbolSentimentService,
) -> SignalAnalysisContext:
    """Build shared signal-analysis inputs once for one selected symbol request."""

    candles = _load_merged_candles(
        repository=repository,
        runtime=runtime,
        symbol=symbol,
        interval="1m",
    )
    feature_snapshot = _build_feature_snapshot_from_history(
        runtime=runtime,
        symbol=symbol,
        candles=candles,
    )
    technical_analysis = (
        runtime.technical_analysis(symbol)
        if runtime.status().symbol == symbol and runtime.technical_analysis(symbol) is not None
        else TechnicalAnalysisService().analyze(
            symbol=symbol,
            candles=candles,
            feature_snapshot=feature_snapshot,
        )
    )
    market_sentiment = MarketSentimentService().analyze(
        symbol=symbol,
        symbol_points=MarketContextService(
            repository=repository,
            runtime=runtime,
        ).load_market_context(selected_symbol=symbol),
    )
    benchmark_candles = _load_merged_candles(
        repository=repository,
        runtime=runtime,
        symbol="BTCUSDT",
        interval="1m",
    )
    symbol_sentiment = sentiment_service.analyze(
        symbol=symbol,
        candles=candles,
        benchmark_symbol="BTCUSDT" if benchmark_candles else None,
        benchmark_closes=[candle.close for candle in benchmark_candles[-24:]],
    )
    return SignalAnalysisContext(
        symbol=symbol,
        candles=candles,
        feature_snapshot=feature_snapshot,
        technical_analysis=technical_analysis,
        market_sentiment=market_sentiment,
        symbol_sentiment=symbol_sentiment,
        benchmark_candles=benchmark_candles,
    )


def _safe_technical_analysis(
    runtime: PaperBotRuntime,
    repository: StorageRepository,
    symbol: str,
    context: SignalAnalysisContext | None = None,
) -> tuple[TechnicalAnalysisSnapshot | None, bool]:
    """Return technical analysis without allowing runtime failures to escape the API."""

    try:
        if context is not None:
            return (context.technical_analysis, False)
        candles = _load_merged_candles(repository=repository, runtime=runtime, symbol=symbol, interval="1m")
        feature_snapshot = _build_feature_snapshot_from_history(runtime=runtime, symbol=symbol, candles=candles)
        return (
            runtime.technical_analysis(symbol)
            if runtime.status().symbol == symbol and runtime.technical_analysis(symbol) is not None
            else TechnicalAnalysisService().analyze(
                symbol=symbol,
                candles=candles,
                feature_snapshot=feature_snapshot,
            ),
            False,
        )
    except Exception:
        LOGGER.exception("Failed to build technical analysis for symbol %s.", symbol)
        return None, True


def _safe_pattern_analysis(
    runtime: PaperBotRuntime,
    *,
    symbol: str,
    horizon: str,
    repository: StorageRepository,
    candles: list[Candle] | None = None,
) -> tuple[PatternAnalysisSnapshot | None, bool]:
    """Return pattern analysis without allowing runtime errors to escape the API."""

    try:
        source_candles = candles or _load_merged_candles(
            repository=repository,
            runtime=runtime,
            symbol=symbol,
            interval="1m",
        )
        merged_points = [_to_pattern_point_from_candle(candle) for candle in source_candles]
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
    context: SignalAnalysisContext | None = None,
) -> tuple[SymbolSentimentSnapshot | None, bool]:
    """Return symbol sentiment without allowing source/service errors to escape the API."""

    try:
        if context is not None:
            return (context.symbol_sentiment, False)
        symbol_candles = _load_merged_candles(repository=repository, runtime=runtime, symbol=symbol, interval="1m")
        benchmark_candles = _load_merged_candles(repository=repository, runtime=runtime, symbol="BTCUSDT", interval="1m")
        return (
            service.analyze(
                symbol=symbol,
                candles=symbol_candles,
                benchmark_symbol="BTCUSDT" if benchmark_candles else None,
                benchmark_closes=[candle.close for candle in benchmark_candles[-24:]],
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
    workstation_state: WorkstationState | None = None,
    context: SignalAnalysisContext | None = None,
) -> tuple[FusionSignalSnapshot | None, bool]:
    """Return a fused advisory signal without allowing optional dependencies to escape the API."""

    try:
        if workstation_state is None:
            workstation_state, _, _ = _safe_workstation_state(runtime, symbol)
        if repository is not None:
            if context is None:
                context = _build_signal_analysis_context(
                    runtime=runtime,
                    repository=repository,
                    symbol=symbol,
                    sentiment_service=sentiment_service,
                )
            merged_candles = context.candles
            technical_analysis = context.technical_analysis
            feature_snapshot = context.feature_snapshot
        else:
            merged_candles = runtime.candle_history(symbol)
            technical_analysis = runtime.technical_analysis(symbol)
            feature_snapshot = None
        if repository is not None:
            pattern_analysis, _ = _safe_pattern_analysis(
                runtime,
                symbol=symbol,
                horizon="7d",
                repository=repository,
                candles=merged_candles,
            )
            symbol_sentiment = context.symbol_sentiment if context is not None else None
            ai_signal = workstation_state.ai_signal
            if ai_signal is None and feature_snapshot is not None:
                ai_signal = AISignalService().build_signal(
                    symbol=symbol,
                    candles=merged_candles,
                    feature_snapshot=feature_snapshot,
                    top_of_book=(getattr(runtime, "top_of_book")(symbol) if callable(getattr(runtime, "top_of_book", None)) else None),
                    technical_analysis=technical_analysis,
                    market_sentiment=context.market_sentiment if context is not None else None,
                )
        else:
            pattern_analysis = HorizonPatternAnalysisService().analyze(
                symbol=symbol,
                horizon="7d",
                points=[
                    _to_pattern_point_from_candle(candle)
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
            ai_signal = workstation_state.ai_signal
        return (
            UnifiedSignalFusionEngine().build_signal(
                FusionInputs(
                    symbol=symbol,
                    technical_analysis=technical_analysis,
                    pattern_analysis=pattern_analysis,
                    ai_signal=ai_signal,
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


def _safe_regime_analysis(
    *,
    symbol: str,
    horizon: str,
    runtime: PaperBotRuntime,
    repository: StorageRepository,
    sentiment_service: SymbolSentimentService,
    context: SignalAnalysisContext | None = None,
) -> tuple[RegimeAnalysisSnapshot | None, bool]:
    """Return regime analysis without allowing optional dependencies to escape the API."""

    try:
        if context is None:
            context = _build_signal_analysis_context(
                runtime=runtime,
                repository=repository,
                symbol=symbol,
                sentiment_service=sentiment_service,
            )
        pattern_analysis, _ = _safe_pattern_analysis(
            runtime,
            symbol=symbol,
            horizon=horizon,
            repository=repository,
            candles=context.candles,
        )
        return (
            RegimeAnalysisService().analyze(
                symbol=symbol,
                horizon=horizon,
                candles=context.candles,
                technical_analysis=context.technical_analysis,
                pattern_analysis=pattern_analysis,
                feature_snapshot=context.feature_snapshot,
            ),
            False,
        )
    except Exception:
        LOGGER.exception("Failed to build regime analysis for symbol %s horizon %s.", symbol, horizon)
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
    if analysis is not None and analysis.data_state != "incomplete":
        return ("ready", analysis.status_message or f"Technical analysis is ready for {symbol}.")
    if not _runtime_matches_symbol(status, symbol):
        return (
            "waiting_for_history",
            analysis.status_message
            if analysis is not None
            else f"Technical analysis for {symbol} is waiting for stored or live candle history.",
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


def _derive_regime_analysis_data_state(
    *,
    symbol: str,
    status: BotStatus,
    analysis: RegimeAnalysisSnapshot | None,
    analysis_failed: bool,
    storage_degraded: bool,
    storage_message: str | None,
) -> tuple[DataState, str]:
    """Derive a symbol-scoped regime-analysis readiness state."""

    if analysis_failed or storage_degraded:
        return (
            "degraded_storage",
            storage_message or f"Regime analysis for {symbol} is temporarily unavailable.",
        )
    if analysis is None:
        return (
            "waiting_for_runtime" if not _runtime_matches_symbol(status, symbol) else "waiting_for_history",
            (
                f"Start the runtime for {symbol} or backfill history to classify market regime."
                if not _runtime_matches_symbol(status, symbol)
                else f"Regime analysis for {symbol} needs more closed candles."
            ),
        )
    if analysis.data_state != "ready":
        return ("waiting_for_history", analysis.status_message or f"Regime analysis for {symbol} needs more history.")
    return ("ready", analysis.status_message or f"Regime analysis is ready for {symbol}.")


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
            "waiting_for_history",
            analysis.status_message or f"Market sentiment for {symbol} needs more history.",
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
    if analysis.data_state != "incomplete":
        return (
            "ready",
            analysis.status_message or f"Symbol sentiment is ready for {symbol}.",
        )
    if analysis.data_state == "incomplete":
        return (
            "waiting_for_history",
            analysis.status_message or f"Symbol sentiment for {symbol} still needs more stored or live history.",
        )
    return ("ready", analysis.status_message or f"Symbol sentiment is ready for {symbol}.")


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
    if analysis.data_state != "incomplete":
        return ("ready", analysis.status_message or f"Fusion signal is ready for {symbol}.")
    if analysis.data_state == "incomplete":
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


def get_backfill_service(request: Request) -> HistoricalBackfillService:
    """Return the shared historical backfill service from app state."""

    if hasattr(request.app.state, "backfill_service"):
        return request.app.state.backfill_service

    class _StorageOnlyBackfillService:
        async def ensure_recent_history(self, *, symbol: str, interval: ChartTimeframe = "1m", lookback_days: int = 7, force: bool = False):
            repository = StorageRepository(get_settings().database_url)
            try:
                return CandleRepository(repository).status(
                    symbol=symbol,
                    interval=interval,
                    lookback_days=lookback_days,
                )
            finally:
                repository.close()

        def status(self, *, symbol: str, interval: ChartTimeframe = "1m", lookback_days: int = 7):
            repository = StorageRepository(get_settings().database_url)
            try:
                return CandleRepository(repository).status(
                    symbol=symbol,
                    interval=interval,
                    lookback_days=lookback_days,
                )
            finally:
                repository.close()

    return _StorageOnlyBackfillService()  # type: ignore[return-value]


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


def _feature_engine() -> FeatureEngine:
    """Build the shared feature-engine shape used by analysis endpoints."""

    return FeatureEngine(
        FeatureConfig(
            ema_fast_period=3,
            ema_slow_period=5,
            rsi_period=3,
            atr_period=3,
        )
    )


def _load_merged_candles(
    *,
    repository: StorageRepository,
    runtime: PaperBotRuntime,
    symbol: str,
    interval: ChartTimeframe = "1m",
    limit: int | None = None,
) -> list[Candle]:
    """Load stored candle history first, then merge live runtime candles on top."""

    return _load_merged_candle_series(
        repository=repository,
        runtime=runtime,
        symbol=symbol,
        interval=interval,
        limit=limit,
    ).candles


def _load_merged_candle_series(
    *,
    repository: StorageRepository,
    runtime: PaperBotRuntime,
    symbol: str,
    interval: ChartTimeframe = "1m",
    limit: int | None = None,
):
    """Load stored candle history first, then merge live runtime candles on top."""

    candle_repository = CandleRepository(repository)
    stored = candle_repository.load(symbol=symbol, interval="1m")
    live = runtime.candle_history(symbol) if _runtime_matches_symbol(runtime.status(), symbol) else []
    return merge_candles(
        stored_candles=stored,
        live_candles=live,
        interval=interval,
        limit=limit,
    )


def _build_feature_snapshot_from_history(
    *,
    runtime: PaperBotRuntime,
    symbol: str,
    candles: list[Candle],
) -> FeatureSnapshot | None:
    """Build a feature snapshot from merged stored/live candles when enough history exists."""

    if len(candles) < 5:
        return None
    top_of_book_getter = getattr(runtime, "top_of_book", None)
    top_of_book = top_of_book_getter(symbol) if callable(top_of_book_getter) else None
    try:
        return _feature_engine().build_snapshot(candles, top_of_book=top_of_book)
    except ValueError:
        return None


def _to_pattern_point_from_candle(candle: Candle) -> PatternPricePoint:
    """Convert a full candle into the close-price point used by pattern analysis."""

    return PatternPricePoint(
        symbol=candle.symbol,
        timestamp=candle.close_time,
        close_price=candle.close,
    )


def _to_backfill_status_response(status: CandleBackfillStatus) -> BackfillStatusResponse:
    """Serialize one backfill status for the workstation."""

    return BackfillStatusResponse(
        symbol=status.symbol,
        requested_interval=status.requested_interval,
        requested_lookback_days=status.requested_lookback_days,
        available_from=status.available_from,
        available_to=status.available_to,
        candle_count=status.candle_count,
        coverage_pct=status.coverage_pct,
        status=status.status,
        message=status.message,
        last_backfilled_at=status.last_backfilled_at,
        effective_interval=status.effective_interval,
    )


def _build_ai_signal_from_history(
    *,
    symbol: str,
    runtime: PaperBotRuntime,
    repository: StorageRepository,
    context: SignalAnalysisContext | None = None,
) -> AISignalResponse | None:
    """Build an advisory AI snapshot from stored candles plus any live edge state."""

    candles = context.candles if context is not None else _load_merged_candles(
        repository=repository,
        runtime=runtime,
        symbol=symbol,
        interval="1m",
    )
    feature_snapshot = context.feature_snapshot if context is not None else _build_feature_snapshot_from_history(
        runtime=runtime,
        symbol=symbol,
        candles=candles,
    )
    if feature_snapshot is None:
        return None

    technical = context.technical_analysis if context is not None else TechnicalAnalysisService().analyze(
        symbol=symbol,
        candles=candles,
        feature_snapshot=feature_snapshot,
    )
    market_sentiment = context.market_sentiment if context is not None else MarketSentimentService().analyze(
        symbol=symbol,
        symbol_points=MarketContextService(repository=repository, runtime=runtime).load_market_context(
            selected_symbol=symbol
        ),
    )
    evaluation = AIOutcomeEvaluator(repository).evaluate(symbol=symbol)
    summary_5m = next((item for item in evaluation.horizons if item.horizon == "5m"), None)
    ai_signal = AISignalService().build_signal(
        symbol=symbol,
        candles=candles,
        feature_snapshot=feature_snapshot,
        top_of_book=(getattr(runtime, "top_of_book")(symbol) if callable(getattr(runtime, "top_of_book", None)) else None),
        technical_analysis=technical,
        market_sentiment=market_sentiment,
        recent_false_positive_rate_5m=(summary_5m.false_positive_rate_pct if summary_5m is not None else None),
        recent_false_reversal_rate_5m=(summary_5m.false_reversal_rate_pct if summary_5m is not None else None),
    )
    return _to_ai_signal_response(
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
                horizon=horizon_signal.horizon,
                bias=horizon_signal.bias,
                confidence=horizon_signal.confidence,
                suggested_action=horizon_signal.suggested_action,
                abstain=horizon_signal.abstain,
                confirmation_needed=horizon_signal.confirmation_needed,
                explanation=horizon_signal.explanation,
            )
            for horizon_signal in ai_signal.horizon_signals
        ],
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
        trading_profile=status.trading_profile,
        tuning_version_id=status.tuning_version_id,
        baseline_tuning_version_id=status.baseline_tuning_version_id,
        persistence=persistence,
    )


def _to_candle_history_response(
    *,
    symbol: str,
    timeframe: ChartTimeframe,
    candles: list[Candle],
    source_timeframe: str,
    derived_from_lower_timeframe: bool,
    runtime_active: bool,
    limit: int,
) -> CandleHistoryResponse:
    """Convert merged stored/live candle history into a workstation chart response."""

    normalized_symbol = symbol.upper()
    limited_candles = candles[-limit:]

    if limited_candles:
        minimum_ready_candles = 8 if timeframe != "1m" else 20
        return CandleHistoryResponse(
            symbol=normalized_symbol,
            timeframe=timeframe,
            source_timeframe=source_timeframe,
            derived_from_lower_timeframe=derived_from_lower_timeframe,
            data_state="ready" if len(limited_candles) >= min(limit, minimum_ready_candles) else "waiting_for_history",
            status_message=(
                None
                if len(limited_candles) >= min(limit, minimum_ready_candles)
                else (
                    f"Chart is using {len(limited_candles)} closed candles for {normalized_symbol}. "
                    "More history will improve structure and annotation quality."
                )
            ),
            candles=[
                CandleSummaryResponse(
                    timeframe=timeframe,
                    open_time=candle.open_time,
                    close_time=candle.close_time,
                    open=candle.open,
                    high=candle.high,
                    low=candle.low,
                    close=candle.close,
                    volume=candle.volume,
                    is_closed=candle.is_closed,
                )
                for candle in limited_candles
            ],
            current_price=limited_candles[-1].close,
        )

    return CandleHistoryResponse(
        symbol=normalized_symbol,
        timeframe=timeframe,
        source_timeframe=source_timeframe,
        derived_from_lower_timeframe=derived_from_lower_timeframe,
        data_state="waiting_for_history",
        status_message=(
            (
                f"Historical candles for {normalized_symbol} are still loading for the {timeframe} chart."
                if runtime_active
                else f"Historical candle backfill has not produced enough {timeframe} candles for {normalized_symbol} yet."
            )
        ),
        candles=[],
        current_price=None,
    )


def _default_trade_readiness_response(symbol: str, status: BotStatus) -> TradeReadinessResponse:
    """Return a neutral deterministic readiness payload for one symbol."""

    runtime_active = status.symbol == symbol and status.state in {"running", "paused"}
    return TradeReadinessResponse(
        selected_symbol=symbol,
        runtime_active=runtime_active,
        mode=status.mode,
        trading_profile=status.trading_profile,
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
        blocking_reasons=(
            (status.recovery_message,)
            if status.recovered_from_prior_session and status.symbol == symbol and status.mode == "paused"
            else (
                ("Start the live runtime to receive live candles and order-book data.",)
                if not runtime_active
                else ("Need more closed candles before deterministic entries and exits can activate.",)
            )
        ),
        signal_reason_codes=(),
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
        trading_profile=readiness.trading_profile,
        enough_candle_history=readiness.enough_candle_history,
        deterministic_entry_signal=readiness.deterministic_entry_signal,
        deterministic_exit_signal=readiness.deterministic_exit_signal,
        risk_ready=readiness.risk_ready,
        risk_blocked=readiness.risk_blocked,
        broker_ready=readiness.broker_ready,
        next_action=next_action,
        reason_if_not_trading=reason_if_not_trading,
        blocking_reasons=readiness.blocking_reasons,
        signal_reason_codes=readiness.signal_reason_codes,
        risk_reason_codes=readiness.risk_reason_codes,
        expected_edge_pct=readiness.expected_edge_pct,
        estimated_round_trip_cost_pct=readiness.estimated_round_trip_cost_pct,
    )


def _to_manual_trade_response(result: ManualTradeResult) -> ManualTradeResponse:
    """Convert a manual paper-trade result into an API response."""

    current_position_quantity = (
        result.current_position.quantity if result.current_position is not None else Decimal("0")
    )
    return ManualTradeResponse(
        symbol=result.symbol,
        action=result.action,
        requested_side=result.requested_side,
        status=result.status,
        message=result.message,
        reason_codes=result.reason_codes,
        approved_quantity=(
            result.risk_decision.approved_quantity if result.risk_decision is not None else None
        ),
        filled_quantity=(
            result.fill_result.filled_quantity if result.fill_result is not None else None
        ),
        fill_price=result.fill_result.fill_price if result.fill_result is not None else None,
        current_position_quantity=current_position_quantity,
        current_position_open=current_position_quantity > Decimal("0"),
        current_pnl=result.current_pnl,
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


def _to_regime_analysis_response(
    *,
    symbol: str,
    horizon: str,
    analysis: RegimeAnalysisSnapshot | None,
    data_state: DataState,
    status_message: str | None,
) -> RegimeAnalysisResponse:
    """Build a stable regime-analysis API response."""

    if analysis is None:
        return RegimeAnalysisResponse(
            symbol=symbol,
            horizon=horizon,
            data_state=data_state,
            status_message=status_message,
            preferred_trading_behavior=None,
        )
    return RegimeAnalysisResponse(
        symbol=analysis.symbol,
        horizon=analysis.horizon,
        generated_at=analysis.generated_at,
        data_state=data_state,
        status_message=status_message,
        regime_label=analysis.regime_label,
        confidence=analysis.confidence,
        supporting_evidence=list(analysis.supporting_evidence),
        risk_warnings=list(analysis.risk_warnings),
        preferred_trading_behavior=analysis.preferred_trading_behavior,
        avoid_conditions=list(analysis.avoid_conditions),
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


def _confidence_label(score: int) -> Literal["low", "medium", "high"]:
    if score >= 70:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def _risk_label(value: str | None) -> Literal["low", "medium", "high"]:
    if value == "low":
        return "low"
    if value == "medium":
        return "medium"
    return "high"


def _build_trading_assistant_response(
    *,
    symbol: str,
    backfill_status: CandleBackfillStatus,
    fusion_signal: FusionSignalResponse,
    technical_analysis: TechnicalAnalysisResponse | None,
    workstation: WorkstationResponse | None,
    similar_setup: SimilarSetupReport | None = None,
) -> TradingAssistantResponse:
    """Build a beginner-friendly trading summary without changing execution logic."""

    decision: Literal["buy", "sell_exit", "wait", "avoid"] = "wait"
    why_not_trade: str | None = None
    confidence_score = fusion_signal.confidence
    simple_reason = fusion_signal.top_reasons[0] if fusion_signal.top_reasons else (
        fusion_signal.status_message or "More evidence is needed before acting."
    )
    if backfill_status.status in {"not_started", "loading"}:
        decision = "wait"
        why_not_trade = "Recent historical candles are still loading, so the decision engine does not have enough context yet."
        simple_reason = "Waiting for recent historical candles to finish loading."
    elif backfill_status.status == "failed":
        decision = "wait"
        why_not_trade = backfill_status.message
        simple_reason = "Historical backfill failed, so the trade view is incomplete."
    elif fusion_signal.data_state != "ready":
        decision = "wait"
        why_not_trade = fusion_signal.status_message or "The combined signal still needs more confirmation."
    elif fusion_signal.final_signal == "long":
        decision = "buy" if fusion_signal.confidence >= 60 else "wait"
        if decision == "wait":
            why_not_trade = "The setup leans bullish, but confidence is still too weak for a clean beginner entry."
    elif fusion_signal.final_signal == "exit_long":
        if workstation is not None and workstation.current_position is not None:
            decision = "sell_exit"
        else:
            decision = "wait"
            why_not_trade = "No open position, so no exit setup exists."
    elif fusion_signal.final_signal in {"short", "exit_short"}:
        decision = "avoid"
        why_not_trade = "The combined signal leans short, but this paper spot flow is long-only."
    elif fusion_signal.final_signal == "reduce_risk":
        decision = "avoid"
        why_not_trade = "Current volatility or signal conflict is high enough that reducing risk is better than entering now."
    else:
        decision = "wait" if fusion_signal.confidence >= 35 else "avoid"
        why_not_trade = why_not_trade or "The combined signal is too mixed to justify a clean beginner trade."

    suggested_entry_zone: str | None = None
    suggested_stop_loss: Decimal | None = None
    suggested_take_profit: Decimal | None = None
    if technical_analysis is not None and technical_analysis.data_state == "ready" and decision == "buy":
        current_price = workstation.last_price if workstation is not None else None
        nearest_support = technical_analysis.support_levels[-1] if technical_analysis.support_levels else None
        nearest_resistance = technical_analysis.resistance_levels[0] if technical_analysis.resistance_levels else None
        atr = workstation.feature.atr if workstation is not None and workstation.feature is not None else None
        if nearest_support is not None and current_price is not None:
            suggested_entry_zone = f"{nearest_support} - {current_price}"
        elif current_price is not None:
            suggested_entry_zone = str(current_price)
        if nearest_support is not None and atr is not None:
            suggested_stop_loss = nearest_support - atr
        elif atr is not None and current_price is not None:
            suggested_stop_loss = current_price - (atr * Decimal("1.5"))
        if nearest_resistance is not None:
            suggested_take_profit = nearest_resistance
        elif atr is not None and current_price is not None:
            suggested_take_profit = current_price + (atr * Decimal("2"))

    best_timeframe: Literal["5m", "15m", "1h", "unknown"] = "unknown"
    if fusion_signal.preferred_horizon in {"5m", "15m", "1h"}:
        best_timeframe = fusion_signal.preferred_horizon

    return TradingAssistantResponse(
        symbol=symbol,
        decision=decision,
        confidence_label=_confidence_label(confidence_score),
        confidence_score=confidence_score,
        risk_label=_risk_label(fusion_signal.risk_grade),
        best_timeframe=best_timeframe,
        simple_reason=simple_reason,
        why_not_trade=why_not_trade,
        suggested_entry_zone=suggested_entry_zone,
        suggested_stop_loss=suggested_stop_loss,
        suggested_take_profit=suggested_take_profit,
        data_state=(
            "ready"
            if decision in {"buy", "sell_exit"} and backfill_status.status == "ready"
            else ("waiting_for_history" if backfill_status.status in {"loading", "partial"} else fusion_signal.data_state)
        ),
        backfill_status=_to_backfill_status_response(backfill_status),
        similar_setup=_to_similar_setup_summary_response(similar_setup),
    )


def _to_similar_setup_summary_response(report: SimilarSetupReport | None) -> SimilarSetupSummaryResponse | None:
    """Convert a similar-setup report into the compact bot API payload."""

    if report is None:
        return None
    return SimilarSetupSummaryResponse(
        status=report.status,
        reliability_label=report.reliability_label,
        matching_sample_size=report.matching_sample_size,
        best_horizon=report.best_horizon,
        horizons=[
            SimilarSetupHorizonResponse(
                horizon=item.horizon,
                sample_size=item.sample_size,
                win_rate_pct=item.win_rate_pct,
                expectancy_pct=item.expectancy_pct,
                average_favorable_move_pct=item.average_favorable_move_pct,
                average_adverse_move_pct=item.average_adverse_move_pct,
            )
            for item in report.horizons
        ],
        explanation=report.explanation,
        matched_attributes=report.matched_attributes,
    )


def _to_trade_eligibility_response(
    *,
    symbol: str,
    result: TradeEligibilityResult,
) -> TradeEligibilityResponse:
    """Convert trade eligibility output into a bot API response."""

    return TradeEligibilityResponse(
        symbol=symbol,
        status=result.status,
        evidence_strength=result.evidence_strength,
        reason=result.reason,
        required_confirmations=result.required_confirmations,
        minimum_confidence_threshold=result.minimum_confidence_threshold,
        preferred_horizon=result.preferred_horizon,
        conditions_to_avoid=result.conditions_to_avoid,
        blocker_summary=result.blocker_summary,
        similar_setup_summary=result.similar_setup_summary,
        regime_summary=result.regime_summary,
        fee_slippage_summary=result.fee_slippage_summary,
        warnings=result.warnings,
    )


def _similar_setup_report_for_snapshot(
    *,
    repository: StorageRepository,
    current_snapshot: SignalValidationSnapshotRecord | None,
) -> SimilarSetupReport | None:
    """Build a compact similar-setup report for a just-persisted current signal."""

    if current_snapshot is None:
        return None
    snapshots = repository.get_signal_validation_snapshots(start_date=None, end_date=None)
    if not snapshots:
        return None
    candles_by_symbol = _candles_by_symbol_for_signal_snapshots(
        repository=repository,
        snapshots=snapshots,
    )
    return build_similar_setup_report(
        current_setup=descriptor_from_snapshot(current_snapshot),
        snapshots=snapshots,
        candles_by_symbol=candles_by_symbol,
        exclude_snapshot_id=current_snapshot.id,
    )


def _signal_validation_report_for_symbol(
    *,
    repository: StorageRepository,
    symbol: str,
    horizon: str | None,
) -> SignalValidationReport:
    """Build validation metrics for trade eligibility without changing execution state."""

    snapshots = repository.get_signal_validation_snapshots(symbol=symbol)
    candles_by_symbol = _candles_by_symbol_for_signal_snapshots(
        repository=repository,
        snapshots=snapshots,
    )
    return build_signal_validation_report(
        snapshots=snapshots,
        candles_by_symbol=candles_by_symbol,
        symbol=symbol,
        start_date=None,
        end_date=None,
        horizon=horizon,
    )


def _candles_by_symbol_for_signal_snapshots(
    *,
    repository: StorageRepository,
    snapshots: list[SignalValidationSnapshotRecord],
) -> dict[str, list[HistoricalCandleRecord]]:
    """Load forward candle windows needed to evaluate persisted signal snapshots."""

    candles_by_symbol = {}
    for symbol in sorted({snapshot.symbol for snapshot in snapshots}):
        symbol_snapshots = [snapshot for snapshot in snapshots if snapshot.symbol == symbol]
        if not symbol_snapshots:
            continue
        start_time = min(snapshot.timestamp for snapshot in symbol_snapshots)
        end_time = max(snapshot.timestamp for snapshot in symbol_snapshots) + timedelta(hours=25)
        candles_by_symbol[symbol] = repository.get_historical_candles(
            symbol=symbol,
            interval="1m",
            start_time=start_time,
            end_time=end_time,
        )
    return candles_by_symbol


def _persist_signal_validation_snapshot(
    *,
    repository: StorageRepository,
    symbol: str,
    assistant: TradingAssistantResponse,
    fusion_signal: FusionSignalResponse,
    workstation: WorkstationResponse | None,
    context: SignalAnalysisContext | None,
    pattern_analysis: PatternAnalysisSnapshot | None,
    regime_analysis: RegimeAnalysisSnapshot | None = None,
) -> SignalValidationSnapshotRecord | None:
    """Persist one validation snapshot without affecting advisory or paper execution reads."""

    snapshot = _build_signal_validation_snapshot_record(
        symbol=symbol,
        assistant=assistant,
        fusion_signal=fusion_signal,
        workstation=workstation,
        context=context,
        pattern_analysis=pattern_analysis,
        regime_analysis=regime_analysis,
    )
    if snapshot is None:
        return None
    snapshot.id = repository.insert_signal_validation_snapshot(snapshot)
    return snapshot


def _build_signal_validation_snapshot_record(
    *,
    symbol: str,
    assistant: TradingAssistantResponse,
    fusion_signal: FusionSignalResponse,
    workstation: WorkstationResponse | None,
    context: SignalAnalysisContext | None,
    pattern_analysis: PatternAnalysisSnapshot | None,
    regime_analysis: RegimeAnalysisSnapshot | None = None,
) -> SignalValidationSnapshotRecord | None:
    """Build a signal-validation snapshot record without writing it."""

    price = _snapshot_price(workstation=workstation, context=context)
    if price is None:
        return None
    readiness = workstation.trade_readiness if workstation is not None else None
    blocker_reasons: tuple[str, ...] = ()
    if readiness is not None:
        blocker_reasons = readiness.blocking_reasons
    if assistant.why_not_trade:
        blocker_reasons = tuple(dict.fromkeys((*blocker_reasons, assistant.why_not_trade)))
    signal_ignored_or_blocked = assistant.decision in {"wait", "avoid"} or bool(blocker_reasons)
    trade_opened = (
        workstation is not None
        and workstation.last_action is not None
        and workstation.last_action.execution_status in {"executed", "filled"}
    )
    snapshot = SignalValidationSnapshotRecord(
        id=None,
        symbol=symbol,
        timestamp=fusion_signal.generated_at or datetime.now(tz=UTC),
        price=price,
        final_action=assistant.decision,
        fusion_final_signal=fusion_signal.final_signal,
        confidence=assistant.confidence_score,
        expected_edge_pct=fusion_signal.expected_edge_pct,
        estimated_cost_pct=readiness.estimated_round_trip_cost_pct if readiness is not None else None,
        risk_grade=assistant.risk_label,
        preferred_horizon=(
            assistant.best_timeframe
            if assistant.best_timeframe != "unknown"
            else fusion_signal.preferred_horizon
        ),
        technical_score=_technical_validation_score(context.technical_analysis if context is not None else None),
        technical_context_json=_technical_context_json(context.technical_analysis if context is not None else None),
        sentiment_score=_sentiment_validation_score(context.symbol_sentiment if context is not None else None),
        sentiment_context_json=_sentiment_context_json(context.symbol_sentiment if context is not None else None),
        pattern_score=_pattern_validation_score(pattern_analysis),
        pattern_context_json=_pattern_context_json(pattern_analysis),
        ai_context_json=_ai_context_json(workstation.ai_signal if workstation is not None else None),
        top_reasons=tuple(fusion_signal.top_reasons),
        warnings=tuple(fusion_signal.warnings),
        invalidation_hint=fusion_signal.invalidation_hint,
        trade_opened=trade_opened,
        signal_ignored_or_blocked=signal_ignored_or_blocked,
        blocker_reasons=blocker_reasons,
        regime_label=regime_analysis.regime_label if regime_analysis is not None else None,
    )
    return snapshot


def _snapshot_price(
    *,
    workstation: WorkstationResponse | None,
    context: SignalAnalysisContext | None,
) -> Decimal | None:
    if workstation is not None and workstation.last_price is not None:
        return workstation.last_price
    if context is not None and context.candles:
        return context.candles[-1].close
    return None


def _technical_validation_score(analysis: TechnicalAnalysisSnapshot | None) -> Decimal | None:
    if analysis is None or analysis.trend_strength_score is None:
        return None
    score = Decimal(analysis.trend_strength_score)
    if analysis.trend_direction == "bearish":
        return -score
    if analysis.trend_direction == "sideways":
        return Decimal("0")
    return score


def _sentiment_validation_score(analysis: SymbolSentimentSnapshot | None) -> Decimal | None:
    return Decimal(analysis.score) if analysis is not None and analysis.score is not None else None


def _pattern_validation_score(analysis: PatternAnalysisSnapshot | None) -> Decimal | None:
    if analysis is None or analysis.net_return_pct is None:
        return None
    if analysis.overall_direction == "bearish":
        return -abs(analysis.net_return_pct)
    return analysis.net_return_pct


def _technical_context_json(analysis: TechnicalAnalysisSnapshot | None) -> str:
    if analysis is None:
        return json.dumps({"available": False}, sort_keys=True)
    return json.dumps(
        {
            "available": True,
            "data_state": analysis.data_state,
            "trend_direction": analysis.trend_direction,
            "trend_strength": analysis.trend_strength,
            "trend_strength_score": analysis.trend_strength_score,
            "momentum_state": analysis.momentum_state,
            "volatility_regime": analysis.volatility_regime,
            "breakout_readiness": analysis.breakout_readiness,
            "breakout_bias": analysis.breakout_bias,
            "reversal_risk": analysis.reversal_risk,
            "multi_timeframe_agreement": analysis.multi_timeframe_agreement,
        },
        sort_keys=True,
    )


def _sentiment_context_json(analysis: SymbolSentimentSnapshot | None) -> str:
    if analysis is None:
        return json.dumps({"available": False}, sort_keys=True)
    return json.dumps(
        {
            "available": True,
            "data_state": analysis.data_state,
            "score": analysis.score,
            "label": analysis.label,
            "confidence": analysis.confidence,
            "momentum_state": analysis.momentum_state,
            "risk_flag": analysis.risk_flag,
            "source_mode": analysis.source_mode,
            "components": [component.name for component in analysis.components],
        },
        sort_keys=True,
    )


def _pattern_context_json(analysis: PatternAnalysisSnapshot | None) -> str:
    if analysis is None:
        return json.dumps({"available": False}, sort_keys=True)
    return json.dumps(
        {
            "available": True,
            "data_state": analysis.data_state,
            "horizon": analysis.horizon,
            "overall_direction": analysis.overall_direction,
            "net_return_pct": str(analysis.net_return_pct) if analysis.net_return_pct is not None else None,
            "trend_character": analysis.trend_character,
            "breakout_tendency": analysis.breakout_tendency,
            "reversal_tendency": analysis.reversal_tendency,
            "coverage_ratio_pct": str(analysis.coverage_ratio_pct),
        },
        sort_keys=True,
    )


def _ai_context_json(analysis: AISignalResponse | None) -> str:
    if analysis is None:
        return json.dumps({"available": False}, sort_keys=True)
    return json.dumps(
        {
            "available": True,
            "bias": analysis.bias,
            "confidence": analysis.confidence,
            "suggested_action": analysis.suggested_action,
            "regime": analysis.regime,
            "noise_level": analysis.noise_level,
            "abstain": analysis.abstain,
            "low_confidence": analysis.low_confidence,
            "confirmation_needed": analysis.confirmation_needed,
            "preferred_horizon": analysis.preferred_horizon,
            "weakening_factors": list(analysis.weakening_factors),
        },
        sort_keys=True,
    )


def _opportunity_from_candles(
    *,
    symbol: str,
    candles: list[Candle],
    spread_ratio: Decimal | None = None,
) -> OpportunityResponse:
    """Build a lightweight advisory opportunity score from stored/live candles."""

    if len(candles) < 24:
        return OpportunityResponse(
            symbol=symbol,
            score=0,
            suggested_action="avoid",
            confidence="low",
            volatility_label="insufficient_data",
            momentum_label="insufficient_data",
            liquidity_label="insufficient_data",
            risk_label="high",
            reason="Not enough stored candle history is available for this symbol yet.",
            data_state="waiting_for_history",
        )
    closes = [candle.close for candle in candles[-24:]]
    returns = []
    for previous, current in zip(closes, closes[1:]):
        if previous > Decimal("0"):
            returns.append((current - previous) / previous)
    if not returns:
        return OpportunityResponse(
            symbol=symbol,
            score=0,
            suggested_action="avoid",
            confidence="low",
            volatility_label="insufficient_data",
            momentum_label="insufficient_data",
            liquidity_label="insufficient_data",
            risk_label="high",
            reason="Recent price history is too thin to rank this symbol yet.",
            data_state="waiting_for_history",
        )

    momentum_pct = ((closes[-1] - closes[0]) / closes[0]) * Decimal("100")
    average_range_pct = sum(
        (((candle.high - candle.low) / candle.close) * Decimal("100")) for candle in candles[-24:] if candle.close > Decimal("0")
    ) / Decimal(max(1, len(candles[-24:])))
    average_quote_volume = sum((candle.quote_volume for candle in candles[-24:]), start=Decimal("0")) / Decimal("24")
    score = Decimal("50")
    score += min(Decimal("20"), max(Decimal("-20"), momentum_pct * Decimal("1.5")))
    score += min(Decimal("20"), average_range_pct * Decimal("5"))
    if average_quote_volume >= Decimal("10000000"):
        score += Decimal("15")
        liquidity_label = "high"
    elif average_quote_volume >= Decimal("1000000"):
        score += Decimal("8")
        liquidity_label = "medium"
    else:
        score -= Decimal("5")
        liquidity_label = "low"
    if spread_ratio is not None and spread_ratio > Decimal("0.0035"):
        score -= Decimal("12")
    bounded_score = int(max(Decimal("0"), min(Decimal("100"), score)))
    momentum_label = "bullish" if momentum_pct >= Decimal("1.0") else ("bearish" if momentum_pct <= Decimal("-1.0") else "mixed")
    volatility_label = "high" if average_range_pct >= Decimal("1.2") else ("normal" if average_range_pct >= Decimal("0.4") else "low")
    confidence = _confidence_label(bounded_score)
    suggested_action: Literal["watch", "possible_buy", "avoid"] = "watch"
    risk_label: Literal["low", "medium", "high"] = "medium"
    reason = f"Recent momentum is {momentum_label} with {volatility_label} volatility and {liquidity_label} liquidity."
    if bounded_score >= 70 and momentum_pct > Decimal("0"):
        suggested_action = "possible_buy"
        risk_label = "medium" if volatility_label != "high" else "high"
    elif bounded_score < 45:
        suggested_action = "avoid"
        risk_label = "high"
    return OpportunityResponse(
        symbol=symbol,
        score=bounded_score,
        suggested_action=suggested_action,
        confidence=confidence,
        volatility_label=volatility_label,
        momentum_label=momentum_label,
        liquidity_label=liquidity_label,
        risk_label=risk_label,
        reason=reason,
        data_state="ready",
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
    backfill_service: Annotated[HistoricalBackfillService, Depends(get_backfill_service)],
) -> BotStatusResponse:
    """Start live Binance Spot market-data driven paper trading."""

    try:
        status = await runtime.start(payload.symbol, payload.trading_profile)
        await backfill_service.ensure_recent_history(symbol=payload.symbol.strip().upper(), interval="1m", lookback_days=7)
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


@router.post("/bot/manual-buy", response_model=ManualTradeResponse)
async def manual_buy_market(
    payload: ManualTradeRequest,
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
) -> ManualTradeResponse:
    """Execute a manual paper-market buy for the selected symbol."""

    normalized_symbol = payload.symbol.strip().upper()
    try:
        return _to_manual_trade_response(await runtime.manual_buy_market(normalized_symbol))
    except Exception:
        LOGGER.exception("Manual paper buy failed for %s.", normalized_symbol)
        return ManualTradeResponse(
            symbol=normalized_symbol,
            action="buy_market",
            requested_side="BUY",
            status="rejected",
            message="Manual paper buy could not be completed. The workstation is still safe to refresh.",
            reason_codes=("MANUAL_TRADE_FAILED",),
        )


@router.post("/bot/manual-close", response_model=ManualTradeResponse)
async def manual_close_position(
    payload: ManualTradeRequest,
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
) -> ManualTradeResponse:
    """Execute a manual paper close for the selected symbol."""

    normalized_symbol = payload.symbol.strip().upper()
    try:
        return _to_manual_trade_response(await runtime.manual_close_position(normalized_symbol))
    except Exception:
        LOGGER.exception("Manual paper close failed for %s.", normalized_symbol)
        return ManualTradeResponse(
            symbol=normalized_symbol,
            action="close_position",
            requested_side="SELL",
            status="rejected",
            message="Manual paper close could not be completed. The workstation is still safe to refresh.",
            reason_codes=("MANUAL_TRADE_FAILED",),
        )


@router.get("/bot/backfill-status", response_model=BackfillStatusResponse)
def get_backfill_status(
    symbol: Annotated[str, Query(min_length=1)],
    backfill_service: Annotated[HistoricalBackfillService, Depends(get_backfill_service)],
    interval: ChartTimeframe = "1m",
    lookback_days: Annotated[int, Query(ge=1, le=30)] = 7,
) -> BackfillStatusResponse:
    """Return stored historical-candle coverage for one selected symbol."""

    return _to_backfill_status_response(
        backfill_service.status(
            symbol=symbol.strip().upper(),
            interval=interval,
            lookback_days=lookback_days,
        )
    )


@router.post("/bot/backfill", response_model=BackfillStatusResponse)
async def trigger_backfill(
    symbol: Annotated[str, Query(min_length=1)],
    backfill_service: Annotated[HistoricalBackfillService, Depends(get_backfill_service)],
    interval: ChartTimeframe = "1m",
    lookback_days: Annotated[int, Query(ge=1, le=30)] = 7,
) -> BackfillStatusResponse:
    """Trigger or refresh historical-candle backfill for one selected symbol."""

    return _to_backfill_status_response(
        await backfill_service.ensure_recent_history(
            symbol=symbol.strip().upper(),
            interval=interval,
            lookback_days=lookback_days,
        )
    )


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


@router.get("/bot/candles", response_model=CandleHistoryResponse)
def get_candles(
    symbol: Annotated[str, Query(min_length=1)],
    timeframe: Annotated[ChartTimeframe, Query()] = "1m",
    limit: Annotated[int, Query(ge=20, le=240)] = 120,
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)] = None,
    settings: Annotated[Settings, Depends(get_settings_dependency)] = None,
) -> CandleHistoryResponse:
    """Return recent closed candles for the selected symbol chart."""

    normalized_symbol = symbol.strip().upper()
    status = runtime.status()
    runtime_active = _runtime_matches_symbol(status, normalized_symbol)
    repository = StorageRepository(settings.database_url)
    try:
        merged = _load_merged_candle_series(
            repository=repository,
            runtime=runtime,
            symbol=normalized_symbol,
            interval=timeframe,
            limit=limit,
        )
        return _to_candle_history_response(
            symbol=normalized_symbol,
            timeframe=timeframe,
            candles=merged.candles,
            source_timeframe=merged.source_interval,
            derived_from_lower_timeframe=merged.derived_from_lower_timeframe,
            runtime_active=runtime_active,
            limit=limit,
        )
    except Exception:
        LOGGER.exception(
            "Failed to build candle history for symbol %s timeframe %s.",
            normalized_symbol,
            timeframe,
        )
        return CandleHistoryResponse(
            symbol=normalized_symbol,
            timeframe=timeframe,
            source_timeframe="1m",
            derived_from_lower_timeframe=timeframe != "1m",
            data_state="degraded_storage",
            status_message="Candle history is temporarily unavailable.",
            candles=[],
            current_price=None,
        )
    finally:
        repository.close()


@router.get("/bot/technical-analysis", response_model=TechnicalAnalysisResponse)
def get_technical_analysis(
    symbol: Annotated[str, Query(min_length=1)],
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
    settings: Annotated[Settings, Depends(get_settings_dependency)],
) -> TechnicalAnalysisResponse:
    """Return symbol-scoped technical analysis for the workstation."""

    normalized_symbol = symbol.strip().upper()
    status = runtime.status()
    repository = StorageRepository(settings.database_url)
    try:
        analysis, analysis_failed = _safe_technical_analysis(runtime, repository, normalized_symbol)
    finally:
        repository.close()
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


@router.get("/bot/regime-analysis", response_model=RegimeAnalysisResponse)
def get_regime_analysis(
    symbol: Annotated[str, Query(min_length=1)],
    horizon: str = Query(default="7d"),
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)] = None,
    settings: Annotated[Settings, Depends(get_settings_dependency)] = None,
    sentiment_service: Annotated[SymbolSentimentService, Depends(get_symbol_sentiment_service)] = None,
) -> RegimeAnalysisResponse:
    """Return deterministic market-regime analysis for one selected symbol."""

    normalized_symbol = symbol.strip().upper()
    try:
        normalized_horizon = normalize_horizon(horizon)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    runtime_status = runtime.status()
    try:
        repository = StorageRepository(settings.database_url)
    except Exception:
        LOGGER.exception("Failed to open storage while reading regime analysis for %s.", normalized_symbol)
        return _to_regime_analysis_response(
            symbol=normalized_symbol,
            horizon=normalized_horizon,
            analysis=None,
            data_state="degraded_storage",
            status_message="Regime-analysis storage is unavailable.",
        )
    try:
        analysis, analysis_failed = _safe_regime_analysis(
            symbol=normalized_symbol,
            horizon=normalized_horizon,
            runtime=runtime,
            repository=repository,
            sentiment_service=sentiment_service,
        )
        data_state, status_message = _derive_regime_analysis_data_state(
            symbol=normalized_symbol,
            status=runtime_status,
            analysis=analysis,
            analysis_failed=analysis_failed,
            storage_degraded=repository.optional_storage_degraded,
            storage_message=repository.optional_storage_message,
        )
    finally:
        repository.close()
    return _to_regime_analysis_response(
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
        workstation_state, _, _ = _safe_workstation_state(runtime, normalized_symbol)
        context = None
        if repository is not None:
            context = _build_signal_analysis_context(
                runtime=runtime,
                repository=repository,
                symbol=normalized_symbol,
                sentiment_service=sentiment_service,
            )
        analysis, analysis_failed = _safe_fusion_signal(
            symbol=normalized_symbol,
            runtime=runtime,
            repository=repository,
            sentiment_service=sentiment_service,
            workstation_state=workstation_state,
            context=context,
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


@router.get("/bot/trading-assistant", response_model=TradingAssistantResponse)
async def get_trading_assistant(
    symbol: Annotated[str, Query(min_length=1)],
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
    settings: Annotated[Settings, Depends(get_settings_dependency)],
    sentiment_service: Annotated[SymbolSentimentService, Depends(get_symbol_sentiment_service)],
    backfill_service: Annotated[HistoricalBackfillService, Depends(get_backfill_service)],
) -> TradingAssistantResponse:
    """Return a beginner-friendly trading summary for the selected symbol."""

    normalized_symbol = symbol.strip().upper()
    backfill_status = backfill_service.status(symbol=normalized_symbol, interval="1m", lookback_days=7)
    repository = StorageRepository(settings.database_url)
    try:
        workstation_state, _, _ = _safe_workstation_state(runtime, normalized_symbol)
        workstation_status = runtime.status()
        workstation_data_state, workstation_status_message = _derive_workstation_data_state(
            state=workstation_state,
            status=workstation_status,
            storage_degraded=runtime.storage_degraded(),
            storage_message=runtime.storage_status_message(),
            state_failed=False,
            state_failure_message=None,
        )
        workstation = _to_workstation_response(
            state=workstation_state,
            runtime=runtime,
            status=workstation_status,
            data_state=workstation_data_state,
            status_message=workstation_status_message,
        )
        context = _build_signal_analysis_context(
            runtime=runtime,
            repository=repository,
            symbol=normalized_symbol,
            sentiment_service=sentiment_service,
        )
        technical_analysis, _ = _safe_technical_analysis(
            runtime,
            repository,
            normalized_symbol,
            context=context,
        )
        technical_response = _to_technical_analysis_response(
            symbol=normalized_symbol,
            analysis=technical_analysis,
            data_state="ready" if technical_analysis is not None and technical_analysis.data_state == "ready" else "waiting_for_history",
            status_message=technical_analysis.status_message if technical_analysis is not None else None,
        )
        fusion_analysis, _ = _safe_fusion_signal(
            symbol=normalized_symbol,
            runtime=runtime,
            repository=repository,
            sentiment_service=sentiment_service,
            workstation_state=workstation_state,
            context=context,
        )
        fusion_state, fusion_message = _derive_fusion_data_state(
            symbol=normalized_symbol,
            status=runtime.status(),
            analysis=fusion_analysis,
            analysis_failed=False,
        )
        fusion_response = _to_fusion_signal_response(
            symbol=normalized_symbol,
            analysis=fusion_analysis,
            data_state=fusion_state,
            status_message=fusion_message,
        )
        pattern_analysis, _ = _safe_pattern_analysis(
            runtime,
            symbol=normalized_symbol,
            horizon="7d",
            repository=repository,
            candles=context.candles,
        )
        regime_analysis, _ = _safe_regime_analysis(
            symbol=normalized_symbol,
            horizon="7d",
            runtime=runtime,
            repository=repository,
            sentiment_service=sentiment_service,
            context=context,
        )
        assistant = _build_trading_assistant_response(
            symbol=normalized_symbol,
            backfill_status=backfill_status,
            fusion_signal=fusion_response,
            technical_analysis=technical_response,
            workstation=workstation,
        )
        current_snapshot = _persist_signal_validation_snapshot(
            repository=repository,
            symbol=normalized_symbol,
            assistant=assistant,
            fusion_signal=fusion_response,
            workstation=workstation,
            context=context,
            pattern_analysis=pattern_analysis,
            regime_analysis=regime_analysis,
        )
        similar_setup = _similar_setup_report_for_snapshot(
            repository=repository,
            current_snapshot=current_snapshot,
        )
        assistant = assistant.model_copy(
            update={"similar_setup": _to_similar_setup_summary_response(similar_setup)}
        )
        return assistant
    finally:
        repository.close()


@router.get("/bot/trade-eligibility", response_model=TradeEligibilityResponse)
async def get_trade_eligibility(
    symbol: Annotated[str, Query(min_length=1)],
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
    settings: Annotated[Settings, Depends(get_settings_dependency)],
    sentiment_service: Annotated[SymbolSentimentService, Depends(get_symbol_sentiment_service)],
    backfill_service: Annotated[HistoricalBackfillService, Depends(get_backfill_service)],
    horizon: str | None = None,
) -> TradeEligibilityResponse:
    """Return advisory-only paper automation eligibility for the selected symbol."""

    normalized_symbol = symbol.strip().upper()
    validation_horizon = horizon.strip().lower() if horizon is not None else None
    if validation_horizon is not None and validation_horizon not in VALIDATION_HORIZONS:
        raise HTTPException(status_code=400, detail="horizon must be one of 5m, 15m, 1h, 4h, 24h")

    backfill_status = backfill_service.status(symbol=normalized_symbol, interval="1m", lookback_days=7)
    repository = StorageRepository(settings.database_url)
    try:
        workstation_state, _, _ = _safe_workstation_state(runtime, normalized_symbol)
        workstation_status = runtime.status()
        workstation_data_state, workstation_status_message = _derive_workstation_data_state(
            state=workstation_state,
            status=workstation_status,
            storage_degraded=runtime.storage_degraded(),
            storage_message=runtime.storage_status_message(),
            state_failed=False,
            state_failure_message=None,
        )
        workstation = _to_workstation_response(
            state=workstation_state,
            runtime=runtime,
            status=workstation_status,
            data_state=workstation_data_state,
            status_message=workstation_status_message,
        )
        context = _build_signal_analysis_context(
            runtime=runtime,
            repository=repository,
            symbol=normalized_symbol,
            sentiment_service=sentiment_service,
        )
        technical_analysis, _ = _safe_technical_analysis(
            runtime,
            repository,
            normalized_symbol,
            context=context,
        )
        technical_response = _to_technical_analysis_response(
            symbol=normalized_symbol,
            analysis=technical_analysis,
            data_state=(
                "ready"
                if technical_analysis is not None and technical_analysis.data_state == "ready"
                else "waiting_for_history"
            ),
            status_message=technical_analysis.status_message if technical_analysis is not None else None,
        )
        fusion_analysis, _ = _safe_fusion_signal(
            symbol=normalized_symbol,
            runtime=runtime,
            repository=repository,
            sentiment_service=sentiment_service,
            workstation_state=workstation_state,
            context=context,
        )
        fusion_state, fusion_message = _derive_fusion_data_state(
            symbol=normalized_symbol,
            status=runtime.status(),
            analysis=fusion_analysis,
            analysis_failed=False,
        )
        fusion_response = _to_fusion_signal_response(
            symbol=normalized_symbol,
            analysis=fusion_analysis,
            data_state=fusion_state,
            status_message=fusion_message,
        )
        preferred_horizon = validation_horizon or fusion_response.preferred_horizon
        pattern_analysis, _ = _safe_pattern_analysis(
            runtime,
            symbol=normalized_symbol,
            horizon="7d",
            repository=repository,
            candles=context.candles,
        )
        regime_analysis, _ = _safe_regime_analysis(
            symbol=normalized_symbol,
            horizon="7d",
            runtime=runtime,
            repository=repository,
            sentiment_service=sentiment_service,
            context=context,
        )
        assistant = _build_trading_assistant_response(
            symbol=normalized_symbol,
            backfill_status=backfill_status,
            fusion_signal=fusion_response,
            technical_analysis=technical_response,
            workstation=workstation,
        )
        current_snapshot = _build_signal_validation_snapshot_record(
            symbol=normalized_symbol,
            assistant=assistant,
            fusion_signal=fusion_response,
            workstation=workstation,
            context=context,
            pattern_analysis=pattern_analysis,
            regime_analysis=regime_analysis,
        )
        similar_setup = _similar_setup_report_for_snapshot(
            repository=repository,
            current_snapshot=current_snapshot,
        )
        validation_report = _signal_validation_report_for_symbol(
            repository=repository,
            symbol=normalized_symbol,
            horizon=preferred_horizon,
        )
        blocker_reasons = current_snapshot.blocker_reasons if current_snapshot is not None else ()
        result = evaluate_trade_eligibility(
            TradeEligibilityInput(
                symbol=normalized_symbol,
                action=assistant.decision,
                confidence=assistant.confidence_score,
                risk_grade=assistant.risk_label,
                preferred_horizon=preferred_horizon,
                expected_edge_pct=fusion_response.expected_edge_pct,
                estimated_cost_pct=(
                    current_snapshot.estimated_cost_pct if current_snapshot is not None else None
                ),
                blocker_reasons=blocker_reasons,
                current_warnings=tuple(fusion_response.warnings),
                regime_label=regime_analysis.regime_label if regime_analysis is not None else None,
                regime_confidence=regime_analysis.confidence if regime_analysis is not None else None,
                regime_warnings=regime_analysis.risk_warnings if regime_analysis is not None else (),
                regime_avoid_conditions=(
                    regime_analysis.avoid_conditions if regime_analysis is not None else ()
                ),
                similar_setup=similar_setup,
                signal_validation=validation_report,
            )
        )
        return _to_trade_eligibility_response(symbol=normalized_symbol, result=result)
    finally:
        repository.close()


@router.get("/bot/opportunities", response_model=list[OpportunityResponse])
async def get_opportunities(
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)] = None,
    settings: Annotated[Settings, Depends(get_settings_dependency)] = None,
    symbol_service: Annotated[SpotSymbolService, Depends(get_symbol_service)] = None,
) -> list[OpportunityResponse]:
    """Rank a lightweight set of USDT Spot symbols by paper-trading opportunity potential."""

    candidates = await symbol_service.search_symbols(query="", limit=limit)
    repository = StorageRepository(settings.database_url)
    try:
        responses: list[OpportunityResponse] = []
        for record in candidates:
            candles = _load_merged_candles(
                repository=repository,
                runtime=runtime,
                symbol=record.symbol,
                interval="5m",
                limit=120,
            )
            spread_ratio = None
            top_of_book_getter = getattr(runtime, "top_of_book", None)
            top = top_of_book_getter(record.symbol) if callable(top_of_book_getter) else None
            if top is not None and top.bid_price > Decimal("0"):
                spread_ratio = (top.ask_price - top.bid_price) / top.bid_price
            responses.append(
                _opportunity_from_candles(
                    symbol=record.symbol,
                    candles=candles,
                    spread_ratio=spread_ratio,
                )
            )
        ranked = sorted(
            responses,
            key=lambda item: (item.data_state != "ready", -item.score, item.symbol),
        )
        return ranked[:limit]
    finally:
        repository.close()


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
            derived_signal = _build_ai_signal_from_history(
                symbol=normalized_symbol,
                runtime=runtime,
                repository=repository,
            )
        except Exception:
            LOGGER.exception("Failed to build AI signal from stored history for %s.", normalized_symbol)
            derived_signal = None
        finally:
            repository.close()
        return derived_signal
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
