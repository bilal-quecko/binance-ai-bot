"""FastAPI endpoints for paper-bot symbol discovery and runtime control."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field as dataclass_field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import json
import logging
from threading import RLock, Thread
import time
from typing import Annotated, Literal
from uuid import uuid4

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
from app.data.historical_candles import SupportedInterval, interval_to_timedelta, now_utc, parse_rest_kline
from app.data.heatmap_provider import HeatmapSignalEnrichment, enrich_signal_with_heatmap
from app.data.binance_liquidation_feed import get_global_liquidation_feed_service
from app.data.binance_derivatives_data import (
    BinanceDerivativesSnapshot,
    fallback_derivatives_snapshot,
    get_derivatives_snapshot,
)
from app.exchange.binance_rest import BinanceRestClient
from app.data import MarketContextService
from app.features.feature_store import FeatureEngine
from app.features.models import FeatureConfig, FeatureSnapshot
from app.exchange.symbol_service import SpotSymbolRecord, SpotSymbolService
from app.futures_paper import FuturesPaperService
from app.futures_paper.models import FuturesFillResult, FuturesPosition, FuturesSignal, FuturesSignalInput
from app.fusion import FusionInputs, FusionSignalSnapshot, UnifiedSignalFusionEngine
from app.market_data.candles import Candle
from app.runner.models import ManualTradeResult, TradeReadiness, TradingProfile
from app.services import HistoricalBackfillService
from app.storage import StorageRepository
from app.storage.candle_repository import CandleBackfillStatus, CandleRepository, merge_candles
from app.storage.models import (
    HistoricalCandleRecord,
    MarketCandleSnapshotRecord,
    ScannerCandidatePriceRecord,
    ScannerCandidateRecord,
    ScannerRunRecord,
    ScannerValidationSnapshotRecord,
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
from app.monitoring.futures_opportunity_scanner import (
    FuturesOpportunityScanReport,
    FuturesOpportunityScanner,
    FuturesPaperSignal,
    FuturesSignalContext,
    MIN_CANDLES_FOR_FUTURES_SIGNAL,
)
from app.monitoring.spot_opportunity_scanner import (
    SpotOpportunityScanReport,
    SpotOpportunityScanner,
    SpotOpportunitySignal,
    SpotScannerContext,
)
from app.monitoring.liquidity_bias import (
    NEUTRAL_LIQUIDITY_BIAS,
    LiquidityBiasInput,
    LiquidityBiasSnapshot,
    estimate_liquidity_bias,
)
from app.monitoring.crowd_positioning import (
    CrowdPositioningSnapshot,
    NEUTRAL_CROWD_POSITIONING,
    crowd_positioning_from_derivatives,
)
from app.monitoring.liquidity_zones import (
    NEUTRAL_LIQUIDITY_ZONES,
    LiquidityZone,
    LiquidityZoneSnapshot,
    NearestLiquidityTarget,
    estimate_liquidity_zones,
    validate_liquidity_zones_with_liquidations,
)
from app.monitoring.liquidation_intelligence import (
    LiquidationIntelligenceSnapshot,
    NEUTRAL_LIQUIDATION_INTELLIGENCE,
    interpret_liquidation_events,
)
from app.monitoring.scanner_validation_report import persist_scanner_validation_snapshots
from app.monitoring.signal_outcomes import SignalSnapshotInput, persist_signal_snapshot
from app.monitoring.signal_timing_baseline import (
    TIMING_HORIZONS,
    SignalTimingAggregate,
    build_signal_timing_baseline_report,
    evaluate_pending_signal_timing_baselines,
)
from app.monitoring.continuous_market_intelligence import (
    ContinuousIntelligenceCandidate,
    ContinuousIntelligenceConfig,
    ContinuousIntelligenceStatus,
    ContinuousMarketIntelligenceService,
)
from app.monitoring.futures_scanner_ws_heartbeat import (
    FuturesScannerLivePrice,
    FuturesScannerWebSocketHeartbeatService,
    sanitize_scanner_symbols,
)

router = APIRouter()
LOGGER = logging.getLogger(__name__)

DataState = Literal["ready", "waiting_for_runtime", "waiting_for_history", "degraded_storage"]
ChartTimeframe = Literal["1m", "5m", "15m", "1h"]
SelectedMarket = Literal["spot", "futures"]
FuturesSymbolUniverseSource = Literal["live", "cache", "fallback", "unavailable"]
FUTURES_SYMBOL_UNIVERSE_CACHE_TTL = timedelta(minutes=20)
FUTURES_SCANNER_FALLBACK_SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "DOGEUSDT",
    "ADAUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "LTCUSDT",
    "TRXUSDT",
    "DOTUSDT",
    "BCHUSDT",
    "NEARUSDT",
    "INJUSDT",
    "OPUSDT",
    "ARBUSDT",
    "SUIUSDT",
    "SEIUSDT",
    "APTUSDT",
)


@dataclass(slots=True)
class FuturesSymbolUniverseCacheEntry:
    """In-memory USD-M Futures universe cache entry."""

    records: list[SpotSymbolRecord]
    fetched_at: datetime
    latest_error: str | None = None


@dataclass(slots=True)
class FuturesSymbolUniverseResult:
    """Resolved USD-M Futures universe with diagnostics for the scanner response."""

    records: list[SpotSymbolRecord]
    source: FuturesSymbolUniverseSource
    last_successful_fetch_at: datetime | None
    latest_error: str | None = None


_FUTURES_SYMBOL_UNIVERSE_CACHE: dict[str, FuturesSymbolUniverseCacheEntry] = {}


@dataclass(slots=True)
class SignalAnalysisContext:
    """Shared per-request signal-analysis inputs for one selected symbol."""

    symbol: str
    candles: list[Candle]
    feature_snapshot: FeatureSnapshot | None
    technical_analysis: TechnicalAnalysisSnapshot | None
    market_sentiment: MarketSentimentSnapshot | None
    symbol_sentiment: SymbolSentimentSnapshot | None
    liquidity_bias: LiquidityBiasSnapshot
    benchmark_candles: list[Candle]
    crowd_positioning: CrowdPositioningSnapshot = NEUTRAL_CROWD_POSITIONING
    derivatives_data: BinanceDerivativesSnapshot | None = None
    liquidation_intelligence: LiquidationIntelligenceSnapshot = NEUTRAL_LIQUIDATION_INTELLIGENCE


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


class LiquidityZoneResponse(BaseModel):
    """Estimated liquidity zone, not an exact liquidation level."""

    level: Decimal | None = None
    strength: Literal["low", "medium", "high"] = "low"
    reason: str = "No clear estimated liquidity zone."


class NearestLiquidityTargetResponse(BaseModel):
    """Nearest estimated liquidity target relative to current price."""

    direction: Literal["up", "down", "none"] = "none"
    level: Decimal | None = None
    distance_pct: Decimal | None = None
    strength: Literal["low", "medium", "high"] = "low"


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
    liquidity_bias: Literal["bullish", "bearish", "neutral"] = "neutral"
    liquidity_pressure: Literal["low", "medium", "high"] = "low"
    likely_liquidation_direction: Literal["up", "down", "none"] = "none"
    trap_risk: Literal["long_trap", "short_trap", "low"] = "low"
    liquidity_explanation: str = NEUTRAL_LIQUIDITY_BIAS.explanation
    upside_liquidity_zone: LiquidityZoneResponse = Field(default_factory=LiquidityZoneResponse)
    downside_liquidity_zone: LiquidityZoneResponse = Field(default_factory=LiquidityZoneResponse)
    nearest_liquidity_target: NearestLiquidityTargetResponse = Field(default_factory=NearestLiquidityTargetResponse)
    sweep_risk: Literal["none", "upside_sweep", "downside_sweep", "both_sides"] = "none"
    trade_timing_adjustment: Literal[
        "enter_now",
        "wait_for_sweep",
        "wait_for_confirmation",
        "avoid_chop",
    ] = "wait_for_confirmation"
    tp_sl_alignment: Literal[
        "aligned",
        "stop_too_close_to_liquidity",
        "target_before_liquidity",
        "target_after_liquidity",
        "needs_review",
    ] = "needs_review"
    liquidity_zone_explanation: str = NEUTRAL_LIQUIDITY_ZONES.explanation
    crowd_side: Literal["long_crowded", "short_crowded", "balanced"] = "balanced"
    crowd_strength: Literal["low", "medium", "high"] = "low"
    squeeze_risk: Literal["long_squeeze", "short_squeeze", "low"] = "low"
    positioning_explanation: str = NEUTRAL_CROWD_POSITIONING.explanation
    funding_rate: Decimal | None = None
    open_interest: Decimal | None = None
    oi_trend: Literal["rising", "falling", "neutral"] = "neutral"
    heatmap_liquidity_above: Decimal | None = None
    heatmap_liquidity_below: Decimal | None = None
    heatmap_intensity_score: int | None = None
    heatmap_bias: Literal["upside_squeeze", "downside_sweep", "neutral"] = "neutral"
    base_signal_type: str = "WAIT"
    heatmap_signal_type: str = "WAIT"
    base_confidence: int = 0
    heatmap_confidence: int = 0
    heatmap_alignment: Literal["confirmed", "conflict", "neutral"] = "neutral"
    heatmap_explanation: str = "Heatmap unavailable."
    heatmap_provider: str = "mock"
    heatmap_data_quality: str = "mock"
    heatmap_is_real_data: bool = False
    heatmap_provider_status: str = "available"
    liquidation_pressure: Literal["low", "medium", "high"] = "low"
    liquidation_imbalance: Decimal | None = None
    liquidation_signal: Literal[
        "none",
        "cascade_down",
        "cascade_up",
        "exhaustion",
        "sweep_confirmation",
        "noise",
    ] = "none"
    liquidation_intensity: Literal["low", "medium", "high"] = "low"
    dominant_side: Literal["longs_liquidated", "shorts_liquidated", "balanced"] = "balanced"
    liquidation_explanation: str = NEUTRAL_LIQUIDATION_INTELLIGENCE.explanation
    liquidation_volume_long: Decimal = Decimal("0")
    liquidation_volume_short: Decimal = Decimal("0")
    liquidation_imbalance_ratio: Decimal = Decimal("0")
    liquidation_event_frequency: Decimal = Decimal("0")


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
    liquidity_zone_summary: str = "No liquidity-zone estimate is available yet."
    sweep_risk: Literal["none", "upside_sweep", "downside_sweep", "both_sides"] = "none"
    trade_timing_adjustment: Literal[
        "enter_now",
        "wait_for_sweep",
        "wait_for_confirmation",
        "avoid_chop",
    ] = "wait_for_confirmation"
    tp_sl_alignment: Literal[
        "aligned",
        "stop_too_close_to_liquidity",
        "target_before_liquidity",
        "target_after_liquidity",
        "needs_review",
    ] = "needs_review"
    crowd_side: Literal["long_crowded", "short_crowded", "balanced"] = "balanced"
    crowd_strength: Literal["low", "medium", "high"] = "low"
    squeeze_risk: Literal["long_squeeze", "short_squeeze", "low"] = "low"
    funding_rate: Decimal | None = None
    open_interest: Decimal | None = None
    oi_trend: Literal["rising", "falling", "neutral"] = "neutral"
    liquidation_signal: Literal[
        "none",
        "cascade_down",
        "cascade_up",
        "exhaustion",
        "sweep_confirmation",
        "noise",
    ] = "none"
    liquidation_intensity: Literal["low", "medium", "high"] = "low"
    dominant_side: Literal["longs_liquidated", "shorts_liquidated", "balanced"] = "balanced"
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


class SpotOpportunitySignalResponse(BaseModel):
    """Paper-only Spot scanner signal for one symbol."""

    symbol: str
    action: Literal["buy_candidate", "watch", "avoid", "exit_watch"]
    opportunity_score: int
    confidence: int
    trend_score: int
    momentum_score: int
    volatility_quality_score: int
    liquidity_score: int
    structure_score: int
    regime_score: int
    validation_score: int | None = None
    eligibility_score: int
    evidence_strength: Literal["insufficient", "weak", "mixed", "promising", "strong"]
    trend: str
    momentum: str
    best_horizon: str
    risk_grade: Literal["low", "medium", "high"]
    current_price: Decimal | None = None
    suggested_entry_zone: str | None = None
    suggested_stop_loss: Decimal | None = None
    suggested_take_profit: Decimal | None = None
    regime: str | None = None
    data_source: Literal["binance_spot"] = "binance_spot"
    price_type: Literal["spot_last_price"] = "spot_last_price"
    reason: str
    warnings: list[str] = Field(default_factory=list)
    timestamp: datetime
    paper_only: bool = True
    advisory_only: bool = True
    live_trading_enabled: bool = False
    futures_enabled: bool = False


class SpotOpportunityScanResponse(BaseModel):
    """Paper-only Spot scanner response."""

    generated_at: datetime
    scan_state: Literal["ready", "partial", "insufficient_data", "degraded"]
    warnings: list[str] = Field(default_factory=list)
    scanned_count: int
    failed_symbols: list[str] = Field(default_factory=list)
    buy_candidates: list[SpotOpportunitySignalResponse] = Field(default_factory=list)
    watch_candidates: list[SpotOpportunitySignalResponse] = Field(default_factory=list)
    avoid_candidates: list[SpotOpportunitySignalResponse] = Field(default_factory=list)
    exit_watch_candidates: list[SpotOpportunitySignalResponse] = Field(default_factory=list)
    data_source: Literal["binance_spot", "last_successful_cache", "empty_degraded"] = "binance_spot"
    quote_asset: str = "USDT"
    symbol_count: int = 0
    latest_successful_scanner_at: datetime | None = None
    latest_error: str | None = None
    persisted_candidate_count: int = 0


class FuturesPaperSignalResponse(BaseModel):
    """Paper-only futures long/short scanner signal for one symbol."""

    symbol: str
    direction: Literal["long", "short", "wait", "avoid"]
    opportunity_score: int
    direction_score: int
    momentum_score: int
    trend_score: int
    volatility_quality_score: int
    liquidity_score: int
    risk_score: int
    validation_score: int | None = None
    confidence: int
    evidence_strength: Literal["insufficient", "unvalidated", "weak", "mixed", "promising", "strong"]
    trend: str
    momentum: str
    best_horizon: str
    risk_grade: Literal["low", "medium", "high"]
    regime: str | None = None
    current_price: Decimal | None = None
    market_sensitivity: Literal["conservative", "balanced", "aggressive"] = "balanced"
    slow_market_setup: Literal[
        "none",
        "range_breakout",
        "liquidity_sweep_reversal",
        "compression_breakout",
        "mean_reversion_range_edge",
        "low_volatility_continuation",
        "low_volatility_no_edge",
    ] = "none"
    slow_market_reason: str | None = None
    data_source: Literal["binance_usdm_futures"] = "binance_usdm_futures"
    price_type: Literal["mark_price", "futures_last_price"] = "futures_last_price"
    reason: str
    invalidation_hint: str | None = None
    suggested_entry_zone: str | None = None
    suggested_stop_loss: Decimal | None = None
    suggested_take_profit: Decimal | None = None
    estimated_fee_impact: Decimal | None = None
    leverage_suggestion: str
    liquidation_safety_note: str
    similar_setup_summary: str
    eligibility_status: str
    warnings: list[str] = Field(default_factory=list)
    timestamp: datetime
    liquidity_bias: Literal["bullish", "bearish", "neutral"] = "neutral"
    liquidity_pressure: Literal["low", "medium", "high"] = "low"
    likely_liquidation_direction: Literal["up", "down", "none"] = "none"
    trap_risk: Literal["long_trap", "short_trap", "low"] = "low"
    liquidity_explanation: str = NEUTRAL_LIQUIDITY_BIAS.explanation
    upside_liquidity_zone: LiquidityZoneResponse = Field(default_factory=LiquidityZoneResponse)
    downside_liquidity_zone: LiquidityZoneResponse = Field(default_factory=LiquidityZoneResponse)
    nearest_liquidity_target: NearestLiquidityTargetResponse = Field(default_factory=NearestLiquidityTargetResponse)
    sweep_risk: Literal["none", "upside_sweep", "downside_sweep", "both_sides"] = "none"
    trade_timing_adjustment: Literal[
        "enter_now",
        "wait_for_sweep",
        "wait_for_confirmation",
        "avoid_chop",
    ] = "wait_for_confirmation"
    tp_sl_alignment: Literal[
        "aligned",
        "stop_too_close_to_liquidity",
        "target_before_liquidity",
        "target_after_liquidity",
        "needs_review",
    ] = "needs_review"
    liquidity_zone_explanation: str = NEUTRAL_LIQUIDITY_ZONES.explanation
    liquidity_adjusted_note: str | None = None
    crowd_side: Literal["long_crowded", "short_crowded", "balanced"] = "balanced"
    crowd_strength: Literal["low", "medium", "high"] = "low"
    squeeze_risk: Literal["long_squeeze", "short_squeeze", "low"] = "low"
    funding_rate: Decimal | None = None
    open_interest: Decimal | None = None
    oi_trend: Literal["rising", "falling", "neutral"] = "neutral"
    heatmap_liquidity_above: Decimal | None = None
    heatmap_liquidity_below: Decimal | None = None
    heatmap_intensity_score: int | None = None
    heatmap_bias: Literal["upside_squeeze", "downside_sweep", "neutral"] = "neutral"
    base_signal_type: str = "WAIT"
    heatmap_signal_type: str = "WAIT"
    base_confidence: int = 0
    heatmap_confidence: int = 0
    heatmap_alignment: Literal["confirmed", "conflict", "neutral"] = "neutral"
    heatmap_explanation: str = "Heatmap unavailable."
    heatmap_provider: str = "mock"
    heatmap_data_quality: str = "mock"
    heatmap_is_real_data: bool = False
    heatmap_provider_status: str = "available"
    liquidation_pressure: Literal["low", "medium", "high"] = "low"
    liquidation_imbalance: Decimal | None = None
    liquidation_signal: Literal[
        "none",
        "cascade_down",
        "cascade_up",
        "exhaustion",
        "sweep_confirmation",
        "noise",
    ] = "none"
    liquidation_intensity: Literal["low", "medium", "high"] = "low"
    dominant_side: Literal["longs_liquidated", "shorts_liquidated", "balanced"] = "balanced"
    liquidation_explanation: str = NEUTRAL_LIQUIDATION_INTELLIGENCE.explanation
    liquidation_volume_long: Decimal = Decimal("0")
    liquidation_volume_short: Decimal = Decimal("0")
    liquidation_imbalance_ratio: Decimal = Decimal("0")
    liquidation_event_frequency: Decimal = Decimal("0")


class FuturesOpportunityScanResponse(BaseModel):
    """Paper-only futures opportunity scanner response."""

    generated_at: datetime
    scan_state: Literal["ready", "partial", "insufficient_data", "degraded"]
    long_candidates: list[FuturesPaperSignalResponse] = Field(default_factory=list)
    short_candidates: list[FuturesPaperSignalResponse] = Field(default_factory=list)
    neutral_candidates: list[FuturesPaperSignalResponse] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    scanned_count: int
    failed_symbols: list[str] = Field(default_factory=list)
    paper_only: bool = True
    advisory_only: bool = True
    live_futures_trading_enabled: bool = False
    real_orders_enabled: bool = False
    max_leverage_suggestion: str = "3x paper-only"
    futures_symbol_universe_source: Literal["live", "cache", "fallback", "unavailable"] = "unavailable"
    symbol_count: int = 0
    last_successful_fetch_at: datetime | None = None
    latest_error: str | None = None
    data_source: str = "live_scan"
    latest_successful_scanner_at: datetime | None = None
    latest_scanner_error: str | None = None
    persisted_candidate_count: int = 0
    fallback_symbol_count: int = 0


FuturesScannerJobStatus = Literal["queued", "running", "partial", "completed", "failed", "cancelled"]


class SpotOpportunityScanStartRequest(BaseModel):
    """Request body for an async paper-only Spot scanner job."""

    quote_asset: str = "USDT"
    limit: int | None = Field(default=None, ge=1)
    max_symbols: int | None = Field(default=None, ge=1)
    concurrency: int = Field(default=5, ge=1, le=10)
    batch_size: int = Field(default=8, ge=5, le=10)
    symbol_timeout_seconds: float = Field(default=6.0, ge=1, le=8)
    scan_timeout_seconds: float = Field(default=45.0, ge=5, le=90)
    horizon: str = "7d"
    min_opportunity_score: int = Field(default=0, ge=0, le=100)
    min_confidence: int = Field(default=0, ge=0, le=100)
    include_avoid: bool = True


class SpotOpportunityScanJobResponse(BaseModel):
    """Progress snapshot for an async Spot scanner job."""

    scan_id: str
    status: FuturesScannerJobStatus
    total_symbols: int = 0
    scanned_symbols: int = 0
    current_symbol: str | None = None
    current_phase: str = "queued"
    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    scan: SpotOpportunityScanResponse | None = None
    warnings: list[str] = Field(default_factory=list)
    failed_symbols: list[str] = Field(default_factory=list)
    latest_error: str | None = None


@dataclass(slots=True)
class SpotScannerJob:
    """Mutable in-memory state for one async Spot scanner run."""

    scan_id: str
    request: SpotOpportunityScanStartRequest
    status: FuturesScannerJobStatus = "queued"
    total_symbols: int = 0
    scanned_symbols: int = 0
    current_symbol: str | None = None
    current_phase: str = "queued"
    started_at: datetime = dataclass_field(default_factory=now_utc)
    updated_at: datetime = dataclass_field(default_factory=now_utc)
    completed_at: datetime | None = None
    response: SpotOpportunityScanResponse | None = None
    warnings: list[str] = dataclass_field(default_factory=list)
    failed_symbols: list[str] = dataclass_field(default_factory=list)
    latest_error: str | None = None
    cancel_requested: bool = False
    thread: Thread | None = None


class SpotScannerJobManager:
    """Small process-local Spot scanner job registry."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._jobs: dict[str, SpotScannerJob] = {}

    def create(self, request: SpotOpportunityScanStartRequest) -> SpotScannerJob:
        job = SpotScannerJob(scan_id=uuid4().hex, request=request)
        with self._lock:
            self._jobs[job.scan_id] = job
        return job

    def set_thread(self, scan_id: str, thread: Thread) -> None:
        with self._lock:
            job = self._jobs.get(scan_id)
            if job is not None:
                job.thread = thread
                job.updated_at = now_utc()

    def get(self, scan_id: str) -> SpotScannerJob | None:
        with self._lock:
            return self._jobs.get(scan_id)

    def update(self, scan_id: str, **updates: object) -> SpotScannerJob | None:
        with self._lock:
            job = self._jobs.get(scan_id)
            if job is None:
                return None
            if job.status == "cancelled" and updates.get("status") != "cancelled":
                return job
            for key, value in updates.items():
                setattr(job, key, value)
            job.updated_at = now_utc()
            return job

    def cancel(self, scan_id: str) -> SpotScannerJob | None:
        with self._lock:
            job = self._jobs.get(scan_id)
            if job is None:
                return None
            job.cancel_requested = True
            job.status = "cancelled"
            job.current_phase = "cancel_requested"
            job.completed_at = now_utc()
            job.latest_error = "Spot scan cancelled by user."
            job.warnings = ["Spot scan cancelled. Partial results remain advisory-only."] if job.response is not None else ["Spot scan cancelled."]
            job.updated_at = now_utc()
            return job


class FuturesOpportunityScanStartRequest(BaseModel):
    """Request body for an async paper-only futures scanner job."""

    quote_asset: str = "USDT"
    limit: int | None = Field(default=None, ge=1)
    max_symbols: int | None = Field(default=None, ge=1)
    concurrency: int = Field(default=5, ge=1, le=10)
    batch_size: int = Field(default=8, ge=5, le=10)
    symbol_timeout_seconds: float = Field(default=7.0, ge=1, le=8)
    scan_timeout_seconds: float = Field(default=45.0, ge=5, le=90)
    horizon: str = "7d"
    min_opportunity_score: int = Field(default=0, ge=0, le=100)
    min_confidence: int = Field(default=0, ge=0, le=100)
    include_weak_evidence: bool = True
    include_avoid: bool = True
    market_sensitivity: Literal["conservative", "balanced", "aggressive"] = "balanced"


class FuturesOpportunityScanJobResponse(BaseModel):
    """Progress snapshot for an async futures scanner job."""

    scan_id: str
    status: FuturesScannerJobStatus
    total_symbols: int = 0
    scanned_symbols: int = 0
    current_symbol: str | None = None
    current_phase: str = "queued"
    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    scan: FuturesOpportunityScanResponse | None = None
    warnings: list[str] = Field(default_factory=list)
    failed_symbols: list[str] = Field(default_factory=list)
    latest_error: str | None = None


@dataclass(slots=True)
class FuturesScannerJob:
    """Mutable in-memory state for one async futures scanner run."""

    scan_id: str
    request: FuturesOpportunityScanStartRequest
    status: FuturesScannerJobStatus = "queued"
    total_symbols: int = 0
    scanned_symbols: int = 0
    current_symbol: str | None = None
    current_phase: str = "queued"
    started_at: datetime = dataclass_field(default_factory=now_utc)
    updated_at: datetime = dataclass_field(default_factory=now_utc)
    completed_at: datetime | None = None
    long_candidates: list[FuturesPaperSignal] = dataclass_field(default_factory=list)
    short_candidates: list[FuturesPaperSignal] = dataclass_field(default_factory=list)
    neutral_candidates: list[FuturesPaperSignal] = dataclass_field(default_factory=list)
    warnings: list[str] = dataclass_field(default_factory=list)
    failed_symbols: list[str] = dataclass_field(default_factory=list)
    response: FuturesOpportunityScanResponse | None = None
    latest_error: str | None = None
    cancel_requested: bool = False
    task: asyncio.Task[None] | None = None
    thread: Thread | None = None


class FuturesScannerJobManager:
    """Small process-local async scanner job registry."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._jobs: dict[str, FuturesScannerJob] = {}

    def create(self, request: FuturesOpportunityScanStartRequest) -> FuturesScannerJob:
        job = FuturesScannerJob(scan_id=uuid4().hex, request=request)
        with self._lock:
            self._jobs[job.scan_id] = job
        return job

    def set_task(self, scan_id: str, task: asyncio.Task[None]) -> None:
        with self._lock:
            job = self._jobs.get(scan_id)
            if job is not None:
                job.task = task
                job.updated_at = now_utc()

    def set_thread(self, scan_id: str, thread: Thread) -> None:
        with self._lock:
            job = self._jobs.get(scan_id)
            if job is not None:
                job.thread = thread
                job.updated_at = now_utc()

    def get(self, scan_id: str) -> FuturesScannerJob | None:
        with self._lock:
            return self._jobs.get(scan_id)

    def update(self, scan_id: str, **updates: object) -> FuturesScannerJob | None:
        with self._lock:
            job = self._jobs.get(scan_id)
            if job is None:
                return None
            if job.status == "cancelled" and updates.get("status") != "cancelled":
                return job
            for key, value in updates.items():
                setattr(job, key, value)
            job.updated_at = now_utc()
            return job

    def cancel(self, scan_id: str) -> FuturesScannerJob | None:
        with self._lock:
            job = self._jobs.get(scan_id)
            if job is None:
                return None
            job.cancel_requested = True
            job.status = "cancelled"
            job.current_phase = "cancel_requested"
            job.completed_at = now_utc()
            job.latest_error = "Scan cancelled by user."
            job.warnings = ["Scan cancelled. Partial results remain advisory-only."] if job.response is not None else ["Scan cancelled."]
            job.updated_at = now_utc()
            task = job.task
        if task is not None and not task.done():
            task.cancel()
        return job


_SPOT_SCANNER_JOB_MANAGER = SpotScannerJobManager()
_FUTURES_SCANNER_JOB_MANAGER = FuturesScannerJobManager()


class FuturesLivePriceItemResponse(BaseModel):
    """Lightweight live price heartbeat for a scanner symbol."""

    symbol: str
    live_price: Decimal | None = None
    updated_at: datetime
    source: Literal["websocket", "rest", "cache", "unavailable"]
    data_source: Literal["binance_usdm_futures"] = "binance_usdm_futures"
    price_type: Literal["mark_price", "futures_last_price"] = "mark_price"
    stale: bool = False
    warning: str | None = None


class FuturesLivePriceResponse(BaseModel):
    """Live price heartbeat response for visible futures scanner candidates."""

    items: list[FuturesLivePriceItemResponse]
    warnings: list[str] = Field(default_factory=list)


class FuturesLiveSubscriptionRequest(BaseModel):
    """Visible scanner symbols for websocket heartbeat subscriptions."""

    symbols: list[str] = Field(default_factory=list)


class FuturesLiveSubscriptionResponse(BaseModel):
    """WebSocket heartbeat subscription state."""

    symbols: list[str] = Field(default_factory=list)
    count: int
    websocket_enabled: bool
    warning: str | None = None


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
    latest_signal_side: str | None = None
    latest_signal_reasons: tuple[str, ...] = ()
    risk_decision: str | None = None
    execution_status: str | None = None
    blocker_category: str | None = None
    blocker_message: str | None = None
    next_possible_trigger: str | None = None
    last_trade_attempt_at: str | None = None


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


class FuturesPaperPositionResponse(BaseModel):
    """Serialized paper Futures position."""

    symbol: str
    side: str
    quantity: Decimal
    entry_price: Decimal
    mark_price: Decimal
    leverage: int
    margin_mode: str
    margin_used: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    liquidation_price_estimate: Decimal
    liquidation_estimate_label: str = "Estimated paper liquidation reference only."
    opened_at: datetime
    updated_at: datetime


class FuturesPaperStatusResponse(BaseModel):
    """Paper Futures runtime status."""

    active: bool
    mode: Literal["paper"] = "paper"
    paper_only: bool = True
    live_futures_trading_enabled: bool = False
    positions: list[FuturesPaperPositionResponse]
    realized_pnl: Decimal


class FuturesPaperExecutionSignalResponse(BaseModel):
    """Deterministic paper Futures signal."""

    symbol: str
    signal: str
    confidence: int
    risk_grade: str
    reason_codes: tuple[str, ...]
    blocker_reason: str | None = None
    paper_only: bool = True
    ai_execution_authority: bool = False


class FuturesPaperOrderRequest(BaseModel):
    """Manual paper Futures request."""

    symbol: str = Field(min_length=1)
    quantity: Decimal = Field(default=Decimal("0.001"), gt=Decimal("0"))
    market_price: Decimal = Field(gt=Decimal("0"))
    leverage: int = Field(default=2, ge=1, le=3)


class FuturesPaperCloseRequest(BaseModel):
    """Manual paper Futures close request."""

    symbol: str = Field(min_length=1)
    market_price: Decimal = Field(gt=Decimal("0"))


class FuturesPaperFillResponse(BaseModel):
    """Serialized paper Futures fill result."""

    order_id: str
    status: str
    symbol: str
    side: str
    filled_quantity: Decimal
    fill_price: Decimal
    fee_paid: Decimal
    realized_pnl: Decimal
    reason_codes: tuple[str, ...]
    paper_only: bool = True


class FuturesPaperPerformanceResponse(BaseModel):
    """Paper Futures performance summary."""

    symbol: str | None
    paper_only: bool
    total_fills: int
    realized_pnl: Decimal
    positions: list[FuturesPaperPositionResponse]
    recent_fills: list[FuturesPaperFillResponse]


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


class SignalTimingAggregateResponse(BaseModel):
    """Aggregated Phase 1 timing-quality metrics for one bucket."""

    label: str
    sample_size: int
    average_move_consumed_pct: Decimal | None = None
    average_move_capture_ratio_pct: Decimal | None = None
    average_entry_efficiency_pct: Decimal | None = None
    average_lead_time_seconds: Decimal | None = None
    average_net_return_after_costs_pct: Decimal | None = None
    late_rate_pct: Decimal
    chase_rate_pct: Decimal
    useful_rate_pct: Decimal


class SignalTimingSampleResponse(BaseModel):
    """One persisted actionable-signal timing measurement."""

    signal_id: str
    horizon: str
    symbol: str
    source: str
    direction: str
    signal_time: datetime
    setup_start_time: datetime | None = None
    setup_start_price: Decimal | None = None
    activation_price: Decimal | None = None
    recent_swing_low: Decimal | None = None
    recent_swing_high: Decimal | None = None
    horizon_end_price: Decimal | None = None
    max_favorable_price: Decimal | None = None
    max_adverse_price: Decimal | None = None
    move_before_signal_pct: Decimal | None = None
    move_after_signal_pct: Decimal | None = None
    max_favorable_excursion_pct: Decimal | None = None
    max_adverse_excursion_pct: Decimal | None = None
    full_move_pct: Decimal | None = None
    move_already_consumed_pct: Decimal | None = None
    move_capture_ratio_pct: Decimal | None = None
    entry_efficiency_pct: Decimal | None = None
    pre_move_lead_time_seconds: int | None = None
    signal_to_entry_latency_seconds: int | None = None
    time_to_target_seconds: int | None = None
    time_to_stop_seconds: int | None = None
    expiry_seconds: int
    net_return_after_costs_pct: Decimal | None = None
    estimated_round_trip_cost_pct: Decimal
    realized_volatility_pct: Decimal | None = None
    regime_label: str | None = None
    liquidity_context: str | None = None
    classification: str
    classification_reasons: list[str]
    outcome_state: str
    evaluated_at: datetime


class SignalTimingBaselineResponse(BaseModel):
    """Phase 1 baseline report proving current signal timing quality."""

    generated_at: datetime
    data_state: Literal["ready", "insufficient_data", "degraded_storage"]
    status_message: str
    actionable_snapshot_count: int
    evaluated_count: int
    pending_count: int
    insufficient_data_count: int
    classification_counts: dict[str, int]
    overall: SignalTimingAggregateResponse
    by_horizon: list[SignalTimingAggregateResponse]
    by_source: list[SignalTimingAggregateResponse]
    recent_samples: list[SignalTimingSampleResponse]
    definitions: dict[str, str]


class ContinuousIntelligenceConfigResponse(BaseModel):
    """Serialized continuous intelligence configuration."""

    enabled: bool
    markets: list[Literal["spot", "futures"]]
    quote_asset: str
    universe_limit: int
    cycle_interval_seconds: int
    universe_refresh_seconds: int
    deep_candidate_limit: int
    fast_score_threshold: int
    concurrency: int
    request_interval_ms: int
    initial_delay_seconds: int


class ContinuousIntelligenceStatusResponse(BaseModel):
    """Continuous scanner lifecycle, progress, lag, and recovery health."""

    enabled: bool
    status: str
    cycle_id: str | None = None
    started_at: datetime | None = None
    last_cycle_started_at: datetime | None = None
    last_cycle_completed_at: datetime | None = None
    last_full_universe_pass_at: datetime | None = None
    last_universe_refresh_at: datetime | None = None
    last_websocket_event_at: datetime | None = None
    next_cycle_at: datetime | None = None
    last_error: str | None = None
    universe_source: str
    total_symbols: int
    fast_screened_symbols: int
    deep_analyzed_symbols: int
    deep_queue_depth: int
    successful_cycles: int
    failed_cycles: int
    consecutive_failures: int
    websocket_events: int
    websocket_state: str
    data_lag_seconds: int | None = None
    warnings: list[str]
    config: ContinuousIntelligenceConfigResponse
    advisory_only: bool
    paper_only: bool


class ContinuousIntelligenceCandidateResponse(BaseModel):
    """Latest fast/deep continuous intelligence for one symbol."""

    market: Literal["spot", "futures"]
    symbol: str
    stage: str
    fast_score: int
    deep_score: int | None = None
    direction_hint: str
    current_price: Decimal | None = None
    triggers: list[str]
    metrics: dict[str, object]
    reasons: list[str]
    warnings: list[str]
    screened_at: datetime
    deep_analyzed_at: datetime | None = None
    data_source: str


class ContinuousIntelligenceCandidatesResponse(BaseModel):
    """Latest persisted continuous candidate collection."""

    generated_at: datetime
    count: int
    candidates: list[ContinuousIntelligenceCandidateResponse]
    advisory_only: bool = True
    paper_only: bool = True


class ContinuousIntelligenceCycleResponse(BaseModel):
    """One persisted continuous scan-cycle summary."""

    cycle_id: str
    started_at: datetime
    completed_at: datetime | None = None
    status: str
    universe_source: str
    total_symbols: int
    fast_screened_symbols: int
    deep_analyzed_symbols: int
    candidate_count: int
    failed_symbols: list[str]
    error_message: str | None = None
    duration_ms: int | None = None


class ContinuousIntelligenceCyclesResponse(BaseModel):
    """Recent persistent full-universe cycle history."""

    generated_at: datetime
    cycles: list[ContinuousIntelligenceCycleResponse]


class ContinuousIntelligenceConfigRequest(BaseModel):
    """Validated operator configuration for later continuous cycles."""

    markets: list[Literal["spot", "futures"]] | None = None
    quote_asset: str | None = Field(default=None, min_length=2, max_length=12)
    universe_limit: int | None = Field(default=None, ge=1, le=100)
    cycle_interval_seconds: int | None = Field(default=None, ge=30, le=3600)
    universe_refresh_seconds: int | None = Field(default=None, ge=300, le=86400)
    deep_candidate_limit: int | None = Field(default=None, ge=1, le=30)
    fast_score_threshold: int | None = Field(default=None, ge=0, le=100)
    concurrency: int | None = Field(default=None, ge=1, le=10)
    request_interval_ms: int | None = Field(default=None, ge=0, le=2000)
    initial_delay_seconds: int | None = Field(default=None, ge=0, le=300)


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
    liquidity_bias = estimate_liquidity_bias(
        LiquidityBiasInput(
            symbol=symbol,
            candles=candles,
            volatility_regime=(
                technical_analysis.volatility_regime
                if technical_analysis is not None and technical_analysis.data_state == "ready"
                else None
            ),
        )
    )
    return SignalAnalysisContext(
        symbol=symbol,
        candles=candles,
        feature_snapshot=feature_snapshot,
        technical_analysis=technical_analysis,
        market_sentiment=market_sentiment,
        symbol_sentiment=symbol_sentiment,
        liquidity_bias=liquidity_bias,
        benchmark_candles=benchmark_candles,
    )


async def _load_crowd_positioning(
    *,
    settings: Settings,
    symbol: str,
) -> tuple[BinanceDerivativesSnapshot, CrowdPositioningSnapshot]:
    """Load Binance funding/OI crowd-positioning inputs with safe fallback."""

    if not settings.binance_derivatives_data_enabled:
        derivatives = fallback_derivatives_snapshot(symbol)
        return derivatives, crowd_positioning_from_derivatives(derivatives)
    derivatives = await get_derivatives_snapshot(symbol, settings=settings)
    crowd = crowd_positioning_from_derivatives(derivatives)
    return derivatives, crowd


def _apply_crowd_positioning_to_context(
    *,
    context: SignalAnalysisContext,
    crowd: CrowdPositioningSnapshot,
    derivatives: BinanceDerivativesSnapshot,
) -> SignalAnalysisContext:
    """Update context liquidity bias with derivatives-based crowd positioning."""

    volatility_regime = (
        context.technical_analysis.volatility_regime
        if context.technical_analysis is not None and context.technical_analysis.data_state == "ready"
        else None
    )
    context.crowd_positioning = crowd
    context.derivatives_data = derivatives
    context.liquidity_bias = estimate_liquidity_bias(
        LiquidityBiasInput(
            symbol=context.symbol,
            candles=context.candles,
            funding_rate=derivatives.funding_rate,
            open_interest_change_pct=derivatives.oi_change_1h or derivatives.oi_change_24h,
            volatility_regime=volatility_regime,
            crowd_positioning=crowd,
        )
    )
    return context


def _load_liquidation_intelligence(
    *,
    symbol: str,
    candles: list[Candle],
    liquidity_zones: LiquidityZoneSnapshot | None = None,
    crowd_positioning: CrowdPositioningSnapshot | None = None,
) -> LiquidationIntelligenceSnapshot:
    """Interpret recent Binance force-order events when the feed is available."""

    service = get_global_liquidation_feed_service()
    if service is None:
        return NEUTRAL_LIQUIDATION_INTELLIGENCE
    try:
        events = service.recent_events(symbol, lookback_minutes=5)
        return interpret_liquidation_events(
            symbol=symbol,
            events=events,
            candles=candles,
            liquidity_zones=liquidity_zones,
            crowd_positioning=crowd_positioning,
        )
    except Exception:
        LOGGER.exception("Failed to interpret liquidation events for %s.", symbol)
        return NEUTRAL_LIQUIDATION_INTELLIGENCE


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


def get_futures_paper_service(request: Request) -> FuturesPaperService:
    """Return the shared paper-only Futures service."""

    if not hasattr(request.app.state, "futures_paper_service"):
        request.app.state.futures_paper_service = FuturesPaperService(
            repository=StorageRepository(get_settings().database_url)
        )
    return request.app.state.futures_paper_service


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


def get_rest_client(request: Request) -> BinanceRestClient:
    """Return the shared Binance REST client from app state."""

    if hasattr(request.app.state, "rest_client"):
        return request.app.state.rest_client
    return BinanceRestClient(get_settings())


def get_futures_scanner_heartbeat_service(request: Request) -> FuturesScannerWebSocketHeartbeatService | None:
    """Return the shared futures scanner WebSocket heartbeat service when available."""

    if hasattr(request.app.state, "futures_scanner_heartbeat_service"):
        return request.app.state.futures_scanner_heartbeat_service
    return None


def get_settings_dependency() -> Settings:
    """Return application settings for bot control routes."""

    return get_settings()


def get_continuous_intelligence_service(
    request: Request,
) -> ContinuousMarketIntelligenceService:
    """Return the backend-owned continuous intelligence service."""

    if hasattr(request.app.state, "continuous_intelligence_service"):
        return request.app.state.continuous_intelligence_service
    raise HTTPException(status_code=503, detail="Continuous market intelligence is unavailable.")


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


def _load_futures_candle_series(
    *,
    repository: StorageRepository,
    symbol: str,
    interval: ChartTimeframe = "1m",
    limit: int | None = None,
):
    """Load stored USD-M Futures candles for selected-symbol charting."""

    end_time = now_utc()
    start_time = end_time - timedelta(days=7)
    stored = [
        _historical_record_to_candle(record)
        for record in repository.get_futures_historical_candles(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
        )
    ]
    if limit is not None:
        stored = stored[-limit:]
    return merge_candles(
        stored_candles=stored,
        live_candles=[],
        interval=interval,
        limit=limit,
    )


def _futures_backfill_status(
    *,
    repository: StorageRepository,
    symbol: str,
    interval: ChartTimeframe,
    lookback_days: int,
    loading: bool = False,
    failed_message: str | None = None,
) -> CandleBackfillStatus:
    """Return USD-M Futures selected-symbol candle coverage."""

    end_time = now_utc()
    start_time = end_time - timedelta(days=lookback_days)
    candles = [
        _historical_record_to_candle(record)
        for record in repository.get_futures_historical_candles(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
        )
    ]
    if not candles:
        status = "failed" if failed_message else ("loading" if loading else "not_started")
        return CandleBackfillStatus(
            symbol=symbol,
            requested_interval=interval,
            requested_lookback_days=lookback_days,
            available_from=None,
            available_to=None,
            candle_count=0,
            coverage_pct=Decimal("0"),
            status=status,
            message=failed_message or (
                f"USD-M Futures {interval} candles for {symbol} are loading."
                if loading
                else f"USD-M Futures {interval} candles for {symbol} have not been loaded yet."
            ),
            last_backfilled_at=None,
            effective_interval=interval,
        )

    latest = candles[-1]
    earliest = candles[0]
    requested_span = timedelta(days=lookback_days)
    actual_span = max(latest.close_time - earliest.open_time, timedelta(0))
    coverage_pct = min(
        Decimal("100"),
        (Decimal(actual_span.total_seconds()) / Decimal(requested_span.total_seconds())) * Decimal("100")
        if requested_span.total_seconds() > 0
        else Decimal("0"),
    ).quantize(Decimal("0.01"))
    if failed_message:
        status = "failed"
        message = failed_message
    elif loading:
        status = "partial"
        message = f"USD-M Futures {interval} candles for {symbol} are still loading."
    elif coverage_pct >= Decimal("50"):
        status = "ready"
        message = f"USD-M Futures {interval} candles are ready for {symbol}."
    else:
        status = "partial"
        message = f"USD-M Futures {interval} candles for {symbol} are only partially backfilled."
    return CandleBackfillStatus(
        symbol=symbol,
        requested_interval=interval,
        requested_lookback_days=lookback_days,
        available_from=earliest.open_time,
        available_to=latest.close_time,
        candle_count=len(candles),
        coverage_pct=coverage_pct,
        status=status,
        message=message,
        last_backfilled_at=latest.event_time,
        effective_interval=interval,
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
        latest_signal_side=None,
        latest_signal_reasons=(),
        risk_decision="skipped",
        execution_status="skipped",
        blocker_category="insufficient_history" if runtime_active else "unknown",
        blocker_message=(
            status.recovery_message
            if status.recovered_from_prior_session and status.symbol == symbol and status.mode == "paused"
            else None
        ),
        next_possible_trigger=(
            "Resume the recovered paper runtime."
            if status.recovered_from_prior_session and status.symbol == symbol and status.mode == "paused"
            else ("Start the paper runtime." if not runtime_active else "More closed candles and feature context.")
        ),
        last_trade_attempt_at=None,
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
        latest_signal_side=readiness.latest_signal_side,
        latest_signal_reasons=readiness.latest_signal_reasons,
        risk_decision=readiness.risk_decision,
        execution_status=readiness.execution_status,
        blocker_category=readiness.blocker_category,
        blocker_message=readiness.blocker_message,
        next_possible_trigger=readiness.next_possible_trigger,
        last_trade_attempt_at=readiness.last_trade_attempt_at,
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


def _to_futures_position_response(position: FuturesPosition) -> FuturesPaperPositionResponse:
    """Convert a paper Futures position to API response."""

    return FuturesPaperPositionResponse(
        symbol=position.symbol,
        side=position.side,
        quantity=position.quantity,
        entry_price=position.entry_price,
        mark_price=position.mark_price,
        leverage=position.leverage,
        margin_mode=position.margin_mode,
        margin_used=position.margin_used,
        unrealized_pnl=position.unrealized_pnl,
        realized_pnl=position.realized_pnl,
        liquidation_price_estimate=position.liquidation_price_estimate,
        opened_at=position.opened_at,
        updated_at=position.updated_at,
    )


def _to_futures_status_response(service: FuturesPaperService) -> FuturesPaperStatusResponse:
    """Convert paper Futures service status to API response."""

    status = service.status()
    return FuturesPaperStatusResponse(
        active=status.active,
        mode="paper",
        paper_only=True,
        live_futures_trading_enabled=False,
        positions=[_to_futures_position_response(position) for position in status.positions],
        realized_pnl=status.realized_pnl,
    )


def _to_futures_signal_engine_response(signal: FuturesSignal) -> FuturesPaperExecutionSignalResponse:
    """Convert deterministic Futures engine signal to API response."""

    return FuturesPaperExecutionSignalResponse(
        symbol=signal.symbol,
        signal=signal.side,
        confidence=signal.confidence,
        risk_grade=signal.risk_grade,
        reason_codes=signal.reason_codes,
        blocker_reason=signal.blocker_reason,
        paper_only=True,
        ai_execution_authority=False,
    )


def _to_futures_fill_response(result: FuturesFillResult) -> FuturesPaperFillResponse:
    """Convert a paper Futures fill to API response."""

    return FuturesPaperFillResponse(
        order_id=result.order_id,
        status=result.status,
        symbol=result.symbol,
        side=result.side,
        filled_quantity=result.filled_quantity,
        fill_price=result.fill_price,
        fee_paid=result.fee_paid,
        realized_pnl=result.realized_pnl,
        reason_codes=result.reason_codes,
        paper_only=True,
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


def _build_heatmap_enrichment(
    *,
    symbol: str,
    price: Decimal | None,
    base_signal_type: str,
    base_confidence: int,
) -> HeatmapSignalEnrichment:
    """Build heatmap metadata without affecting the base signal decision."""

    try:
        return enrich_signal_with_heatmap(
            symbol=symbol,
            price=price,
            base_signal_type=base_signal_type,
            base_confidence=base_confidence,
        )
    except Exception:
        LOGGER.exception("Failed to enrich %s signal with liquidation heatmap metadata.", symbol)
        return enrich_signal_with_heatmap(
            symbol=symbol,
            price=None,
            base_signal_type=base_signal_type,
            base_confidence=base_confidence,
        )


def _build_trading_assistant_response(
    *,
    symbol: str,
    backfill_status: CandleBackfillStatus,
    fusion_signal: FusionSignalResponse,
    technical_analysis: TechnicalAnalysisResponse | None,
    workstation: WorkstationResponse | None,
    similar_setup: SimilarSetupReport | None = None,
    liquidity_bias: LiquidityBiasSnapshot | None = None,
    crowd_positioning: CrowdPositioningSnapshot | None = None,
    derivatives_data: BinanceDerivativesSnapshot | None = None,
    candles: list[Candle] | None = None,
    regime_label: str | None = None,
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
    current_price = workstation.last_price if workstation is not None else None
    atr = workstation.feature.atr if workstation is not None and workstation.feature is not None else None
    if technical_analysis is not None and technical_analysis.data_state == "ready" and decision == "buy":
        nearest_support = technical_analysis.support_levels[-1] if technical_analysis.support_levels else None
        nearest_resistance = technical_analysis.resistance_levels[0] if technical_analysis.resistance_levels else None
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

    liquidity = liquidity_bias or NEUTRAL_LIQUIDITY_BIAS
    crowd = crowd_positioning or NEUTRAL_CROWD_POSITIONING
    derivatives = derivatives_data or fallback_derivatives_snapshot(symbol)
    confidence_score = _liquidity_adjusted_assistant_confidence(
        confidence=confidence_score,
        decision=decision,
        liquidity=liquidity,
    )
    confidence_score = _crowd_adjusted_assistant_confidence(
        confidence=confidence_score,
        decision=decision,
        crowd=crowd,
    )
    if decision == "buy" and crowd.crowd_side == "long_crowded" and crowd.crowd_strength == "high":
        decision = "wait"
        why_not_trade = "Binance funding and open interest show crowded longs with downside squeeze risk."
        simple_reason = f"{simple_reason} Crowd: long heavy downside risk."
    if decision == "buy" and liquidity.trap_risk == "long_trap" and liquidity.liquidity_pressure == "high":
        decision = "wait"
        why_not_trade = "Estimated liquidity positioning shows high downside sweep risk against a fresh long entry."
        simple_reason = f"{simple_reason} Liquidity: high downside sweep risk."
    liquidity_zones = estimate_liquidity_zones(
        symbol=symbol,
        candles=candles or (),
        current_price=current_price,
        trade_direction=_assistant_liquidity_zone_direction(decision=decision, fusion_signal=fusion_signal.final_signal),
        stop_loss=suggested_stop_loss,
        take_profit=suggested_take_profit,
        liquidity_bias=liquidity,
        crowd_positioning=crowd,
        regime_label=regime_label,
        atr=atr,
    )
    liquidation_intelligence = _load_liquidation_intelligence(
        symbol=symbol,
        candles=candles or (),
        liquidity_zones=liquidity_zones,
        crowd_positioning=crowd,
    )
    liquidity_zones = validate_liquidity_zones_with_liquidations(
        zones=liquidity_zones,
        liquidation_signal=liquidation_intelligence.liquidation_signal,
        dominant_side=liquidation_intelligence.dominant_side,
    )
    if decision == "buy" and liquidity_zones.trade_timing_adjustment == "wait_for_sweep":
        decision = "wait"
        confidence_score = max(0, confidence_score - 6)
        why_not_trade = "Estimated liquidity zones show sweep risk against this entry; waiting for the sweep or confirmation is safer in paper mode."
        simple_reason = f"{simple_reason} Liquidity: downside sweep risk."
    elif decision == "buy" and liquidity_zones.trade_timing_adjustment == "avoid_chop":
        decision = "wait"
        confidence_score = max(0, confidence_score - 8)
        why_not_trade = "Estimated liquidity is concentrated on both sides in a choppy structure."
        simple_reason = f"{simple_reason} Liquidity: choppy both-side risk."
    confidence_score = _liquidation_adjusted_assistant_confidence(
        confidence=confidence_score,
        decision=decision,
        liquidation=liquidation_intelligence,
    )
    if decision == "buy" and liquidation_intelligence.liquidation_signal == "cascade_down":
        decision = "wait"
        why_not_trade = "Recent Binance force-order events show downside liquidation cascade risk."
        simple_reason = f"{simple_reason} Liquidation: downside cascade risk."
    elif decision == "sell_exit" and liquidation_intelligence.liquidation_signal == "cascade_up":
        decision = "wait"
        why_not_trade = "Recent Binance force-order events show upside short-squeeze pressure."
        simple_reason = f"{simple_reason} Liquidation: upside squeeze risk."
    elif liquidation_intelligence.liquidation_signal == "exhaustion":
        simple_reason = f"{simple_reason} Liquidation: exhaustion risk."

    heatmap = _build_heatmap_enrichment(
        symbol=symbol,
        price=current_price,
        base_signal_type=_assistant_signal_type(decision),
        base_confidence=confidence_score,
    )

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
        liquidity_bias=liquidity.liquidity_bias,
        liquidity_pressure=liquidity.liquidity_pressure,
        likely_liquidation_direction=liquidity.likely_liquidation_direction,
        trap_risk=liquidity.trap_risk,
        liquidity_explanation=liquidity.explanation,
        upside_liquidity_zone=_to_liquidity_zone_response(liquidity_zones.upside_liquidity_zone),
        downside_liquidity_zone=_to_liquidity_zone_response(liquidity_zones.downside_liquidity_zone),
        nearest_liquidity_target=_to_nearest_liquidity_target_response(liquidity_zones.nearest_liquidity_target),
        sweep_risk=liquidity_zones.sweep_risk,
        trade_timing_adjustment=liquidity_zones.trade_timing_adjustment,
        tp_sl_alignment=liquidity_zones.tp_sl_alignment,
        liquidity_zone_explanation=liquidity_zones.explanation,
        crowd_side=crowd.crowd_side,
        crowd_strength=crowd.crowd_strength,
        squeeze_risk=crowd.squeeze_risk,
        positioning_explanation=crowd.explanation,
        funding_rate=derivatives.funding_rate,
        open_interest=derivatives.open_interest,
        oi_trend=derivatives.oi_trend,
        heatmap_liquidity_above=heatmap.heatmap_liquidity_above,
        heatmap_liquidity_below=heatmap.heatmap_liquidity_below,
        heatmap_intensity_score=heatmap.heatmap_intensity_score,
        heatmap_bias=heatmap.heatmap_bias,
        base_signal_type=heatmap.base_signal_type,
        heatmap_signal_type=heatmap.heatmap_signal_type,
        base_confidence=heatmap.base_confidence,
        heatmap_confidence=heatmap.heatmap_confidence,
        heatmap_alignment=heatmap.heatmap_alignment,
        heatmap_explanation=heatmap.heatmap_explanation,
        heatmap_provider=heatmap.heatmap_provider,
        heatmap_data_quality=heatmap.heatmap_data_quality,
        heatmap_is_real_data=heatmap.heatmap_is_real_data,
        heatmap_provider_status=heatmap.heatmap_provider_status,
        liquidation_pressure=heatmap.liquidation_pressure,
        liquidation_imbalance=heatmap.liquidation_imbalance,
        liquidation_signal=liquidation_intelligence.liquidation_signal,
        liquidation_intensity=liquidation_intelligence.liquidation_intensity,
        dominant_side=liquidation_intelligence.dominant_side,
        liquidation_explanation=liquidation_intelligence.explanation,
        liquidation_volume_long=liquidation_intelligence.liquidation_volume_long,
        liquidation_volume_short=liquidation_intelligence.liquidation_volume_short,
        liquidation_imbalance_ratio=liquidation_intelligence.imbalance_ratio,
        liquidation_event_frequency=liquidation_intelligence.event_frequency,
    )


def _assistant_liquidity_zone_direction(*, decision: str, fusion_signal: str) -> Literal["long", "short", "wait", "avoid", "buy", "sell_exit", "none"]:
    if decision == "buy":
        return "buy"
    if decision == "sell_exit":
        return "sell_exit"
    if fusion_signal == "short":
        return "short"
    if decision == "avoid":
        return "avoid"
    if decision == "wait":
        return "wait"
    return "none"


def _liquidity_adjusted_assistant_confidence(
    *,
    confidence: int,
    decision: str,
    liquidity: LiquidityBiasSnapshot,
) -> int:
    adjustment = 0
    if liquidity.liquidity_pressure == "high":
        adjustment -= 3
    if decision == "buy":
        if liquidity.trap_risk == "long_trap":
            adjustment -= 10 if liquidity.liquidity_pressure == "high" else 5
        elif liquidity.trap_risk == "short_trap":
            adjustment += 4
    return max(0, min(100, confidence + adjustment))


def _crowd_adjusted_assistant_confidence(
    *,
    confidence: int,
    decision: str,
    crowd: CrowdPositioningSnapshot,
) -> int:
    adjustment = 0
    if crowd.crowd_strength == "high":
        if decision == "buy" and crowd.crowd_side == "long_crowded":
            adjustment -= 6
        elif decision == "buy" and crowd.crowd_side == "short_crowded":
            adjustment += 3
    elif crowd.crowd_strength == "medium":
        if decision == "buy" and crowd.crowd_side == "long_crowded":
            adjustment -= 3
        elif decision == "buy" and crowd.crowd_side == "short_crowded":
            adjustment += 2
    return max(0, min(100, confidence + adjustment))


def _liquidation_adjusted_assistant_confidence(
    *,
    confidence: int,
    decision: str,
    liquidation: LiquidationIntelligenceSnapshot,
) -> int:
    adjustment = 0
    if decision == "buy":
        if liquidation.liquidation_signal == "cascade_up":
            adjustment += 4
        elif liquidation.liquidation_signal == "cascade_down":
            adjustment -= 10
    elif decision == "sell_exit":
        if liquidation.liquidation_signal == "cascade_down":
            adjustment += 3
        elif liquidation.liquidation_signal == "cascade_up":
            adjustment -= 8
    if liquidation.liquidation_signal == "exhaustion":
        adjustment -= 5
    return max(0, min(100, confidence + adjustment))


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


def _to_liquidity_zone_response(zone: LiquidityZone | None) -> LiquidityZoneResponse:
    if zone is None:
        return LiquidityZoneResponse()
    return LiquidityZoneResponse(
        level=zone.level,
        strength=zone.strength,
        reason=zone.reason,
    )


def _to_nearest_liquidity_target_response(target: NearestLiquidityTarget | None) -> NearestLiquidityTargetResponse:
    if target is None:
        return NearestLiquidityTargetResponse()
    return NearestLiquidityTargetResponse(
        direction=target.direction,
        level=target.level,
        distance_pct=target.distance_pct,
        strength=target.strength,
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
        liquidity_zone_summary=result.liquidity_zone_summary,
        sweep_risk=result.sweep_risk,
        trade_timing_adjustment=result.trade_timing_adjustment,
        tp_sl_alignment=result.tp_sl_alignment,
        crowd_side=result.crowd_side,
        crowd_strength=result.crowd_strength,
        squeeze_risk=result.squeeze_risk,
        funding_rate=result.funding_rate,
        open_interest=result.open_interest,
        oi_trend=result.oi_trend,
        liquidation_signal=result.liquidation_signal,
        liquidation_intensity=result.liquidation_intensity,
        dominant_side=result.dominant_side,
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


def _to_spot_signal_response(signal: SpotOpportunitySignal) -> SpotOpportunitySignalResponse:
    return SpotOpportunitySignalResponse(
        symbol=signal.symbol,
        action=signal.action,
        opportunity_score=signal.opportunity_score,
        confidence=signal.confidence,
        trend_score=signal.trend_score,
        momentum_score=signal.momentum_score,
        volatility_quality_score=signal.volatility_quality_score,
        liquidity_score=signal.liquidity_score,
        structure_score=signal.structure_score,
        regime_score=signal.regime_score,
        validation_score=signal.validation_score,
        eligibility_score=signal.eligibility_score,
        evidence_strength=signal.evidence_strength,
        trend=signal.trend,
        momentum=signal.momentum,
        best_horizon=signal.best_horizon,
        risk_grade=signal.risk_grade,
        current_price=signal.current_price,
        suggested_entry_zone=signal.suggested_entry_zone,
        suggested_stop_loss=signal.suggested_stop_loss,
        suggested_take_profit=signal.suggested_take_profit,
        regime=signal.regime,
        data_source="binance_spot",
        price_type="spot_last_price",
        reason=signal.reason,
        warnings=list(signal.warnings),
        timestamp=signal.timestamp,
    )


def _to_spot_scan_response(
    report: SpotOpportunityScanReport,
    *,
    quote_asset: str,
    symbol_count: int,
    data_source: Literal["binance_spot", "last_successful_cache", "empty_degraded"] = "binance_spot",
    latest_error: str | None = None,
    latest_successful_scanner_at: datetime | None = None,
    persisted_candidate_count: int = 0,
) -> SpotOpportunityScanResponse:
    return SpotOpportunityScanResponse(
        generated_at=report.generated_at,
        scan_state=report.scan_state,
        warnings=list(report.warnings),
        scanned_count=report.scanned_count,
        failed_symbols=list(report.failed_symbols),
        buy_candidates=[_to_spot_signal_response(signal) for signal in report.buy_candidates],
        watch_candidates=[_to_spot_signal_response(signal) for signal in report.watch_candidates],
        avoid_candidates=[_to_spot_signal_response(signal) for signal in report.avoid_candidates],
        exit_watch_candidates=[_to_spot_signal_response(signal) for signal in report.exit_watch_candidates],
        data_source=data_source,
        quote_asset=quote_asset,
        symbol_count=symbol_count,
        latest_successful_scanner_at=latest_successful_scanner_at,
        latest_error=latest_error,
        persisted_candidate_count=persisted_candidate_count,
    )


def _to_futures_signal_response(signal: FuturesPaperSignal) -> FuturesPaperSignalResponse:
    """Convert a paper futures scanner signal into an API response."""

    heatmap = _build_heatmap_enrichment(
        symbol=signal.symbol,
        price=signal.current_price,
        base_signal_type=_scanner_signal_type(signal.direction),
        base_confidence=signal.confidence,
    )
    return FuturesPaperSignalResponse(
        symbol=signal.symbol,
        direction=signal.direction,
        opportunity_score=signal.opportunity_score,
        direction_score=signal.direction_score,
        momentum_score=signal.momentum_score,
        trend_score=signal.trend_score,
        volatility_quality_score=signal.volatility_quality_score,
        liquidity_score=signal.liquidity_score,
        risk_score=signal.risk_score,
        validation_score=signal.validation_score,
        confidence=signal.confidence,
        evidence_strength=signal.evidence_strength,
        trend=signal.trend,
        momentum=signal.momentum,
        best_horizon=signal.best_horizon,
        risk_grade=signal.risk_grade,
        regime=signal.regime,
        current_price=signal.current_price,
        market_sensitivity=signal.market_sensitivity,
        slow_market_setup=signal.slow_market_setup,
        slow_market_reason=signal.slow_market_reason,
        data_source="binance_usdm_futures",
        price_type=signal.price_type,
        reason=signal.reason,
        invalidation_hint=signal.invalidation_hint,
        suggested_entry_zone=signal.suggested_entry_zone,
        suggested_stop_loss=signal.suggested_stop_loss,
        suggested_take_profit=signal.suggested_take_profit,
        estimated_fee_impact=signal.estimated_fee_impact,
        leverage_suggestion=signal.leverage_suggestion,
        liquidation_safety_note=signal.liquidation_safety_note,
        similar_setup_summary=signal.similar_setup_summary,
        eligibility_status=signal.eligibility_status,
        warnings=list(signal.warnings),
        timestamp=signal.timestamp,
        liquidity_bias=signal.liquidity_bias,
        liquidity_pressure=signal.liquidity_pressure,
        likely_liquidation_direction=signal.likely_liquidation_direction,
        trap_risk=signal.trap_risk,
        liquidity_explanation=signal.liquidity_explanation,
        upside_liquidity_zone=LiquidityZoneResponse(
            level=signal.upside_liquidity_zone_level,
            strength=signal.upside_liquidity_zone_strength,
            reason=signal.upside_liquidity_zone_reason,
        ),
        downside_liquidity_zone=LiquidityZoneResponse(
            level=signal.downside_liquidity_zone_level,
            strength=signal.downside_liquidity_zone_strength,
            reason=signal.downside_liquidity_zone_reason,
        ),
        nearest_liquidity_target=NearestLiquidityTargetResponse(
            direction=signal.nearest_liquidity_target_direction,
            level=signal.nearest_liquidity_target_level,
            distance_pct=signal.nearest_liquidity_target_distance_pct,
            strength=signal.nearest_liquidity_target_strength,
        ),
        sweep_risk=signal.sweep_risk,
        trade_timing_adjustment=signal.trade_timing_adjustment,
        tp_sl_alignment=signal.tp_sl_alignment,
        liquidity_zone_explanation=signal.liquidity_zone_explanation,
        liquidity_adjusted_note=signal.liquidity_adjusted_note,
        crowd_side=signal.crowd_side,
        crowd_strength=signal.crowd_strength,
        squeeze_risk=signal.squeeze_risk,
        funding_rate=signal.funding_rate,
        open_interest=signal.open_interest,
        oi_trend=signal.oi_trend,
        heatmap_liquidity_above=heatmap.heatmap_liquidity_above,
        heatmap_liquidity_below=heatmap.heatmap_liquidity_below,
        heatmap_intensity_score=heatmap.heatmap_intensity_score,
        heatmap_bias=heatmap.heatmap_bias,
        base_signal_type=heatmap.base_signal_type,
        heatmap_signal_type=heatmap.heatmap_signal_type,
        base_confidence=heatmap.base_confidence,
        heatmap_confidence=heatmap.heatmap_confidence,
        heatmap_alignment=heatmap.heatmap_alignment,
        heatmap_explanation=heatmap.heatmap_explanation,
        heatmap_provider=heatmap.heatmap_provider,
        heatmap_data_quality=heatmap.heatmap_data_quality,
        heatmap_is_real_data=heatmap.heatmap_is_real_data,
        heatmap_provider_status=heatmap.heatmap_provider_status,
        liquidation_pressure=heatmap.liquidation_pressure,
        liquidation_imbalance=heatmap.liquidation_imbalance,
        liquidation_signal=signal.liquidation_signal,
        liquidation_intensity=signal.liquidation_intensity,
        dominant_side=signal.dominant_side,
        liquidation_explanation=signal.liquidation_explanation,
        liquidation_volume_long=signal.liquidation_volume_long,
        liquidation_volume_short=signal.liquidation_volume_short,
        liquidation_imbalance_ratio=signal.liquidation_imbalance_ratio,
        liquidation_event_frequency=signal.liquidation_event_frequency,
    )


def _to_futures_scan_response(report: FuturesOpportunityScanReport) -> FuturesOpportunityScanResponse:
    """Convert paper futures scanner report into the API response shape."""

    candidate_count = (
        len(report.long_candidates)
        + len(report.short_candidates)
        + len(report.neutral_candidates)
    )
    fallback_symbol_count = (
        len(_manual_futures_symbol_fallback("USDT"))
        if report.futures_symbol_universe_source == "fallback"
        else 0
    )
    data_source = "fallback_scan" if report.futures_symbol_universe_source == "fallback" else "live_scan"
    if report.futures_symbol_universe_source == "cache":
        data_source = "symbol_universe_cache"
    return FuturesOpportunityScanResponse(
        generated_at=report.generated_at,
        scan_state=report.scan_state,
        long_candidates=[_to_futures_signal_response(signal) for signal in report.long_candidates],
        short_candidates=[_to_futures_signal_response(signal) for signal in report.short_candidates],
        neutral_candidates=[_to_futures_signal_response(signal) for signal in report.neutral_candidates],
        warnings=report.warnings,
        scanned_count=report.scanned_count,
        failed_symbols=report.failed_symbols,
        futures_symbol_universe_source=report.futures_symbol_universe_source,  # type: ignore[arg-type]
        symbol_count=report.symbol_count,
        last_successful_fetch_at=report.last_successful_fetch_at,
        latest_error=report.latest_error,
        data_source=data_source,
        latest_successful_scanner_at=report.generated_at if report.scan_state != "degraded" else None,
        latest_scanner_error=report.latest_error,
        persisted_candidate_count=candidate_count,
        fallback_symbol_count=fallback_symbol_count,
    )


def _build_futures_paper_signal_for_symbol(
    *,
    scanner: FuturesOpportunityScanner,
    symbol: str,
    horizon: str,
    runtime: PaperBotRuntime,
    repository: StorageRepository,
    sentiment_service: SymbolSentimentService,
    backfill_service: HistoricalBackfillService,
) -> FuturesPaperSignal:
    """Build one paper-only futures scanner signal without touching execution."""

    context = _build_signal_analysis_context(
        runtime=runtime,
        repository=repository,
        symbol=symbol,
        sentiment_service=sentiment_service,
    )
    workstation_state, _, _ = _safe_workstation_state(runtime, symbol)
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
    technical_analysis, _ = _safe_technical_analysis(
        runtime,
        repository,
        symbol,
        context=context,
    )
    technical_response = _to_technical_analysis_response(
        symbol=symbol,
        analysis=technical_analysis,
        data_state=(
            "ready"
            if technical_analysis is not None and technical_analysis.data_state == "ready"
            else "waiting_for_history"
        ),
        status_message=technical_analysis.status_message if technical_analysis is not None else None,
    )
    fusion_analysis, _ = _safe_fusion_signal(
        symbol=symbol,
        runtime=runtime,
        repository=repository,
        sentiment_service=sentiment_service,
        workstation_state=workstation_state,
        context=context,
    )
    fusion_state, fusion_message = _derive_fusion_data_state(
        symbol=symbol,
        status=runtime.status(),
        analysis=fusion_analysis,
        analysis_failed=False,
    )
    fusion_response = _to_fusion_signal_response(
        symbol=symbol,
        analysis=fusion_analysis,
        data_state=fusion_state,
        status_message=fusion_message,
    )
    backfill_status = backfill_service.status(symbol=symbol, interval="1m", lookback_days=7)
    pattern_analysis, _ = _safe_pattern_analysis(
        runtime,
        symbol=symbol,
        horizon=horizon,
        repository=repository,
        candles=context.candles,
    )
    regime_analysis, _ = _safe_regime_analysis(
        symbol=symbol,
        horizon=horizon,
        runtime=runtime,
        repository=repository,
        sentiment_service=sentiment_service,
        context=context,
    )
    assistant = _build_trading_assistant_response(
        symbol=symbol,
        backfill_status=backfill_status,
        fusion_signal=fusion_response,
        technical_analysis=technical_response,
        workstation=workstation,
        liquidity_bias=context.liquidity_bias,
        crowd_positioning=context.crowd_positioning,
        derivatives_data=context.derivatives_data,
        candles=context.candles,
        regime_label=regime_analysis.regime_label if regime_analysis is not None else None,
    )
    current_snapshot = _build_signal_validation_snapshot_record(
        symbol=symbol,
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
        symbol=symbol,
        horizon=fusion_response.preferred_horizon,
    )
    blocker_reasons = current_snapshot.blocker_reasons if current_snapshot is not None else ()
    liquidity_zones = _estimate_assistant_liquidity_zones(
        symbol=symbol,
        candles=context.candles,
        workstation=workstation,
        assistant=assistant,
        fusion_signal=fusion_response,
        liquidity_bias=context.liquidity_bias,
        regime_analysis=regime_analysis,
        crowd_positioning=context.crowd_positioning,
    )
    liquidation_intelligence = _load_liquidation_intelligence(
        symbol=symbol,
        candles=context.candles,
        liquidity_zones=liquidity_zones,
        crowd_positioning=context.crowd_positioning,
    )
    liquidity_zones = validate_liquidity_zones_with_liquidations(
        zones=liquidity_zones,
        liquidation_signal=liquidation_intelligence.liquidation_signal,
        dominant_side=liquidation_intelligence.dominant_side,
    )
    eligibility = evaluate_trade_eligibility(
        TradeEligibilityInput(
            symbol=symbol,
            action=assistant.decision,
            confidence=assistant.confidence_score,
            risk_grade=assistant.risk_label,
            preferred_horizon=fusion_response.preferred_horizon,
            expected_edge_pct=fusion_response.expected_edge_pct,
            estimated_cost_pct=current_snapshot.estimated_cost_pct if current_snapshot is not None else None,
            blocker_reasons=blocker_reasons,
            current_warnings=tuple(fusion_response.warnings),
            regime_label=regime_analysis.regime_label if regime_analysis is not None else None,
            regime_confidence=regime_analysis.confidence if regime_analysis is not None else None,
            regime_warnings=regime_analysis.risk_warnings if regime_analysis is not None else (),
            regime_avoid_conditions=regime_analysis.avoid_conditions if regime_analysis is not None else (),
            similar_setup=similar_setup,
            signal_validation=validation_report,
            liquidity_bias=context.liquidity_bias,
            liquidity_zones=liquidity_zones,
            crowd_positioning=context.crowd_positioning,
            funding_rate=context.derivatives_data.funding_rate if context.derivatives_data is not None else None,
            open_interest=context.derivatives_data.open_interest if context.derivatives_data is not None else None,
            oi_trend=context.derivatives_data.oi_trend if context.derivatives_data is not None else "neutral",
            liquidation_intelligence=liquidation_intelligence,
        )
    )
    return scanner.analyze_symbol(
        FuturesSignalContext(
            symbol=symbol,
            candles=context.candles,
            technical_analysis=technical_analysis,
            regime_analysis=regime_analysis,
            similar_setup=similar_setup,
            trade_eligibility=eligibility,
            preferred_horizon=fusion_response.preferred_horizon,
            expected_edge_pct=fusion_response.expected_edge_pct,
            invalidation_hint=fusion_response.invalidation_hint,
            blocker_reasons=blocker_reasons,
            warnings=tuple(fusion_response.warnings),
            spread_ratio_pct=_spread_ratio_pct(runtime=runtime, symbol=symbol),
            liquidity_bias=context.liquidity_bias,
            liquidity_zones=liquidity_zones,
            crowd_positioning=context.crowd_positioning,
            funding_rate=context.derivatives_data.funding_rate if context.derivatives_data is not None else None,
            open_interest=context.derivatives_data.open_interest if context.derivatives_data is not None else None,
            oi_trend=context.derivatives_data.oi_trend if context.derivatives_data is not None else "neutral",
            liquidation_intelligence=liquidation_intelligence,
        )
    )


def _spread_ratio_pct(*, runtime: PaperBotRuntime, symbol: str) -> Decimal | None:
    top_of_book_getter = getattr(runtime, "top_of_book", None)
    top = top_of_book_getter(symbol) if callable(top_of_book_getter) else None
    if top is None or top.bid_price <= Decimal("0"):
        return None
    return (((top.ask_price - top.bid_price) / top.bid_price) * Decimal("100")).quantize(
        Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )


def _estimate_assistant_liquidity_zones(
    *,
    symbol: str,
    candles: list[Candle],
    workstation: WorkstationResponse | None,
    assistant: TradingAssistantResponse,
    fusion_signal: FusionSignalResponse,
    liquidity_bias: LiquidityBiasSnapshot,
    regime_analysis: RegimeAnalysisSnapshot | None,
    crowd_positioning: CrowdPositioningSnapshot | None = None,
) -> LiquidityZoneSnapshot:
    current_price = workstation.last_price if workstation is not None else (candles[-1].close if candles else None)
    atr = workstation.feature.atr if workstation is not None and workstation.feature is not None else None
    return estimate_liquidity_zones(
        symbol=symbol,
        candles=candles,
        current_price=current_price,
        trade_direction=_assistant_liquidity_zone_direction(
            decision=assistant.decision,
            fusion_signal=fusion_signal.final_signal,
        ),
        stop_loss=assistant.suggested_stop_loss,
        take_profit=assistant.suggested_take_profit,
        liquidity_bias=liquidity_bias,
        crowd_positioning=crowd_positioning,
        regime_label=regime_analysis.regime_label if regime_analysis is not None else None,
        atr=atr,
    )


def _persist_assistant_outcome_snapshot(
    *,
    repository: StorageRepository,
    symbol: str,
    assistant: TradingAssistantResponse,
    current_price: Decimal | None,
) -> None:
    try:
        persist_signal_snapshot(
            repository=repository,
            payload=SignalSnapshotInput(
                symbol=symbol,
                source="assistant",
                signal_type=_assistant_signal_type(assistant.decision),
                confidence=assistant.confidence_score,
                entry_price=current_price,
                liquidity_bias=assistant.liquidity_bias,
                sweep_risk=assistant.sweep_risk,
                nearest_liquidity_above=(
                    assistant.nearest_liquidity_target.level
                    if assistant.nearest_liquidity_target.direction == "up"
                    else assistant.upside_liquidity_zone.level
                ),
                nearest_liquidity_below=(
                    assistant.nearest_liquidity_target.level
                    if assistant.nearest_liquidity_target.direction == "down"
                    else assistant.downside_liquidity_zone.level
                ),
                funding_rate=assistant.funding_rate,
                open_interest=assistant.open_interest,
                notes=assistant.simple_reason,
            ),
        )
    except Exception:
        LOGGER.exception("Failed to persist post-signal assistant snapshot for %s.", symbol)


def _persist_eligibility_outcome_snapshot(
    *,
    repository: StorageRepository,
    symbol: str,
    assistant: TradingAssistantResponse,
    eligibility: TradeEligibilityResponse,
    current_price: Decimal | None,
) -> None:
    try:
        persist_signal_snapshot(
            repository=repository,
            payload=SignalSnapshotInput(
                symbol=symbol,
                source="eligibility",
                signal_type=_eligibility_signal_type(eligibility.status, assistant.decision),
                confidence=assistant.confidence_score,
                entry_price=current_price,
                liquidity_bias=assistant.liquidity_bias,
                sweep_risk=eligibility.sweep_risk,
                nearest_liquidity_above=assistant.upside_liquidity_zone.level,
                nearest_liquidity_below=assistant.downside_liquidity_zone.level,
                funding_rate=assistant.funding_rate,
                open_interest=assistant.open_interest,
                notes=eligibility.reason,
            ),
        )
    except Exception:
        LOGGER.exception("Failed to persist post-signal eligibility snapshot for %s.", symbol)


def _persist_scanner_outcome_snapshots(
    *,
    repository: StorageRepository,
    report: FuturesOpportunityScanReport,
) -> None:
    for signal in report.long_candidates + report.short_candidates + report.neutral_candidates:
        try:
            persist_signal_snapshot(
                repository=repository,
                payload=SignalSnapshotInput(
                    symbol=signal.symbol,
                    source="scanner",
                    signal_type=_scanner_signal_type(signal.direction),
                    confidence=signal.confidence,
                    entry_price=signal.current_price,
                    liquidity_bias=signal.liquidity_bias,
                    sweep_risk=signal.sweep_risk,
                    nearest_liquidity_above=signal.upside_liquidity_zone_level,
                    nearest_liquidity_below=signal.downside_liquidity_zone_level,
                    funding_rate=signal.funding_rate,
                    open_interest=signal.open_interest,
                    notes=signal.reason,
                ),
            )
        except Exception:
            LOGGER.exception("Failed to persist post-signal scanner snapshot for %s.", signal.symbol)


def _persist_spot_scanner_outcome_snapshots(
    *,
    repository: StorageRepository,
    report: SpotOpportunityScanReport,
) -> None:
    for signal in (
        report.buy_candidates
        + report.watch_candidates
        + report.exit_watch_candidates
        + report.avoid_candidates
    ):
        try:
            persist_signal_snapshot(
                repository=repository,
                payload=SignalSnapshotInput(
                    symbol=signal.symbol,
                    source="spot_scanner",
                    signal_type=_spot_scanner_signal_type(signal.action),
                    confidence=signal.confidence,
                    entry_price=signal.current_price,
                    notes=signal.reason,
                    timestamp=signal.timestamp,
                ),
            )
        except Exception:
            LOGGER.exception("Failed to persist post-signal Spot scanner snapshot for %s.", signal.symbol)


def _persist_scanner_run_candidates(
    *,
    repository: StorageRepository,
    scan_id: str,
    report: FuturesOpportunityScanReport,
    response: FuturesOpportunityScanResponse,
    quote_asset: str,
    horizon: str,
    max_symbols: int,
    min_opportunity_score: int,
) -> None:
    """Persist scanner run and candidate rows for later review."""

    all_candidates = report.long_candidates + report.short_candidates + report.neutral_candidates
    candidate_count = len(all_candidates)
    repository.upsert_scanner_run(
        ScannerRunRecord(
            id=scan_id,
            generated_at=report.generated_at,
            quote_asset=quote_asset,
            horizon=horizon,
            max_symbols=max_symbols,
            min_opportunity_score=min_opportunity_score,
            scan_state=report.scan_state,
            scanned_count=report.scanned_count,
            failed_symbols_json=json.dumps(report.failed_symbols),
            warnings_json=json.dumps(report.warnings),
            result_json=response.model_dump_json(),
            candidate_count=candidate_count,
        )
    )
    candidate_records = [
        ScannerCandidateRecord(
            id=f"{scan_id}:{signal.symbol}:{signal.direction}",
            scanner_run_id=scan_id,
            symbol=signal.symbol,
            direction=signal.direction,
            opportunity_score=signal.opportunity_score,
            confidence=signal.confidence,
            evidence_strength=signal.evidence_strength,
            current_price=signal.current_price,
            entry_zone=signal.suggested_entry_zone,
            stop_loss=signal.suggested_stop_loss,
            take_profit=signal.suggested_take_profit,
            risk_grade=signal.risk_grade,
            regime=signal.regime,
            reason=signal.reason,
            warnings_json=json.dumps(signal.warnings),
            timestamp=signal.timestamp,
        )
        for signal in all_candidates
    ]
    repository.upsert_scanner_candidates(candidate_records)
    repository.upsert_scanner_candidate_prices(
        [
            ScannerCandidatePriceRecord(
                id=None,
                scanner_candidate_id=f"{scan_id}:{signal.symbol}:{signal.direction}",
                symbol=signal.symbol,
                price=signal.current_price,
                price_type=signal.price_type,
                source=signal.data_source,
                recorded_at=signal.timestamp,
            )
            for signal in all_candidates
        ]
    )


def _persist_spot_scanner_run_candidates(
    *,
    repository: StorageRepository,
    scan_id: str,
    report: SpotOpportunityScanReport,
    response: SpotOpportunityScanResponse,
    quote_asset: str,
    horizon: str,
    max_symbols: int,
    min_opportunity_score: int,
) -> None:
    """Persist Spot scanner run and candidates for later review."""

    all_candidates = (
        report.buy_candidates
        + report.watch_candidates
        + report.exit_watch_candidates
        + report.avoid_candidates
    )
    candidate_count = len(all_candidates)
    repository.upsert_scanner_run(
        ScannerRunRecord(
            id=scan_id,
            generated_at=report.generated_at,
            quote_asset=_spot_scanner_quote_key(quote_asset),
            horizon=horizon,
            max_symbols=max_symbols,
            min_opportunity_score=min_opportunity_score,
            scan_state=report.scan_state,
            scanned_count=report.scanned_count,
            failed_symbols_json=json.dumps(report.failed_symbols),
            warnings_json=json.dumps(report.warnings),
            result_json=response.model_dump_json(),
            candidate_count=candidate_count,
        )
    )
    candidate_records = [
        ScannerCandidateRecord(
            id=f"{scan_id}:{signal.symbol}:{signal.action}",
            scanner_run_id=scan_id,
            symbol=signal.symbol,
            direction=signal.action,
            opportunity_score=signal.opportunity_score,
            confidence=signal.confidence,
            evidence_strength=signal.evidence_strength,
            current_price=signal.current_price,
            entry_zone=signal.suggested_entry_zone,
            stop_loss=signal.suggested_stop_loss,
            take_profit=signal.suggested_take_profit,
            risk_grade=signal.risk_grade,
            regime=signal.regime,
            reason=signal.reason,
            warnings_json=json.dumps(signal.warnings),
            timestamp=signal.timestamp,
        )
        for signal in all_candidates
    ]
    repository.upsert_scanner_candidates(candidate_records)
    repository.upsert_scanner_candidate_prices(
        [
            ScannerCandidatePriceRecord(
                id=None,
                scanner_candidate_id=f"{scan_id}:{signal.symbol}:{signal.action}",
                symbol=signal.symbol,
                price=signal.current_price,
                price_type=signal.price_type,
                source=signal.data_source,
                recorded_at=signal.timestamp,
            )
            for signal in all_candidates
        ]
    )


def _persist_spot_scanner_validation_snapshots(
    *,
    repository: StorageRepository,
    report: SpotOpportunityScanReport,
    scan_id: str,
) -> int:
    """Persist Spot scanner candidates into validation snapshots."""

    grouped: list[tuple[str, list[SpotOpportunitySignal]]] = [
        ("spot_buy_candidate", report.buy_candidates),
        ("spot_watch", report.watch_candidates),
        ("spot_exit_watch", report.exit_watch_candidates),
        ("spot_avoid", report.avoid_candidates),
    ]
    snapshots: list[ScannerValidationSnapshotRecord] = []
    for group_name, signals in grouped:
        for index, signal in enumerate(signals, start=1):
            snapshots.append(
                ScannerValidationSnapshotRecord(
                    id=None,
                    scan_id=scan_id,
                    symbol=signal.symbol,
                    direction=_spot_validation_direction(signal.action),
                    price_at_scan=signal.current_price,
                    opportunity_score=signal.opportunity_score,
                    confidence=signal.confidence,
                    horizon=signal.best_horizon,
                    risk_grade=signal.risk_grade,
                    trend_score=signal.trend_score,
                    momentum_score=signal.momentum_score,
                    volatility_quality_score=signal.volatility_quality_score,
                    liquidity_score=signal.liquidity_score,
                    risk_score=100 - signal.eligibility_score,
                    direction_score=signal.structure_score,
                    validation_score=signal.validation_score,
                    evidence_strength=signal.evidence_strength,
                    stop_loss=signal.suggested_stop_loss,
                    take_profit=signal.suggested_take_profit,
                    timestamp=signal.timestamp,
                    rank_position=index,
                    candidate_group=group_name,
                    regime_label=signal.regime,
                    data_source=signal.data_source,
                )
            )
    return repository.insert_scanner_validation_snapshots(snapshots)


def _latest_successful_scanner_response(
    *,
    repository: StorageRepository,
    quote_asset: str,
    horizon: str,
    latest_error: str | None,
    universe_source: FuturesSymbolUniverseSource,
    fallback_symbol_count: int,
) -> FuturesOpportunityScanResponse | None:
    """Load the latest persisted full scanner result for degraded fallback."""

    run = repository.get_latest_successful_scanner_run(quote_asset=quote_asset, horizon=horizon)
    if run is None or not run.result_json:
        return None
    try:
        cached = FuturesOpportunityScanResponse.model_validate(json.loads(run.result_json))
    except Exception:
        LOGGER.exception("Failed to parse cached scanner result %s.", run.id)
        return None
    warnings = [
        "Binance API unavailable; showing last successful scanner result.",
        *[
            warning
            for warning in cached.warnings
            if warning != "Binance API unavailable; showing last successful scanner result."
        ],
    ]
    return cached.model_copy(
        update={
            "scan_state": "degraded",
            "warnings": warnings,
            "data_source": "last_successful_cache",
            "futures_symbol_universe_source": universe_source,
            "latest_successful_scanner_at": run.generated_at,
            "latest_scanner_error": latest_error,
            "latest_error": latest_error,
            "persisted_candidate_count": run.candidate_count,
            "fallback_symbol_count": fallback_symbol_count,
        }
    )


def _latest_successful_spot_scanner_response(
    *,
    repository: StorageRepository,
    quote_asset: str,
    horizon: str,
    latest_error: str | None,
) -> SpotOpportunityScanResponse | None:
    """Load the latest persisted full Spot scanner result for degraded fallback."""

    run = repository.get_latest_successful_scanner_run(
        quote_asset=_spot_scanner_quote_key(quote_asset),
        horizon=horizon,
    )
    if run is None or not run.result_json:
        return None
    try:
        cached = SpotOpportunityScanResponse.model_validate(json.loads(run.result_json))
    except Exception:
        LOGGER.exception("Failed to parse cached Spot scanner result %s.", run.id)
        return None
    warnings = [
        "Binance Spot API unavailable; showing last successful Spot scanner result.",
        *[
            warning
            for warning in cached.warnings
            if warning != "Binance Spot API unavailable; showing last successful Spot scanner result."
        ],
    ]
    return cached.model_copy(
        update={
            "scan_state": "degraded",
            "warnings": warnings,
            "data_source": "last_successful_cache",
            "latest_successful_scanner_at": run.generated_at,
            "latest_error": latest_error,
            "persisted_candidate_count": run.candidate_count,
        }
    )


def _empty_degraded_spot_scanner_response(
    *,
    quote_asset: str,
    latest_error: str | None,
    failed_symbols: list[str] | None = None,
) -> SpotOpportunityScanResponse:
    return SpotOpportunityScanResponse(
        generated_at=datetime.now(tz=UTC),
        scan_state="degraded",
        warnings=["No cached Spot scanner results are available and the Spot symbol universe is unavailable."],
        scanned_count=0,
        failed_symbols=failed_symbols or [],
        data_source="empty_degraded",
        quote_asset=quote_asset,
        symbol_count=0,
        latest_successful_scanner_at=None,
        latest_error=latest_error,
        persisted_candidate_count=0,
    )


def _empty_degraded_scanner_response(
    *,
    universe_source: FuturesSymbolUniverseSource,
    latest_error: str | None,
    fallback_symbol_count: int,
    failed_symbols: list[str] | None = None,
) -> FuturesOpportunityScanResponse:
    """Return a stable empty scanner state when no cached result exists."""

    warning = "No scanner results yet. Run scanner when Binance API is available."
    if universe_source == "fallback":
        warning = "No fallback symbols could be scanned. Run scanner again when Binance USD-M klines are available."
    elif universe_source == "unavailable":
        warning = "No cached scanner results are available and the USD-M symbol universe is unavailable."
    return FuturesOpportunityScanResponse(
        generated_at=datetime.now(tz=UTC),
        scan_state="degraded",
        warnings=[warning],
        scanned_count=0,
        failed_symbols=failed_symbols or [],
        futures_symbol_universe_source=universe_source,
        symbol_count=0,
        last_successful_fetch_at=None,
        latest_error=latest_error,
        data_source="empty_degraded",
        latest_successful_scanner_at=None,
        latest_scanner_error=latest_error,
        persisted_candidate_count=0,
        fallback_symbol_count=fallback_symbol_count,
    )


def _to_futures_scan_job_response(job: FuturesScannerJob) -> FuturesOpportunityScanJobResponse:
    return FuturesOpportunityScanJobResponse(
        scan_id=job.scan_id,
        status=job.status,
        total_symbols=job.total_symbols,
        scanned_symbols=job.scanned_symbols,
        current_symbol=job.current_symbol,
        current_phase=job.current_phase,
        started_at=job.started_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
        scan=job.response,
        warnings=list(job.warnings),
        failed_symbols=list(job.failed_symbols),
        latest_error=job.latest_error,
    )


def _to_spot_scan_job_response(job: SpotScannerJob) -> SpotOpportunityScanJobResponse:
    return SpotOpportunityScanJobResponse(
        scan_id=job.scan_id,
        status=job.status,
        total_symbols=job.total_symbols,
        scanned_symbols=job.scanned_symbols,
        current_symbol=job.current_symbol,
        current_phase=job.current_phase,
        started_at=job.started_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
        scan=job.response,
        warnings=list(job.warnings),
        failed_symbols=list(job.failed_symbols),
        latest_error=job.latest_error,
    )


def _build_async_spot_scan_report(
    *,
    scanner: SpotOpportunityScanner,
    signals: list[SpotOpportunitySignal],
    failed_symbols: list[str],
    include_avoid: bool,
    scanned_symbols: int,
    partial: bool,
) -> SpotOpportunityScanReport:
    report = scanner.build_report(
        signals=signals,
        failed_symbols=failed_symbols,
        include_avoid=include_avoid,
    )
    report.scanned_count = scanned_symbols
    if partial:
        report.scan_state = "partial"
        if "Spot scanner is still running; partial results are shown." not in report.warnings:
            report.warnings.append("Spot scanner is still running; partial results are shown.")
    return report


async def _run_spot_opportunity_scan_job(
    *,
    scan_id: str,
    settings: Settings,
    rest_client: BinanceRestClient | None,
) -> None:
    job = _SPOT_SCANNER_JOB_MANAGER.get(scan_id)
    if job is None:
        return

    request = job.request
    normalized_quote = request.quote_asset.strip().upper() or "USDT"
    scan_limit = min(
        request.max_symbols if request.max_symbols is not None else request.limit if request.limit is not None else 50,
        100,
    )
    try:
        normalized_horizon = _normalize_futures_scanner_horizon(request.horizon)
    except ValueError as exc:
        _SPOT_SCANNER_JOB_MANAGER.update(
            scan_id,
            status="failed",
            current_phase="failed",
            completed_at=now_utc(),
            latest_error=str(exc),
            warnings=[str(exc)],
        )
        return

    scanner = SpotOpportunityScanner()
    worker_rest_client = rest_client or BinanceRestClient(settings)
    close_worker_rest_client = rest_client is None
    repository = StorageRepository(settings.database_url)
    signals: list[SpotOpportunitySignal] = []
    failed_symbols: list[str] = []
    candle_cache: dict[tuple[str, SupportedInterval], list[Candle]] = {}
    semaphore = asyncio.Semaphore(request.concurrency)
    current_threshold = max(request.min_opportunity_score, request.min_confidence)
    total_started_at = time.perf_counter()

    async def scan_symbol(record: SpotSymbolRecord) -> SpotOpportunitySignal | None:
        async with semaphore:
            current_job = _SPOT_SCANNER_JOB_MANAGER.get(scan_id)
            if current_job is not None and current_job.cancel_requested:
                return None
            _SPOT_SCANNER_JOB_MANAGER.update(
                scan_id,
                current_symbol=record.symbol,
                current_phase="spot_candle_fetch",
            )
            try:
                signal = await asyncio.wait_for(
                    _build_market_wide_spot_signal_for_symbol(
                        scanner=scanner,
                        symbol=record.symbol,
                        horizon=normalized_horizon,
                        repository=repository,
                        rest_client=worker_rest_client,
                        candle_cache=candle_cache,
                    ),
                    timeout=request.symbol_timeout_seconds,
                )
            except asyncio.TimeoutError:
                LOGGER.warning(
                    "Timed out paper Spot scan; scan_id=%s symbol=%s timeout_seconds=%.1f",
                    scan_id,
                    record.symbol,
                    request.symbol_timeout_seconds,
                )
                failed_symbols.append(record.symbol)
                return None
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("Failed to scan paper Spot opportunity; scan_id=%s symbol=%s", scan_id, record.symbol)
                failed_symbols.append(record.symbol)
                return None

            if signal.action == "buy_candidate":
                if signal.opportunity_score < current_threshold or signal.confidence < request.min_confidence:
                    return None
                return signal
            if signal.action in {"watch", "exit_watch"} or request.include_avoid:
                return signal
            return None

    try:
        _SPOT_SCANNER_JOB_MANAGER.update(scan_id, status="running", current_phase="loading_spot_universe")
        symbol_service = SpotSymbolService(worker_rest_client)
        candidates = await symbol_service.search_symbols(query="", limit=scan_limit)
        candidates = [record for record in candidates if record.quote_asset.upper() == normalized_quote]
        _SPOT_SCANNER_JOB_MANAGER.update(
            scan_id,
            total_symbols=len(candidates),
            current_phase="spot_universe_ready",
        )
        if not candidates:
            latest_error = f"No active Binance Spot {normalized_quote} symbols are available."
            cached_response = _latest_successful_spot_scanner_response(
                repository=repository,
                quote_asset=normalized_quote,
                horizon=normalized_horizon,
                latest_error=latest_error,
            )
            response = cached_response or _empty_degraded_spot_scanner_response(
                quote_asset=normalized_quote,
                latest_error=latest_error,
            )
            _SPOT_SCANNER_JOB_MANAGER.update(
                scan_id,
                status="failed",
                current_phase="failed",
                completed_at=now_utc(),
                response=response,
                latest_error=latest_error,
                warnings=list(response.warnings),
            )
            return

        deadline = time.perf_counter() + request.scan_timeout_seconds
        batch_size = min(10, max(5, request.batch_size))
        for start_index in range(0, len(candidates), batch_size):
            current_job = _SPOT_SCANNER_JOB_MANAGER.get(scan_id)
            if current_job is None or current_job.cancel_requested:
                raise asyncio.CancelledError()
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                failed_symbols.extend(record.symbol for record in candidates[start_index:])
                break
            batch = candidates[start_index:start_index + batch_size]
            _SPOT_SCANNER_JOB_MANAGER.update(
                scan_id,
                status="running" if not signals else "partial",
                current_symbol=batch[0].symbol if batch else None,
                current_phase="scanning_spot_batch",
            )
            task_by_symbol = {
                asyncio.create_task(scan_symbol(record), name=f"spot-scan-job-{scan_id}-{record.symbol}"): record.symbol
                for record in batch
            }
            done, pending = await asyncio.wait(task_by_symbol.keys(), timeout=max(0.1, remaining))
            for task in pending:
                symbol = task_by_symbol[task]
                task.cancel()
                failed_symbols.append(symbol)
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            current_job = _SPOT_SCANNER_JOB_MANAGER.get(scan_id)
            if current_job is None or current_job.cancel_requested:
                raise asyncio.CancelledError()
            for task in done:
                result = task.result()
                if result is not None:
                    signals.append(result)

            scanned_symbols = min(start_index + len(batch), len(candidates))
            partial = scanned_symbols < len(candidates)
            _SPOT_SCANNER_JOB_MANAGER.update(
                scan_id,
                scanned_symbols=scanned_symbols,
                failed_symbols=list(failed_symbols),
                current_phase="ranking_spot_partial" if partial else "ranking_spot_final",
            )
            report = _build_async_spot_scan_report(
                scanner=scanner,
                signals=signals,
                failed_symbols=failed_symbols,
                include_avoid=request.include_avoid,
                scanned_symbols=scanned_symbols,
                partial=partial,
            )
            response = _to_spot_scan_response(
                report,
                quote_asset=normalized_quote,
                symbol_count=len(candidates),
            )
            _SPOT_SCANNER_JOB_MANAGER.update(
                scan_id,
                status="partial" if partial else "running",
                response=response,
                warnings=list(report.warnings),
            )
            if pending:
                break

        current_job = _SPOT_SCANNER_JOB_MANAGER.get(scan_id)
        if current_job is None or current_job.cancel_requested:
            raise asyncio.CancelledError()
        report = _build_async_spot_scan_report(
            scanner=scanner,
            signals=signals,
            failed_symbols=failed_symbols,
            include_avoid=request.include_avoid,
            scanned_symbols=min(len(candidates), current_job.scanned_symbols),
            partial=bool(failed_symbols) and bool(signals),
        )
        if not signals and failed_symbols:
            latest_error = "spot_klines_unavailable: no requested Spot symbols returned candles."
            cached_response = _latest_successful_spot_scanner_response(
                repository=repository,
                quote_asset=normalized_quote,
                horizon=normalized_horizon,
                latest_error=latest_error,
            )
            response = cached_response or _empty_degraded_spot_scanner_response(
                quote_asset=normalized_quote,
                latest_error=latest_error,
                failed_symbols=failed_symbols,
            )
        else:
            response = _to_spot_scan_response(
                report,
                quote_asset=normalized_quote,
                symbol_count=len(candidates),
            )
            _SPOT_SCANNER_JOB_MANAGER.update(scan_id, current_phase="persisting_spot_completed")
            try:
                _persist_spot_scanner_run_candidates(
                    repository=repository,
                    scan_id=scan_id,
                    report=report,
                    response=response,
                    quote_asset=normalized_quote,
                    horizon=normalized_horizon,
                    max_symbols=scan_limit,
                    min_opportunity_score=request.min_opportunity_score,
                )
                response.persisted_candidate_count = (
                    len(report.buy_candidates)
                    + len(report.watch_candidates)
                    + len(report.exit_watch_candidates)
                    + len(report.avoid_candidates)
                )
            except Exception:
                LOGGER.exception("Failed to persist async Spot scanner run candidates.")
                response.warnings.append("Spot scanner candidate persistence failed; visible results are still usable for this session.")
            try:
                _persist_spot_scanner_validation_snapshots(
                    repository=repository,
                    report=report,
                    scan_id=scan_id,
                )
            except Exception:
                LOGGER.exception("Failed to persist async Spot scanner validation snapshots.")
                response.warnings.append(
                    "Spot scanner validation snapshot persistence failed; this scan will not be included in scanner validation reports."
                )
            _persist_spot_scanner_outcome_snapshots(repository=repository, report=report)

        _SPOT_SCANNER_JOB_MANAGER.update(
            scan_id,
            status="completed",
            scanned_symbols=response.scanned_count,
            current_symbol=None,
            current_phase="completed",
            completed_at=now_utc(),
            response=response,
            failed_symbols=list(response.failed_symbols),
            warnings=list(response.warnings),
            latest_error=response.latest_error,
        )
        LOGGER.info("Async Spot scanner total scan time %.3fs scan_id=%s.", time.perf_counter() - total_started_at, scan_id)
    except asyncio.CancelledError:
        current = _SPOT_SCANNER_JOB_MANAGER.get(scan_id)
        _SPOT_SCANNER_JOB_MANAGER.update(
            scan_id,
            status="cancelled",
            current_symbol=None,
            current_phase="cancelled",
            completed_at=now_utc(),
            response=current.response if current is not None else None,
            latest_error="Spot scan cancelled by user.",
            warnings=["Spot scan cancelled. Partial results remain advisory-only."] if current is not None and current.response is not None else ["Spot scan cancelled."],
        )
    except Exception as exc:
        LOGGER.exception("Async Spot scanner job failed; scan_id=%s.", scan_id)
        latest_error = f"{type(exc).__name__}: {exc}"
        cached_response = None
        try:
            cached_response = _latest_successful_spot_scanner_response(
                repository=repository,
                quote_asset=normalized_quote,
                horizon=normalized_horizon,
                latest_error=latest_error,
            )
        except Exception:
            LOGGER.exception("Failed to load cached Spot scanner response after scan failure.")
        _SPOT_SCANNER_JOB_MANAGER.update(
            scan_id,
            status="failed",
            current_symbol=None,
            current_phase="failed",
            completed_at=now_utc(),
            response=cached_response,
            latest_error=latest_error,
            warnings=["Spot scanner failed. Last successful results are still shown."],
        )
    finally:
        repository.close()
        if close_worker_rest_client:
            await worker_rest_client.close()


def _build_async_futures_scan_report(
    *,
    scanner: FuturesOpportunityScanner,
    signals: list[FuturesPaperSignal],
    failed_symbols: list[str],
    include_avoid: bool,
    universe_source: FuturesSymbolUniverseSource,
    symbol_count: int,
    scanned_symbols: int,
    last_successful_fetch_at: datetime | None,
    latest_error: str | None,
    universe_warnings: list[str],
    partial: bool,
) -> FuturesOpportunityScanReport:
    report = scanner.build_report(
        signals=signals,
        failed_symbols=failed_symbols,
        include_avoid=include_avoid,
    )
    report.scanned_count = scanned_symbols
    report.futures_symbol_universe_source = universe_source
    report.symbol_count = symbol_count
    report.last_successful_fetch_at = last_successful_fetch_at
    report.latest_error = latest_error
    report.warnings.extend(universe_warnings)
    if partial:
        report.scan_state = "partial"
        if "Scanner is still running; partial results are shown." not in report.warnings:
            report.warnings.append("Scanner is still running; partial results are shown.")
    elif universe_source in {"cache", "fallback"} and report.scan_state == "ready":
        report.scan_state = "partial"
    return report


async def _run_futures_opportunity_scan_job(
    *,
    scan_id: str,
    settings: Settings,
    rest_client: BinanceRestClient | None,
) -> None:
    job = _FUTURES_SCANNER_JOB_MANAGER.get(scan_id)
    if job is None:
        return

    request = job.request
    normalized_quote = request.quote_asset.strip().upper() or "USDT"
    scan_limit = min(
        request.max_symbols if request.max_symbols is not None else request.limit if request.limit is not None else 50,
        100,
    )
    fallback_symbol_count = len(_manual_futures_symbol_fallback(normalized_quote))
    try:
        normalized_horizon = _normalize_futures_scanner_horizon(request.horizon)
    except ValueError as exc:
        _FUTURES_SCANNER_JOB_MANAGER.update(
            scan_id,
            status="failed",
            current_phase="failed",
            completed_at=now_utc(),
            latest_error=str(exc),
            warnings=[str(exc)],
        )
        return

    scanner = FuturesOpportunityScanner()
    total_started_at = time.perf_counter()
    worker_rest_client = rest_client or BinanceRestClient(settings)
    close_worker_rest_client = rest_client is None
    repository = StorageRepository(settings.database_url)
    signals: list[FuturesPaperSignal] = []
    failed_symbols: list[str] = []
    candle_cache: dict[tuple[str, SupportedInterval], list[Candle]] = {}
    semaphore = asyncio.Semaphore(request.concurrency)
    threshold_floor = 60 if request.market_sensitivity == "aggressive" else 0
    sensitivity_discount = 8 if request.market_sensitivity == "aggressive" else 0
    current_threshold = max(threshold_floor, max(request.min_opportunity_score, request.min_confidence) - sensitivity_discount)

    async def scan_symbol(record: SpotSymbolRecord) -> FuturesPaperSignal | None:
        async with semaphore:
            current_job = _FUTURES_SCANNER_JOB_MANAGER.get(scan_id)
            if current_job is not None and current_job.cancel_requested:
                return None
            symbol_started_at = time.perf_counter()
            _FUTURES_SCANNER_JOB_MANAGER.update(
                scan_id,
                current_symbol=record.symbol,
                current_phase="futures_candle_fetch",
            )
            try:
                signal = await asyncio.wait_for(
                    _build_market_wide_futures_signal_for_symbol(
                        scanner=scanner,
                        symbol=record.symbol,
                        horizon=normalized_horizon,
                        repository=repository,
                        rest_client=worker_rest_client,
                        settings=settings,
                        candle_cache=candle_cache,
                        market_sensitivity=request.market_sensitivity,
                    ),
                    timeout=request.symbol_timeout_seconds,
                )
            except asyncio.TimeoutError:
                LOGGER.warning(
                    "Timed out futures-paper async scan; scan_id=%s phase=symbol_scan symbol=%s endpoint=/fapi/v1/klines exception_type=TimeoutError timeout_seconds=%.1f",
                    scan_id,
                    record.symbol,
                    request.symbol_timeout_seconds,
                )
                failed_symbols.append(record.symbol)
                return None
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception(
                    "Failed to scan async paper futures opportunity; scan_id=%s phase=symbol_scan symbol=%s endpoint=/fapi/v1/klines",
                    scan_id,
                    record.symbol,
                )
                failed_symbols.append(record.symbol)
                return None
            finally:
                LOGGER.debug(
                    "Async futures scanner symbol %s finished in %.3fs.",
                    record.symbol,
                    time.perf_counter() - symbol_started_at,
                )

            weak_validation = signal.evidence_strength in {"insufficient", "unvalidated", "weak"}
            if signal.direction in {"long", "short"}:
                if signal.opportunity_score < current_threshold:
                    return None
                if weak_validation and not request.include_weak_evidence:
                    return None
                return signal
            if signal.direction == "wait" or request.include_avoid:
                return signal
            return None

    try:
        _FUTURES_SCANNER_JOB_MANAGER.update(scan_id, status="running", current_phase="loading_universe")
        universe_started_at = time.perf_counter()
        universe = await _load_futures_symbol_universe(
            rest_client=worker_rest_client,
            quote_asset=normalized_quote,
            limit=scan_limit,
        )
        LOGGER.info(
            "Async futures scanner universe load %.3fs source=%s symbols=%d scan_id=%s.",
            time.perf_counter() - universe_started_at,
            universe.source,
            len(universe.records),
            scan_id,
        )
        candidates = universe.records
        _FUTURES_SCANNER_JOB_MANAGER.update(
            scan_id,
            total_symbols=len(candidates),
            current_phase="symbol_universe_ready",
        )
        if universe.source == "unavailable" or not candidates:
            latest_error = universe.latest_error or "No USD-M Futures symbol universe is available."
            cached_response = _latest_successful_scanner_response(
                repository=repository,
                quote_asset=normalized_quote,
                horizon=normalized_horizon,
                latest_error=latest_error,
                universe_source=universe.source,
                fallback_symbol_count=fallback_symbol_count,
            )
            response = cached_response or _empty_degraded_scanner_response(
                universe_source=universe.source,
                latest_error=latest_error,
                fallback_symbol_count=fallback_symbol_count,
            )
            _FUTURES_SCANNER_JOB_MANAGER.update(
                scan_id,
                status="failed",
                current_phase="failed",
                completed_at=now_utc(),
                response=response,
                latest_error=latest_error,
                warnings=["Scanner failed. Last successful results are still shown."],
            )
            return

        universe_warnings: list[str] = []
        if universe.source == "cache":
            universe_warnings.append(
                "Using cached USD-M Futures symbol universe because live Binance exchangeInfo is unavailable or recently cached."
            )
        elif universe.source == "fallback":
            universe_warnings.append("Live USD-M symbol universe unavailable; using curated fallback list.")

        deadline = time.perf_counter() + request.scan_timeout_seconds
        batch_size = min(10, max(5, request.batch_size))
        scan_started_at = time.perf_counter()
        for start_index in range(0, len(candidates), batch_size):
            current_job = _FUTURES_SCANNER_JOB_MANAGER.get(scan_id)
            if current_job is None or current_job.cancel_requested:
                raise asyncio.CancelledError()
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                remaining_symbols = [record.symbol for record in candidates[start_index:]]
                failed_symbols.extend(remaining_symbols)
                break
            batch = candidates[start_index:start_index + batch_size]
            _FUTURES_SCANNER_JOB_MANAGER.update(
                scan_id,
                status="running" if not signals else "partial",
                current_symbol=batch[0].symbol if batch else None,
                current_phase="scanning_batch",
            )
            task_by_symbol = {
                asyncio.create_task(scan_symbol(record), name=f"futures-scan-job-{scan_id}-{record.symbol}"): record.symbol
                for record in batch
            }
            done, pending = await asyncio.wait(task_by_symbol.keys(), timeout=max(0.1, remaining))
            for task in pending:
                symbol = task_by_symbol[task]
                task.cancel()
                failed_symbols.append(symbol)
                LOGGER.warning(
                    "Async futures scanner request timed out; scan_id=%s phase=scan_timeout symbol=%s endpoint=/bot/futures-opportunities/scan exception_type=TimeoutError timeout_seconds=%.1f",
                    scan_id,
                    symbol,
                    request.scan_timeout_seconds,
                )
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            current_job = _FUTURES_SCANNER_JOB_MANAGER.get(scan_id)
            if current_job is None or current_job.cancel_requested:
                raise asyncio.CancelledError()
            for task in done:
                result = task.result()
                if result is not None:
                    signals.append(result)

            scanned_symbols = min(start_index + len(batch), len(candidates))
            partial = scanned_symbols < len(candidates)
            _FUTURES_SCANNER_JOB_MANAGER.update(
                scan_id,
                scanned_symbols=scanned_symbols,
                failed_symbols=list(failed_symbols),
                current_phase="ranking_partial" if partial else "ranking_final",
            )
            ranking_started_at = time.perf_counter()
            report = _build_async_futures_scan_report(
                scanner=scanner,
                signals=signals,
                failed_symbols=failed_symbols,
                include_avoid=request.include_avoid,
                universe_source=universe.source,
                symbol_count=len(candidates),
                scanned_symbols=scanned_symbols,
                last_successful_fetch_at=universe.last_successful_fetch_at,
                latest_error=universe.latest_error,
                universe_warnings=universe_warnings,
                partial=partial,
            )
            response = _to_futures_scan_response(report)
            LOGGER.info(
                "Async futures scanner ranking %.3fs scan_id=%s scanned=%d/%d candidates=%d.",
                time.perf_counter() - ranking_started_at,
                scan_id,
                scanned_symbols,
                len(candidates),
                len(signals),
            )
            _FUTURES_SCANNER_JOB_MANAGER.update(
                scan_id,
                status="partial" if partial else "running",
                response=response,
                long_candidates=list(report.long_candidates),
                short_candidates=list(report.short_candidates),
                neutral_candidates=list(report.neutral_candidates),
                warnings=list(report.warnings),
            )
            if pending:
                break

        LOGGER.info(
            "Async futures scanner analyzed %d/%d symbols in %.3fs with concurrency=%d scan_id=%s.",
            len(signals),
            len(candidates),
            time.perf_counter() - scan_started_at,
            request.concurrency,
            scan_id,
        )
        current_job = _FUTURES_SCANNER_JOB_MANAGER.get(scan_id)
        if current_job is None or current_job.cancel_requested:
            raise asyncio.CancelledError()
        scanned_total = current_job.scanned_symbols
        report = _build_async_futures_scan_report(
            scanner=scanner,
            signals=signals,
            failed_symbols=failed_symbols,
            include_avoid=request.include_avoid,
            universe_source=universe.source,
            symbol_count=len(candidates),
            scanned_symbols=min(len(candidates), scanned_total),
            last_successful_fetch_at=universe.last_successful_fetch_at,
            latest_error=universe.latest_error,
            universe_warnings=universe_warnings,
            partial=bool(failed_symbols) and len(signals) > 0,
        )
        if not signals and failed_symbols:
            latest_error = universe.latest_error or "futures_klines_unavailable: no requested futures symbols returned candles."
            cached_response = _latest_successful_scanner_response(
                repository=repository,
                quote_asset=normalized_quote,
                horizon=normalized_horizon,
                latest_error=latest_error,
                universe_source=universe.source,
                fallback_symbol_count=fallback_symbol_count,
            )
            response = cached_response or _empty_degraded_scanner_response(
                universe_source=universe.source,
                latest_error=latest_error,
                fallback_symbol_count=fallback_symbol_count,
                failed_symbols=failed_symbols,
            )
        else:
            response = _to_futures_scan_response(report)
            _FUTURES_SCANNER_JOB_MANAGER.update(scan_id, current_phase="persisting_completed")
            try:
                _persist_scanner_run_candidates(
                    repository=repository,
                    scan_id=scan_id,
                    report=report,
                    response=response,
                    quote_asset=normalized_quote,
                    horizon=normalized_horizon,
                    max_symbols=scan_limit,
                    min_opportunity_score=request.min_opportunity_score,
                )
            except Exception:
                LOGGER.exception("Failed to persist async futures scanner run candidates.")
                response.warnings.append("Scanner candidate persistence failed; visible results are still usable for this session.")
            try:
                persist_scanner_validation_snapshots(repository=repository, report=report, scan_id=scan_id)
            except Exception:
                LOGGER.exception("Failed to persist async futures scanner validation snapshots.")
                response.warnings.append(
                    "Scanner validation snapshot persistence failed; this scan will not be included in paper validation reports."
                )
            _persist_scanner_outcome_snapshots(repository=repository, report=report)

        completed_at = now_utc()
        _FUTURES_SCANNER_JOB_MANAGER.update(
            scan_id,
            status="completed",
            scanned_symbols=response.scanned_count,
            current_symbol=None,
            current_phase="completed",
            completed_at=completed_at,
            response=response,
            long_candidates=list(report.long_candidates) if signals else [],
            short_candidates=list(report.short_candidates) if signals else [],
            neutral_candidates=list(report.neutral_candidates) if signals else [],
            failed_symbols=list(failed_symbols),
            warnings=list(response.warnings),
            latest_error=response.latest_error,
        )
        LOGGER.info("Async futures scanner total scan time %.3fs scan_id=%s.", time.perf_counter() - total_started_at, scan_id)
    except asyncio.CancelledError:
        current = _FUTURES_SCANNER_JOB_MANAGER.get(scan_id)
        _FUTURES_SCANNER_JOB_MANAGER.update(
            scan_id,
            status="cancelled",
            current_symbol=None,
            current_phase="cancelled",
            completed_at=now_utc(),
            response=current.response if current is not None else None,
            latest_error="Scan cancelled by user.",
            warnings=["Scan cancelled. Partial results remain advisory-only."] if current is not None and current.response is not None else ["Scan cancelled."],
        )
    except Exception as exc:
        LOGGER.exception("Async futures scanner job failed; scan_id=%s.", scan_id)
        latest_error = f"{type(exc).__name__}: {exc}"
        cached_response = None
        try:
            cached_response = _latest_successful_scanner_response(
                repository=repository,
                quote_asset=normalized_quote,
                horizon=normalized_horizon,
                latest_error=latest_error,
                universe_source="unavailable",
                fallback_symbol_count=fallback_symbol_count,
            )
        except Exception:
            LOGGER.exception("Failed to load cached scanner response after async scan failure.")
        _FUTURES_SCANNER_JOB_MANAGER.update(
            scan_id,
            status="failed",
            current_symbol=None,
            current_phase="failed",
            completed_at=now_utc(),
            response=cached_response,
            latest_error=latest_error,
            warnings=["Scanner failed. Last successful results are still shown."],
        )
    finally:
        repository.close()
        if close_worker_rest_client:
            await worker_rest_client.close()


def _assistant_signal_type(decision: str) -> str:
    if decision == "buy":
        return "BUY"
    if decision == "sell_exit":
        return "SELL"
    if decision == "avoid":
        return "AVOID"
    return "WAIT"


def _eligibility_signal_type(status: str, assistant_decision: str) -> str:
    if status == "eligible":
        return _assistant_signal_type(assistant_decision)
    if status == "not_eligible":
        return "AVOID"
    return "WAIT"


def _scanner_signal_type(direction: str) -> str:
    if direction == "long":
        return "BUY"
    if direction == "short":
        return "SELL"
    if direction == "avoid":
        return "AVOID"
    return "WAIT"


def _spot_scanner_quote_key(quote_asset: str) -> str:
    return f"SPOT:{quote_asset.strip().upper() or 'USDT'}"


def _spot_validation_direction(action: str) -> str:
    if action == "buy_candidate":
        return "long"
    if action == "exit_watch":
        return "wait"
    if action == "avoid":
        return "avoid"
    return "wait"


def _spot_scanner_signal_type(action: str) -> str:
    if action == "buy_candidate":
        return "BUY"
    if action == "exit_watch":
        return "SELL"
    if action == "avoid":
        return "AVOID"
    return "WAIT"


async def _build_market_wide_spot_signal_for_symbol(
    *,
    scanner: SpotOpportunityScanner,
    symbol: str,
    horizon: str,
    repository: StorageRepository,
    rest_client: BinanceRestClient,
    candle_cache: dict[tuple[str, SupportedInterval], list[Candle]] | None = None,
) -> SpotOpportunitySignal:
    """Build one scanner signal from stored/fresh Binance Spot OHLCV data."""

    started_at = time.perf_counter()
    candles_15m = await _load_or_fetch_spot_scan_candles(
        repository=repository,
        rest_client=rest_client,
        symbol=symbol,
        interval="15m",
        lookback_days=7,
        candle_cache=candle_cache,
    )
    technical_analysis: TechnicalAnalysisSnapshot | None = None
    feature_snapshot: FeatureSnapshot | None = None
    if len(candles_15m) >= 24:
        try:
            feature_snapshot = FeatureEngine(FeatureConfig()).build_snapshot(candles_15m)
            technical_analysis = TechnicalAnalysisService().analyze(
                symbol=symbol,
                candles=candles_15m,
                feature_snapshot=feature_snapshot,
            )
        except Exception:
            LOGGER.exception("Failed to build Spot scanner technical analysis for %s.", symbol)
            technical_analysis = None
            feature_snapshot = None
    pattern_analysis = None
    try:
        pattern_analysis = HorizonPatternAnalysisService().analyze(
            symbol=symbol,
            horizon=horizon,
            points=[_to_pattern_point_from_candle(candle) for candle in candles_15m],
            runtime_active=False,
        )
    except Exception:
        LOGGER.exception("Failed to build Spot scanner pattern analysis for %s.", symbol)
    regime_analysis = None
    try:
        regime_analysis = RegimeAnalysisService().analyze(
            symbol=symbol,
            horizon=horizon,
            candles=candles_15m,
            technical_analysis=technical_analysis,
            pattern_analysis=pattern_analysis,
            feature_snapshot=feature_snapshot,
        )
    except Exception:
        LOGGER.exception("Failed to build Spot scanner regime analysis for %s.", symbol)
    validation_report = None
    try:
        validation_report = _signal_validation_report_for_symbol(
            repository=repository,
            symbol=symbol,
            horizon=horizon,
        )
    except Exception:
        LOGGER.exception("Failed to build Spot scanner validation report for %s.", symbol)
    liquidity_bias = estimate_liquidity_bias(
        LiquidityBiasInput(
            symbol=symbol,
            candles=candles_15m,
            volatility_regime=(
                technical_analysis.volatility_regime
                if technical_analysis is not None and technical_analysis.data_state == "ready"
                else None
            ),
        )
    )
    liquidity_zones = estimate_liquidity_zones(
        symbol=symbol,
        candles=candles_15m,
        current_price=candles_15m[-1].close if candles_15m else None,
        trade_direction="long",
        liquidity_bias=liquidity_bias,
        regime_label=regime_analysis.regime_label if regime_analysis is not None else None,
        atr=feature_snapshot.atr if feature_snapshot is not None else None,
    )
    momentum_edge = _spot_expected_edge_pct(candles_15m)
    blocker_reasons = _spot_scanner_blockers(
        technical_analysis=technical_analysis,
        regime_analysis=regime_analysis,
        candles=candles_15m,
    )
    eligibility = evaluate_trade_eligibility(
        TradeEligibilityInput(
            symbol=symbol,
            action="buy",
            confidence=_spot_preliminary_confidence(technical_analysis=technical_analysis, candles=candles_15m),
            risk_grade=_spot_preliminary_risk_grade(regime_analysis=regime_analysis, candles=candles_15m),
            preferred_horizon=horizon,
            expected_edge_pct=momentum_edge,
            estimated_cost_pct=Decimal("0.20"),
            blocker_reasons=blocker_reasons,
            current_warnings=(),
            regime_label=regime_analysis.regime_label if regime_analysis is not None else None,
            regime_confidence=regime_analysis.confidence if regime_analysis is not None else None,
            regime_warnings=regime_analysis.risk_warnings if regime_analysis is not None else (),
            regime_avoid_conditions=regime_analysis.avoid_conditions if regime_analysis is not None else (),
            similar_setup=None,
            signal_validation=validation_report,
            liquidity_bias=liquidity_bias,
            liquidity_zones=liquidity_zones,
        )
    )
    signal = scanner.build_signal(
        SpotScannerContext(
            symbol=symbol,
            candles=candles_15m,
            technical_analysis=technical_analysis,
            regime_analysis=regime_analysis,
            signal_validation=validation_report,
            trade_eligibility=eligibility,
            spread_ratio_pct=None,
            current_position_quantity=Decimal("0"),
            horizon=horizon,
        )
    )
    LOGGER.info("Spot scanner analysis completed in %.3fs symbol=%s.", time.perf_counter() - started_at, symbol)
    return signal


async def _load_or_fetch_spot_scan_candles(
    *,
    repository: StorageRepository,
    rest_client: BinanceRestClient,
    symbol: str,
    interval: SupportedInterval,
    lookback_days: int,
    candle_cache: dict[tuple[str, SupportedInterval], list[Candle]] | None = None,
) -> list[Candle]:
    """Load cached Spot candles before fetching Binance Spot klines."""

    cache_key = (symbol.upper(), interval)
    if candle_cache is not None and cache_key in candle_cache:
        return candle_cache[cache_key]
    end_time = now_utc()
    start_time = end_time - timedelta(days=lookback_days)
    stored = [
        _historical_record_to_candle(record)
        for record in repository.get_historical_candles(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
        )
    ]
    expected_limit = max(MIN_CANDLES_FOR_FUTURES_SIGNAL, int(timedelta(days=lookback_days) / interval_to_timedelta(interval)))
    if len(stored) >= min(expected_limit, 96):
        if candle_cache is not None:
            candle_cache[cache_key] = stored
        return stored
    rows = await rest_client.get_klines(
        symbol=symbol,
        interval=interval,
        start_time_ms=int(start_time.timestamp() * 1000),
        end_time_ms=int(end_time.timestamp() * 1000),
        limit=min(1000, max(MIN_CANDLES_FOR_FUTURES_SIGNAL, expected_limit)),
    )
    fetched = [
        parse_rest_kline(symbol, interval, row)
        for row in rows
        if int(row[6]) < int(now_utc().timestamp() * 1000)
    ]
    repository.upsert_historical_candles(fetched, source="spot_scanner_rest")
    merged = merge_candles(
        stored_candles=stored,
        live_candles=fetched,
        interval=interval,
        limit=None,
    ).candles
    if candle_cache is not None:
        candle_cache[cache_key] = merged
    return merged


def _spot_expected_edge_pct(candles: list[Candle]) -> Decimal | None:
    if len(candles) < 24 or candles[-24].close <= Decimal("0"):
        return None
    return (((candles[-1].close - candles[-24].close) / candles[-24].close) * Decimal("100")).quantize(Decimal("0.0001"))


def _spot_preliminary_confidence(
    *,
    technical_analysis: TechnicalAnalysisSnapshot | None,
    candles: list[Candle],
) -> int:
    base = technical_analysis.trend_strength_score if technical_analysis is not None and technical_analysis.trend_strength_score is not None else 50
    edge = _spot_expected_edge_pct(candles) or Decimal("0")
    return int(max(0, min(100, Decimal(base) + edge * Decimal("5"))))


def _spot_preliminary_risk_grade(
    *,
    regime_analysis: RegimeAnalysisSnapshot | None,
    candles: list[Candle],
) -> Literal["low", "medium", "high"]:
    if regime_analysis is not None and regime_analysis.regime_label in {"choppy", "high_volatility", "low_liquidity", "trending_down"}:
        return "high"
    if len(candles) < 24:
        return "high"
    ranges = [
        ((candle.high - candle.low) / candle.close) * Decimal("100")
        for candle in candles[-24:]
        if candle.close > Decimal("0")
    ]
    average_range = sum(ranges, start=Decimal("0")) / Decimal(max(1, len(ranges)))
    if average_range >= Decimal("2.5"):
        return "high"
    if average_range >= Decimal("1.5"):
        return "medium"
    return "low"


def _spot_scanner_blockers(
    *,
    technical_analysis: TechnicalAnalysisSnapshot | None,
    regime_analysis: RegimeAnalysisSnapshot | None,
    candles: list[Candle],
) -> tuple[str, ...]:
    blockers: list[str] = []
    if len(candles) < 48:
        blockers.append("insufficient Spot candle history")
    if technical_analysis is not None and technical_analysis.trend_direction == "bearish":
        blockers.append("bearish Spot trend")
    if regime_analysis is not None and regime_analysis.regime_label in {"choppy", "low_liquidity", "high_volatility"}:
        blockers.append(f"{regime_analysis.regime_label} Spot regime")
    return tuple(dict.fromkeys(blockers))


async def _build_market_wide_futures_signal_for_symbol(
    *,
    scanner: FuturesOpportunityScanner,
    symbol: str,
    horizon: str,
    repository: StorageRepository,
    rest_client: BinanceRestClient,
    settings: Settings,
    candle_cache: dict[tuple[str, SupportedInterval], list[Candle]] | None = None,
    market_sensitivity: Literal["conservative", "balanced", "aggressive"] = "balanced",
) -> FuturesPaperSignal:
    """Build one scanner signal from fresh/stored market-wide OHLCV data."""

    started_at = time.perf_counter()
    candles_15m = await _load_or_fetch_futures_scan_candles(
        repository=repository,
        rest_client=rest_client,
        symbol=symbol,
        interval="15m",
        lookback_days=7,
        candle_cache=candle_cache,
    )
    candles_1h = await _load_or_fetch_futures_scan_candles(
        repository=repository,
        rest_client=rest_client,
        symbol=symbol,
        interval="1h",
        lookback_days=7,
        candle_cache=candle_cache,
    )
    technical_analysis: TechnicalAnalysisSnapshot | None = None
    if len(candles_15m) >= 24:
        try:
            feature_snapshot = FeatureEngine(FeatureConfig()).build_snapshot(candles_15m)
            technical_analysis = TechnicalAnalysisService().analyze(
                symbol=symbol,
                candles=candles_15m,
                feature_snapshot=feature_snapshot,
            )
        except Exception:
            LOGGER.exception("Failed to build futures scanner technical analysis for %s.", symbol)
            technical_analysis = None
    derivatives_data, crowd_positioning = await _load_crowd_positioning(
        settings=settings,
        symbol=symbol,
    )
    liquidity_bias = estimate_liquidity_bias(
        LiquidityBiasInput(
            symbol=symbol,
            candles=candles_15m,
            funding_rate=derivatives_data.funding_rate,
            open_interest_change_pct=derivatives_data.oi_change_1h or derivatives_data.oi_change_24h,
            crowd_positioning=crowd_positioning,
            volatility_regime=(
                technical_analysis.volatility_regime
                if technical_analysis is not None and technical_analysis.data_state == "ready"
                else None
            ),
        )
    )
    preliminary_liquidity_zones = estimate_liquidity_zones(
        symbol=symbol,
        candles=candles_15m,
        current_price=candles_15m[-1].close if candles_15m else None,
        liquidity_bias=liquidity_bias,
        crowd_positioning=crowd_positioning,
    )
    liquidation_intelligence = _load_liquidation_intelligence(
        symbol=symbol,
        candles=candles_15m,
        liquidity_zones=preliminary_liquidity_zones,
        crowd_positioning=crowd_positioning,
    )
    preliminary_liquidity_zones = validate_liquidity_zones_with_liquidations(
        zones=preliminary_liquidity_zones,
        liquidation_signal=liquidation_intelligence.liquidation_signal,
        dominant_side=liquidation_intelligence.dominant_side,
    )

    signal = scanner.analyze_symbol(
        FuturesSignalContext(
            symbol=symbol,
            candles=candles_15m,
            higher_timeframe_candles=candles_1h,
            technical_analysis=technical_analysis,
            regime_analysis=None,
            similar_setup=None,
            trade_eligibility=None,
            preferred_horizon=horizon,
            warnings=(),
            liquidity_bias=liquidity_bias,
            liquidity_zones=preliminary_liquidity_zones,
            crowd_positioning=crowd_positioning,
            funding_rate=derivatives_data.funding_rate,
            open_interest=derivatives_data.open_interest,
            oi_trend=derivatives_data.oi_trend,
            liquidation_intelligence=liquidation_intelligence,
            market_sensitivity=market_sensitivity,
        )
    )
    LOGGER.info("Futures scanner analysis completed in %.3fs symbol=%s.", time.perf_counter() - started_at, symbol)
    return signal


async def _load_or_fetch_futures_scan_candles(
    *,
    repository: StorageRepository,
    rest_client: BinanceRestClient,
    symbol: str,
    interval: SupportedInterval,
    lookback_days: int,
    candle_cache: dict[tuple[str, SupportedInterval], list[Candle]] | None = None,
) -> list[Candle]:
    """Load recent USD-M Futures scanner candles, fetching from Binance when local data is stale."""

    cache_key = (symbol.upper(), interval)
    if candle_cache is not None and cache_key in candle_cache:
        return candle_cache[cache_key]

    end_time = now_utc()
    start_time = end_time - timedelta(days=lookback_days)
    cache_started_at = time.perf_counter()
    stored = [
        _historical_record_to_candle(record)
        for record in repository.get_futures_historical_candles(
            symbol=symbol,
            interval=interval,
            start_time=start_time,
            end_time=end_time,
        )
    ]
    LOGGER.info(
        "Futures scanner candle cache read for %s %s returned %d rows in %.3fs.",
        symbol,
        interval,
        len(stored),
        time.perf_counter() - cache_started_at,
    )
    if len(stored) >= MIN_CANDLES_FOR_FUTURES_SIGNAL and not _futures_scan_candles_stale(stored, interval):
        if candle_cache is not None:
            candle_cache[cache_key] = stored
        return stored

    expected_limit = int(timedelta(days=lookback_days) / interval_to_timedelta(interval)) + 4
    fetch_started_at = time.perf_counter()
    rows = await rest_client.get_futures_klines(
        symbol=symbol,
        interval=interval,
        start_time_ms=int(start_time.timestamp() * 1000),
        end_time_ms=int(end_time.timestamp() * 1000),
        limit=min(1000, max(MIN_CANDLES_FOR_FUTURES_SIGNAL, expected_limit)),
    )
    LOGGER.info(
        "Futures scanner Binance USD-M candle fetch for %s %s returned %d rows in %.3fs.",
        symbol,
        interval,
        len(rows),
        time.perf_counter() - fetch_started_at,
    )
    fetched = [
        parse_rest_kline(symbol, interval, row)
        for row in rows
        if len(row) >= 9 and int(row[6]) < int(now_utc().timestamp() * 1000)
    ]
    if fetched:
        repository.upsert_futures_historical_candles(fetched, source="binance_usdm_futures")
        if candle_cache is not None:
            candle_cache[cache_key] = fetched
        return fetched
    if candle_cache is not None:
        candle_cache[cache_key] = stored
    return stored


def _futures_scan_candles_stale(candles: list[Candle], interval: SupportedInterval) -> bool:
    if not candles:
        return True
    return now_utc() - candles[-1].close_time > max(interval_to_timedelta(interval) * 2, timedelta(minutes=30))


def _historical_record_to_candle(record: HistoricalCandleRecord) -> Candle:
    return Candle(
        symbol=record.symbol,
        timeframe=record.interval,
        open=record.open_price,
        high=record.high_price,
        low=record.low_price,
        close=record.close_price,
        volume=record.volume,
        quote_volume=record.quote_volume,
        open_time=record.open_time,
        close_time=record.close_time,
        event_time=record.created_at,
        trade_count=record.trade_count,
        is_closed=True,
    )


def _normalize_futures_scanner_horizon(horizon: str) -> str:
    normalized = horizon.strip().lower()
    if normalized in {"15m", "1h"}:
        return normalized
    return normalize_horizon(normalized)


async def _load_futures_symbol_universe(
    *,
    rest_client: BinanceRestClient,
    quote_asset: str,
    limit: int,
) -> FuturesSymbolUniverseResult:
    """Return active USD-M Futures symbols ranked by futures market activity with cache/fallback diagnostics."""

    started_at = time.perf_counter()
    normalized_quote = quote_asset.upper()
    cache_key = normalized_quote
    cached = _FUTURES_SYMBOL_UNIVERSE_CACHE.get(cache_key)
    if cached is not None and now_utc() - cached.fetched_at <= FUTURES_SYMBOL_UNIVERSE_CACHE_TTL:
        LOGGER.debug(
            "Futures scanner using cached USD-M symbol universe for %s (%d symbols).",
            normalized_quote,
            len(cached.records),
        )
        return FuturesSymbolUniverseResult(
            records=cached.records[:limit],
            source="cache",
            last_successful_fetch_at=cached.fetched_at,
            latest_error=cached.latest_error,
        )

    try:
        exchange_info = await rest_client.get_futures_exchange_info()
        symbols = _parse_futures_exchange_info_symbols(exchange_info, quote_asset=normalized_quote)
        if not symbols:
            raise ValueError(f"No active Binance USD-M Futures symbols found for quote asset {normalized_quote}.")

        ranked = await _rank_futures_symbols_by_volume(
            rest_client=rest_client,
            symbols=symbols,
        )
        fetched_at = now_utc()
        _FUTURES_SYMBOL_UNIVERSE_CACHE[cache_key] = FuturesSymbolUniverseCacheEntry(
            records=ranked,
            fetched_at=fetched_at,
        )
        LOGGER.info(
            "Futures scanner USD-M symbol universe loaded live %d/%d symbols in %.3fs.",
            min(len(ranked), limit),
            len(ranked),
            time.perf_counter() - started_at,
        )
        return FuturesSymbolUniverseResult(
            records=ranked[:limit],
            source="live",
            last_successful_fetch_at=fetched_at,
        )
    except Exception as exc:
        latest_error = f"{type(exc).__name__}: {exc}"
        LOGGER.warning(
            "Futures scanner symbol universe load failed; phase=symbol_universe endpoint=/fapi/v1/exchangeInfo exception_type=%s error=%s",
            type(exc).__name__,
            exc,
        )
        if cached is not None and cached.records:
            cached.latest_error = latest_error
            return FuturesSymbolUniverseResult(
                records=cached.records[:limit],
                source="cache",
                last_successful_fetch_at=cached.fetched_at,
                latest_error=latest_error,
            )
        fallback = _manual_futures_symbol_fallback(normalized_quote)[:limit]
        if fallback:
            return FuturesSymbolUniverseResult(
                records=fallback,
                source="fallback",
                last_successful_fetch_at=None,
                latest_error=latest_error,
            )
        return FuturesSymbolUniverseResult(
            records=[],
            source="unavailable",
            last_successful_fetch_at=None,
            latest_error=latest_error,
        )


def _parse_futures_exchange_info_symbols(
    exchange_info: dict[str, object],
    *,
    quote_asset: str,
) -> list[SpotSymbolRecord]:
    symbols: list[SpotSymbolRecord] = []
    raw_symbols = exchange_info.get("symbols", [])
    if not isinstance(raw_symbols, list):
        raise ValueError("Binance USD-M Futures exchangeInfo response did not include a symbol list.")
    for raw_symbol in raw_symbols:
        if not isinstance(raw_symbol, dict):
            continue
        symbol = str(raw_symbol.get("symbol", "")).upper()
        quote = str(raw_symbol.get("quoteAsset", "")).upper()
        status = str(raw_symbol.get("status", "")).upper()
        contract_type = str(raw_symbol.get("contractType", "")).upper()
        if not symbol or quote != quote_asset or status != "TRADING":
            continue
        if contract_type and contract_type != "PERPETUAL":
            continue
        symbols.append(
            SpotSymbolRecord(
                symbol=symbol,
                base_asset=str(raw_symbol.get("baseAsset", "")).upper(),
                quote_asset=quote,
                status=status,
            )
        )
    return symbols


async def _rank_futures_symbols_by_volume(
    *,
    rest_client: BinanceRestClient,
    symbols: list[SpotSymbolRecord],
) -> list[SpotSymbolRecord]:
    ranked = sorted(symbols, key=lambda item: item.symbol)
    try:
        tickers = await rest_client.get_futures_ticker_24h()
    except Exception:
        LOGGER.warning(
            "Failed to rank USD-M Futures symbols by ticker volume; phase=symbol_universe endpoint=/fapi/v1/ticker/24hr",
            exc_info=True,
        )
        return ranked

    symbol_lookup = {record.symbol: record for record in symbols}
    ranked_pairs: list[tuple[Decimal, SpotSymbolRecord]] = []
    for ticker in tickers:
        symbol = str(ticker.get("symbol", "")).upper()
        if symbol not in symbol_lookup:
            continue
        try:
            quote_volume = Decimal(str(ticker.get("quoteVolume", "0")))
        except Exception:
            quote_volume = Decimal("0")
        ranked_pairs.append((quote_volume, symbol_lookup[symbol]))
    if not ranked_pairs:
        return ranked
    return [record for _, record in sorted(ranked_pairs, key=lambda item: (-item[0], item[1].symbol))]


def _manual_futures_symbol_fallback(quote_asset: str) -> list[SpotSymbolRecord]:
    if quote_asset != "USDT":
        return []
    return [
        SpotSymbolRecord(
            symbol=symbol,
            base_asset=symbol.removesuffix("USDT"),
            quote_asset="USDT",
            status="TRADING",
        )
        for symbol in FUTURES_SCANNER_FALLBACK_SYMBOLS
    ]


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


@router.get("/bot/futures/status", response_model=FuturesPaperStatusResponse)
def get_futures_paper_status(
    service: Annotated[FuturesPaperService, Depends(get_futures_paper_service)],
) -> FuturesPaperStatusResponse:
    """Return paper-only Futures runtime status."""

    return _to_futures_status_response(service)


@router.post("/bot/futures/start", response_model=FuturesPaperStatusResponse)
def start_futures_paper(
    service: Annotated[FuturesPaperService, Depends(get_futures_paper_service)],
) -> FuturesPaperStatusResponse:
    """Start paper-only Futures runtime."""

    service.start()
    return _to_futures_status_response(service)


@router.post("/bot/futures/stop", response_model=FuturesPaperStatusResponse)
def stop_futures_paper(
    service: Annotated[FuturesPaperService, Depends(get_futures_paper_service)],
) -> FuturesPaperStatusResponse:
    """Stop paper-only Futures runtime."""

    service.stop()
    return _to_futures_status_response(service)


@router.get("/bot/futures/signal", response_model=FuturesPaperExecutionSignalResponse)
def get_futures_paper_signal(
    symbol: Annotated[str, Query(min_length=1)],
    service: Annotated[FuturesPaperService, Depends(get_futures_paper_service)],
) -> FuturesPaperExecutionSignalResponse:
    """Return a deterministic paper Futures LONG/SHORT signal."""

    normalized_symbol = symbol.strip().upper()
    position = service.broker.get_position(normalized_symbol)
    signal_input = FuturesSignalInput(
        symbol=normalized_symbol,
        technical_bias="neutral",
        regime="unknown",
        market_sentiment="unknown",
        symbol_sentiment="unknown",
        pattern_bias="unknown",
        current_position_side=position.side if position is not None else None,
    )
    return _to_futures_signal_engine_response(service.signal(signal_input))


@router.post("/bot/futures/manual-long", response_model=FuturesPaperFillResponse)
def manual_futures_long(
    payload: FuturesPaperOrderRequest,
    service: Annotated[FuturesPaperService, Depends(get_futures_paper_service)],
) -> FuturesPaperFillResponse:
    """Open a manual paper Futures LONG."""

    result = service.manual_open(
        symbol=payload.symbol,
        side="LONG",
        quantity=payload.quantity,
        market_price=payload.market_price,
        leverage=payload.leverage,
    )
    return _to_futures_fill_response(result)


@router.post("/bot/futures/manual-short", response_model=FuturesPaperFillResponse)
def manual_futures_short(
    payload: FuturesPaperOrderRequest,
    service: Annotated[FuturesPaperService, Depends(get_futures_paper_service)],
) -> FuturesPaperFillResponse:
    """Open a manual paper Futures SHORT."""

    result = service.manual_open(
        symbol=payload.symbol,
        side="SHORT",
        quantity=payload.quantity,
        market_price=payload.market_price,
        leverage=payload.leverage,
    )
    return _to_futures_fill_response(result)


@router.post("/bot/futures/manual-close", response_model=FuturesPaperFillResponse)
def manual_futures_close(
    payload: FuturesPaperCloseRequest,
    service: Annotated[FuturesPaperService, Depends(get_futures_paper_service)],
) -> FuturesPaperFillResponse:
    """Close the current manual paper Futures position."""

    return _to_futures_fill_response(
        service.manual_close(symbol=payload.symbol, market_price=payload.market_price)
    )


@router.get("/performance/futures-paper", response_model=FuturesPaperPerformanceResponse)
def get_futures_paper_performance(
    service: Annotated[FuturesPaperService, Depends(get_futures_paper_service)],
    symbol: str | None = Query(default=None, min_length=1),
) -> FuturesPaperPerformanceResponse:
    """Return paper-only Futures performance."""

    report = service.performance(symbol=symbol)
    return FuturesPaperPerformanceResponse(
        symbol=report["symbol"],  # type: ignore[arg-type]
        paper_only=True,
        total_fills=int(report["total_fills"]),
        realized_pnl=report["realized_pnl"],  # type: ignore[arg-type]
        positions=[
            _to_futures_position_response(position)
            for position in report["positions"]  # type: ignore[union-attr]
        ],
        recent_fills=[
            FuturesPaperFillResponse(
                order_id=fill.order_id,
                status=fill.status,
                symbol=fill.symbol,
                side=fill.side,
                filled_quantity=fill.filled_quantity,
                fill_price=fill.fill_price,
                fee_paid=fill.fee_paid,
                realized_pnl=fill.realized_pnl,
                reason_codes=fill.reason_codes,
                paper_only=True,
            )
            for fill in report["recent_fills"]  # type: ignore[union-attr]
        ],
    )


@router.get("/bot/backfill-status", response_model=BackfillStatusResponse)
def get_backfill_status(
    symbol: Annotated[str, Query(min_length=1)],
    backfill_service: Annotated[HistoricalBackfillService, Depends(get_backfill_service)],
    settings: Annotated[Settings, Depends(get_settings_dependency)],
    interval: ChartTimeframe = "1m",
    lookback_days: Annotated[int, Query(ge=1, le=30)] = 7,
    market: SelectedMarket = "spot",
) -> BackfillStatusResponse:
    """Return stored historical-candle coverage for one selected symbol."""

    normalized_symbol = symbol.strip().upper()
    if market == "futures":
        repository = StorageRepository(settings.database_url)
        try:
            return _to_backfill_status_response(
                _futures_backfill_status(
                    repository=repository,
                    symbol=normalized_symbol,
                    interval=interval,
                    lookback_days=lookback_days,
                )
            )
        finally:
            repository.close()
    return _to_backfill_status_response(
        backfill_service.status(
            symbol=normalized_symbol,
            interval=interval,
            lookback_days=lookback_days,
        )
    )


@router.post("/bot/backfill", response_model=BackfillStatusResponse)
async def trigger_backfill(
    symbol: Annotated[str, Query(min_length=1)],
    backfill_service: Annotated[HistoricalBackfillService, Depends(get_backfill_service)],
    settings: Annotated[Settings, Depends(get_settings_dependency)],
    rest_client: Annotated[BinanceRestClient, Depends(get_rest_client)],
    interval: ChartTimeframe = "1m",
    lookback_days: Annotated[int, Query(ge=1, le=30)] = 7,
    market: SelectedMarket = "spot",
) -> BackfillStatusResponse:
    """Trigger or refresh historical-candle backfill for one selected symbol."""

    normalized_symbol = symbol.strip().upper()
    if market == "futures":
        repository = StorageRepository(settings.database_url)
        try:
            try:
                await _load_or_fetch_futures_scan_candles(
                    repository=repository,
                    rest_client=rest_client,
                    symbol=normalized_symbol,
                    interval=interval,
                    lookback_days=lookback_days,
                )
            except Exception as exc:
                LOGGER.exception("USD-M Futures selected-symbol backfill failed for %s %s.", normalized_symbol, interval)
                return _to_backfill_status_response(
                    _futures_backfill_status(
                        repository=repository,
                        symbol=normalized_symbol,
                        interval=interval,
                        lookback_days=lookback_days,
                        failed_message=f"Symbol not available on selected market. {type(exc).__name__}: {exc}",
                    )
                )
            return _to_backfill_status_response(
                _futures_backfill_status(
                    repository=repository,
                    symbol=normalized_symbol,
                    interval=interval,
                    lookback_days=lookback_days,
                )
            )
        finally:
            repository.close()
    return _to_backfill_status_response(
        await backfill_service.ensure_recent_history(
            symbol=normalized_symbol,
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
    market: SelectedMarket = "spot",
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)] = None,
    settings: Annotated[Settings, Depends(get_settings_dependency)] = None,
) -> CandleHistoryResponse:
    """Return recent closed candles for the selected symbol chart."""

    normalized_symbol = symbol.strip().upper()
    status = runtime.status()
    runtime_active = _runtime_matches_symbol(status, normalized_symbol)
    repository = StorageRepository(settings.database_url)
    try:
        if market == "futures":
            merged = _load_futures_candle_series(
                repository=repository,
                symbol=normalized_symbol,
                interval=timeframe,
                limit=limit,
            )
        else:
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
            runtime_active=runtime_active or market == "futures",
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
        derivatives_data, crowd_positioning = await _load_crowd_positioning(
            settings=settings,
            symbol=normalized_symbol,
        )
        _apply_crowd_positioning_to_context(
            context=context,
            crowd=crowd_positioning,
            derivatives=derivatives_data,
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
            liquidity_bias=context.liquidity_bias,
            crowd_positioning=context.crowd_positioning,
            derivatives_data=context.derivatives_data,
            candles=context.candles,
            regime_label=regime_analysis.regime_label if regime_analysis is not None else None,
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
        _persist_assistant_outcome_snapshot(
            repository=repository,
            symbol=normalized_symbol,
            assistant=assistant,
            current_price=workstation.last_price,
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
        derivatives_data, crowd_positioning = await _load_crowd_positioning(
            settings=settings,
            symbol=normalized_symbol,
        )
        _apply_crowd_positioning_to_context(
            context=context,
            crowd=crowd_positioning,
            derivatives=derivatives_data,
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
            liquidity_bias=context.liquidity_bias,
            crowd_positioning=context.crowd_positioning,
            derivatives_data=context.derivatives_data,
            candles=context.candles,
            regime_label=regime_analysis.regime_label if regime_analysis is not None else None,
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
        liquidity_zones = _estimate_assistant_liquidity_zones(
            symbol=normalized_symbol,
            candles=context.candles,
            workstation=workstation,
            assistant=assistant,
            fusion_signal=fusion_response,
            liquidity_bias=context.liquidity_bias,
            regime_analysis=regime_analysis,
            crowd_positioning=context.crowd_positioning,
        )
        liquidation_intelligence = _load_liquidation_intelligence(
            symbol=normalized_symbol,
            candles=context.candles,
            liquidity_zones=liquidity_zones,
            crowd_positioning=context.crowd_positioning,
        )
        liquidity_zones = validate_liquidity_zones_with_liquidations(
            zones=liquidity_zones,
            liquidation_signal=liquidation_intelligence.liquidation_signal,
            dominant_side=liquidation_intelligence.dominant_side,
        )
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
                liquidity_bias=context.liquidity_bias,
                liquidity_zones=liquidity_zones,
                crowd_positioning=context.crowd_positioning,
                funding_rate=context.derivatives_data.funding_rate if context.derivatives_data is not None else None,
                open_interest=context.derivatives_data.open_interest if context.derivatives_data is not None else None,
                oi_trend=context.derivatives_data.oi_trend if context.derivatives_data is not None else "neutral",
                liquidation_intelligence=liquidation_intelligence,
            )
        )
        response = _to_trade_eligibility_response(symbol=normalized_symbol, result=result)
        _persist_eligibility_outcome_snapshot(
            repository=repository,
            symbol=normalized_symbol,
            assistant=assistant,
            eligibility=response,
            current_price=workstation.last_price,
        )
        return response
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


@router.post("/bot/spot-opportunities/scan", response_model=SpotOpportunityScanJobResponse)
async def start_spot_opportunity_scan(
    payload: SpotOpportunityScanStartRequest,
    settings: Annotated[Settings, Depends(get_settings_dependency)] = None,
    rest_client: Annotated[BinanceRestClient, Depends(get_rest_client)] = None,
) -> SpotOpportunityScanJobResponse:
    """Start a background paper-only Spot opportunity scan."""

    try:
        _normalize_futures_scanner_horizon(payload.horizon)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job = _SPOT_SCANNER_JOB_MANAGER.create(payload)
    worker_rest_client = None if isinstance(rest_client, BinanceRestClient) else rest_client
    thread = Thread(
        target=lambda: asyncio.run(
            _run_spot_opportunity_scan_job(
                scan_id=job.scan_id,
                settings=settings,
                rest_client=worker_rest_client,
            )
        ),
        name=f"spot-opportunity-scan-{job.scan_id}",
        daemon=True,
    )
    _SPOT_SCANNER_JOB_MANAGER.set_thread(job.scan_id, thread)
    thread.start()
    return _to_spot_scan_job_response(job)


@router.get("/bot/spot-opportunities/scan/{scan_id}", response_model=SpotOpportunityScanJobResponse)
async def get_spot_opportunity_scan_job(scan_id: str) -> SpotOpportunityScanJobResponse:
    """Return the latest progress snapshot for a background Spot opportunity scan."""

    job = _SPOT_SCANNER_JOB_MANAGER.get(scan_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Spot scanner job not found.")
    return _to_spot_scan_job_response(job)


@router.post("/bot/spot-opportunities/scan/{scan_id}/cancel", response_model=SpotOpportunityScanJobResponse)
async def cancel_spot_opportunity_scan_job(scan_id: str) -> SpotOpportunityScanJobResponse:
    """Cancel a running background Spot opportunity scan."""

    job = _SPOT_SCANNER_JOB_MANAGER.cancel(scan_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Spot scanner job not found.")
    return _to_spot_scan_job_response(job)


@router.post("/bot/futures-opportunities/scan", response_model=FuturesOpportunityScanJobResponse)
async def start_futures_opportunity_scan(
    payload: FuturesOpportunityScanStartRequest,
    settings: Annotated[Settings, Depends(get_settings_dependency)] = None,
    rest_client: Annotated[BinanceRestClient, Depends(get_rest_client)] = None,
) -> FuturesOpportunityScanJobResponse:
    """Start a background paper-only futures opportunity scan."""

    try:
        _normalize_futures_scanner_horizon(payload.horizon)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job = _FUTURES_SCANNER_JOB_MANAGER.create(payload)
    worker_rest_client = None if isinstance(rest_client, BinanceRestClient) else rest_client
    thread = Thread(
        target=lambda: asyncio.run(
            _run_futures_opportunity_scan_job(
                scan_id=job.scan_id,
                settings=settings,
                rest_client=worker_rest_client,
            )
        ),
        name=f"futures-opportunity-scan-{job.scan_id}",
        daemon=True,
    )
    _FUTURES_SCANNER_JOB_MANAGER.set_thread(job.scan_id, thread)
    thread.start()
    return _to_futures_scan_job_response(job)


@router.get("/bot/futures-opportunities/scan/{scan_id}", response_model=FuturesOpportunityScanJobResponse)
async def get_futures_opportunity_scan_job(scan_id: str) -> FuturesOpportunityScanJobResponse:
    """Return the latest progress snapshot for a background futures opportunity scan."""

    job = _FUTURES_SCANNER_JOB_MANAGER.get(scan_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Scanner job not found.")
    return _to_futures_scan_job_response(job)


@router.post("/bot/futures-opportunities/scan/{scan_id}/cancel", response_model=FuturesOpportunityScanJobResponse)
async def cancel_futures_opportunity_scan_job(scan_id: str) -> FuturesOpportunityScanJobResponse:
    """Cancel a running background futures opportunity scan."""

    job = _FUTURES_SCANNER_JOB_MANAGER.cancel(scan_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Scanner job not found.")
    return _to_futures_scan_job_response(job)


@router.get("/bot/futures-opportunities", response_model=FuturesOpportunityScanResponse)
async def get_futures_opportunities(
    quote_asset: str = "USDT",
    limit: Annotated[int | None, Query(ge=1)] = None,
    max_symbols: Annotated[int | None, Query(ge=1)] = None,
    concurrency: Annotated[int, Query(ge=1, le=10)] = 5,
    symbol_timeout_seconds: Annotated[float, Query(ge=1, le=8)] = 7.0,
    scan_timeout_seconds: Annotated[float, Query(ge=5, le=90)] = 45.0,
    horizon: str = Query(default="7d"),
    min_opportunity_score: Annotated[int, Query(ge=0, le=100)] = 0,
    min_confidence: Annotated[int, Query(ge=0, le=100)] = 0,
    include_weak_evidence: bool = True,
    include_avoid: bool = True,
    market_sensitivity: Literal["conservative", "balanced", "aggressive"] = "balanced",
    settings: Annotated[Settings, Depends(get_settings_dependency)] = None,
    rest_client: Annotated[BinanceRestClient, Depends(get_rest_client)] = None,
) -> FuturesOpportunityScanResponse:
    """Scan symbols for paper-only futures long/short opportunities."""

    scan_id = uuid4().hex
    normalized_quote = quote_asset.strip().upper() or "USDT"
    scan_limit = min(max_symbols if max_symbols is not None else limit if limit is not None else 50, 100)
    try:
        normalized_horizon = _normalize_futures_scanner_horizon(horizon)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    scanner = FuturesOpportunityScanner()
    total_started_at = time.perf_counter()
    repository = StorageRepository(settings.database_url)
    signals: list[FuturesPaperSignal] = []
    failed_symbols: list[str] = []
    candle_cache: dict[tuple[str, SupportedInterval], list[Candle]] = {}
    semaphore = asyncio.Semaphore(concurrency)
    threshold_floor = 60 if market_sensitivity == "aggressive" else 0
    sensitivity_discount = 8 if market_sensitivity == "aggressive" else 0
    current_threshold = max(threshold_floor, max(min_opportunity_score, min_confidence) - sensitivity_discount)
    fallback_symbol_count = len(_manual_futures_symbol_fallback(normalized_quote))

    universe_started_at = time.perf_counter()
    universe = await _load_futures_symbol_universe(
        rest_client=rest_client,
        quote_asset=normalized_quote,
        limit=scan_limit,
    )
    LOGGER.info(
        "Futures scanner universe load %.3fs source=%s symbols=%d scan_id=%s.",
        time.perf_counter() - universe_started_at,
        universe.source,
        len(universe.records),
        scan_id,
    )
    candidates = universe.records
    if universe.source == "unavailable" or not candidates:
        latest_error = universe.latest_error or "No USD-M Futures symbol universe is available."
        LOGGER.warning(
            "Futures scanner degraded; scan_id=%s phase=symbol_universe endpoint=/fapi/v1/exchangeInfo exception_type=Unavailable error=%s",
            scan_id,
            latest_error,
        )
        cached_response = _latest_successful_scanner_response(
            repository=repository,
            quote_asset=normalized_quote,
            horizon=normalized_horizon,
            latest_error=latest_error,
            universe_source=universe.source,
            fallback_symbol_count=fallback_symbol_count,
        )
        if cached_response is not None:
            repository.close()
            return cached_response
        repository.close()
        return _empty_degraded_scanner_response(
            universe_source=universe.source,
            latest_error=latest_error,
            fallback_symbol_count=fallback_symbol_count,
        )

    universe_warnings: list[str] = []
    if universe.source == "cache":
        universe_warnings.append(
            "Using cached USD-M Futures symbol universe because live Binance exchangeInfo is unavailable or recently cached."
        )
    elif universe.source == "fallback":
        universe_warnings.append("Live USD-M symbol universe unavailable; using curated fallback list.")

    async def scan_symbol(record: SpotSymbolRecord) -> FuturesPaperSignal | None:
        async with semaphore:
            symbol_started_at = time.perf_counter()
            try:
                signal = await asyncio.wait_for(
                    _build_market_wide_futures_signal_for_symbol(
                        scanner=scanner,
                        symbol=record.symbol,
                        horizon=normalized_horizon,
                        repository=repository,
                        rest_client=rest_client,
                        settings=settings,
                        candle_cache=candle_cache,
                        market_sensitivity=market_sensitivity,
                    ),
                    timeout=symbol_timeout_seconds,
                )
            except asyncio.TimeoutError:
                LOGGER.warning(
                    "Timed out futures-paper scan; scan_id=%s phase=symbol_scan symbol=%s endpoint=/fapi/v1/klines exception_type=TimeoutError timeout_seconds=%.1f",
                    scan_id,
                    record.symbol,
                    symbol_timeout_seconds,
                )
                failed_symbols.append(record.symbol)
                return None
            except Exception:
                LOGGER.exception(
                    "Failed to scan paper futures opportunity; scan_id=%s phase=symbol_scan symbol=%s endpoint=/fapi/v1/klines",
                    scan_id,
                    record.symbol,
                )
                failed_symbols.append(record.symbol)
                return None
            finally:
                LOGGER.debug(
                    "Futures scanner symbol %s finished in %.3fs.",
                    record.symbol,
                    time.perf_counter() - symbol_started_at,
                )

            weak_validation = signal.evidence_strength in {"insufficient", "unvalidated", "weak"}
            if signal.direction in {"long", "short"}:
                if signal.opportunity_score < current_threshold:
                    return None
                if weak_validation and not include_weak_evidence:
                    return None
                return signal
            if signal.direction == "wait" or include_avoid:
                return signal
            return None

    try:
        scan_started_at = time.perf_counter()
        if candidates:
            task_by_symbol = {
                asyncio.create_task(scan_symbol(record), name=f"futures-scan-{record.symbol}"): record.symbol
                for record in candidates
            }
            done, pending = await asyncio.wait(task_by_symbol.keys(), timeout=scan_timeout_seconds)
            for task in pending:
                symbol = task_by_symbol[task]
                task.cancel()
                failed_symbols.append(symbol)
                LOGGER.warning(
                    "Futures scanner request timed out; scan_id=%s phase=scan_timeout symbol=%s endpoint=/bot/futures-opportunities exception_type=TimeoutError timeout_seconds=%.1f",
                    scan_id,
                    symbol,
                    scan_timeout_seconds,
                )
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                result = task.result()
                if result is not None:
                    signals.append(result)
        LOGGER.info(
            "Futures scanner analyzed %d/%d symbols in %.3fs with concurrency=%d scan_id=%s.",
            len(signals),
            len(candidates),
            time.perf_counter() - scan_started_at,
            concurrency,
            scan_id,
        )
        ranking_started_at = time.perf_counter()
        report = scanner.build_report(
            signals=signals,
            failed_symbols=failed_symbols,
            include_avoid=include_avoid,
        )
        LOGGER.info(
            "Futures scanner ranking completed in %.3fs scan_id=%s candidates=%d.",
            time.perf_counter() - ranking_started_at,
            scan_id,
            len(signals),
        )
        report.warnings.extend(universe_warnings)
        report.futures_symbol_universe_source = universe.source
        report.symbol_count = len(candidates)
        report.last_successful_fetch_at = universe.last_successful_fetch_at
        report.latest_error = universe.latest_error
        if universe.source in {"cache", "fallback"} and report.scan_state == "ready":
            report.scan_state = "partial"
        if pending:
            report.scan_state = "partial" if signals else "degraded"
            report.warnings.append("Scanner request timed out before all symbols completed; partial results are shown.")
        if not signals and failed_symbols:
            latest_error = universe.latest_error or "futures_klines_unavailable: no requested futures symbols returned candles."
            cached_response = _latest_successful_scanner_response(
                repository=repository,
                quote_asset=normalized_quote,
                horizon=normalized_horizon,
                latest_error=latest_error,
                universe_source=universe.source,
                fallback_symbol_count=fallback_symbol_count,
            )
            if cached_response is not None:
                return cached_response
            return _empty_degraded_scanner_response(
                universe_source=universe.source,
                latest_error=latest_error,
                fallback_symbol_count=fallback_symbol_count,
                failed_symbols=failed_symbols,
            )
        response = _to_futures_scan_response(report)
        try:
            _persist_scanner_run_candidates(
                repository=repository,
                scan_id=scan_id,
                report=report,
                response=response,
                quote_asset=normalized_quote,
                horizon=normalized_horizon,
                max_symbols=scan_limit,
                min_opportunity_score=min_opportunity_score,
            )
        except Exception:
            LOGGER.exception("Failed to persist futures scanner run candidates.")
            response.warnings.append("Scanner candidate persistence failed; visible results are still usable for this session.")
        try:
            persist_scanner_validation_snapshots(repository=repository, report=report)
        except Exception:
            LOGGER.exception("Failed to persist futures scanner validation snapshots.")
            response.warnings.append(
                "Scanner validation snapshot persistence failed; this scan will not be included in paper validation reports."
            )
        _persist_scanner_outcome_snapshots(repository=repository, report=report)
        LOGGER.info("Futures scanner total scan time %.3fs scan_id=%s.", time.perf_counter() - total_started_at, scan_id)
        return response
    finally:
        repository.close()


@router.get("/bot/futures-opportunities/live-prices", response_model=FuturesLivePriceResponse)
async def get_futures_opportunity_live_prices(
    symbols: Annotated[str, Query(min_length=1)],
    rest_client: Annotated[BinanceRestClient, Depends(get_rest_client)] = None,
    heartbeat_service: Annotated[
        FuturesScannerWebSocketHeartbeatService | None,
        Depends(get_futures_scanner_heartbeat_service),
    ] = None,
) -> FuturesLivePriceResponse:
    """Return lightweight live prices for visible futures-paper scanner cards."""

    requested = list(sanitize_scanner_symbols(symbols.split(","), max_symbols=100))
    if not requested:
        raise HTTPException(status_code=400, detail="symbols must include at least one symbol")

    updated_at = datetime.now(tz=UTC)
    cached = heartbeat_service.latest_prices(requested, now=updated_at) if heartbeat_service is not None else {}
    fresh_websocket = {
        symbol: item
        for symbol, item in cached.items()
        if item.source == "websocket" and not item.stale and item.live_price is not None
    }
    rest_symbols = [symbol for symbol in requested if symbol not in fresh_websocket]
    rest_prices: dict[str, tuple[Decimal, Literal["mark_price", "futures_last_price"]]] = {}
    warnings: list[str] = []
    try:
        rows = await rest_client.get_futures_mark_prices(rest_symbols) if rest_symbols else []
    except Exception:
        LOGGER.exception("Failed to fetch USD-M Futures mark prices for scanner heartbeat.")
        try:
            rows = await rest_client.get_futures_ticker_prices(rest_symbols) if rest_symbols else []
        except Exception:
            LOGGER.exception("Failed to fetch USD-M Futures last prices for scanner heartbeat.")
            rows = []
            warnings.append("Futures REST price fallback is temporarily unavailable; stale WebSocket cache may be shown.")
        else:
            rest_prices = _futures_price_map(rows, price_key="price", price_type="futures_last_price")
    else:
        rest_prices = _futures_price_map(rows, price_key="markPrice", price_type="mark_price")
        missing_symbols = [symbol for symbol in rest_symbols if symbol not in rest_prices]
        if missing_symbols:
            try:
                ticker_rows = await rest_client.get_futures_ticker_prices(missing_symbols)
            except Exception:
                LOGGER.exception("Failed to fetch missing USD-M Futures last prices for scanner heartbeat.")
            else:
                rest_prices.update(
                    _futures_price_map(ticker_rows, price_key="price", price_type="futures_last_price")
                )

    return FuturesLivePriceResponse(
        items=[
            _to_futures_live_price_response(
                symbol=symbol,
                cached=cached.get(symbol),
                rest_price=rest_prices.get(symbol),
                fallback_updated_at=updated_at,
            )
            for symbol in requested
        ],
        warnings=warnings,
    )


def _futures_price_map(
    rows: list[dict],
    *,
    price_key: str,
    price_type: Literal["mark_price", "futures_last_price"],
) -> dict[str, tuple[Decimal, Literal["mark_price", "futures_last_price"]]]:
    price_by_symbol: dict[str, tuple[Decimal, Literal["mark_price", "futures_last_price"]]] = {}
    for row in rows:
        symbol = str(row.get("symbol", "")).upper()
        raw_price = row.get(price_key)
        if symbol and raw_price is not None:
            try:
                price_by_symbol[symbol] = (Decimal(str(raw_price)), price_type)
            except Exception:
                LOGGER.warning("Ignoring invalid USD-M Futures price for %s: %s", symbol, raw_price)
    return price_by_symbol


def _to_futures_live_price_response(
    *,
    symbol: str,
    cached: FuturesScannerLivePrice | None,
    rest_price: tuple[Decimal, Literal["mark_price", "futures_last_price"]] | None,
    fallback_updated_at: datetime,
) -> FuturesLivePriceItemResponse:
    if cached is not None and cached.source == "websocket" and not cached.stale and cached.live_price is not None:
        return FuturesLivePriceItemResponse(
            symbol=symbol,
            live_price=cached.live_price,
            updated_at=cached.updated_at,
            source="websocket",
            data_source=cached.data_source,
            price_type=cached.price_type,
            stale=False,
            warning=None,
        )
    if rest_price is not None:
        price, price_type = rest_price
        return FuturesLivePriceItemResponse(
            symbol=symbol,
            live_price=price,
            updated_at=fallback_updated_at,
            source="rest",
            data_source="binance_usdm_futures",
            price_type=price_type,
            stale=False,
            warning=None,
        )
    if cached is not None and cached.live_price is not None:
        return FuturesLivePriceItemResponse(
            symbol=symbol,
            live_price=cached.live_price,
            updated_at=cached.updated_at,
            source="cache",
            data_source=cached.data_source,
            price_type=cached.price_type,
            stale=True,
            warning=cached.warning or "Cached WebSocket price is stale and REST fallback did not return a price.",
        )
    return FuturesLivePriceItemResponse(
        symbol=symbol,
        live_price=None,
        updated_at=cached.updated_at if cached is not None else fallback_updated_at,
        source="unavailable",
        data_source="binance_usdm_futures",
        price_type=cached.price_type if cached is not None else "mark_price",
        stale=True,
        warning=(
            cached.warning if cached is not None and cached.warning else "Live price heartbeat is temporarily unavailable."
        ),
    )


@router.post("/bot/futures-opportunities/live-subscriptions", response_model=FuturesLiveSubscriptionResponse)
async def update_futures_opportunity_live_subscriptions(
    payload: FuturesLiveSubscriptionRequest,
    heartbeat_service: Annotated[
        FuturesScannerWebSocketHeartbeatService | None,
        Depends(get_futures_scanner_heartbeat_service),
    ] = None,
) -> FuturesLiveSubscriptionResponse:
    """Subscribe the scanner heartbeat to currently visible paper scanner symbols."""

    if heartbeat_service is None:
        sanitized = list(sanitize_scanner_symbols(payload.symbols, max_symbols=100))
        return FuturesLiveSubscriptionResponse(
            symbols=sanitized,
            count=len(sanitized),
            websocket_enabled=False,
            warning="WebSocket heartbeat service is unavailable; REST live price fallback remains active.",
        )
    try:
        subscribed = await heartbeat_service.update_subscriptions(payload.symbols)
    except Exception:
        LOGGER.exception("Failed to update futures scanner websocket subscriptions.")
        return FuturesLiveSubscriptionResponse(
            symbols=[],
            count=0,
            websocket_enabled=False,
            warning="WebSocket heartbeat subscription update failed; REST live price fallback remains active.",
        )
    return FuturesLiveSubscriptionResponse(
        symbols=list(subscribed),
        count=len(subscribed),
        websocket_enabled=True,
        warning=None,
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


def _to_signal_timing_aggregate_response(
    aggregate: SignalTimingAggregate,
) -> SignalTimingAggregateResponse:
    return SignalTimingAggregateResponse(**asdict(aggregate))


@router.get("/bot/signal-timing-baseline", response_model=SignalTimingBaselineResponse)
def get_signal_timing_baseline(
    settings: Annotated[Settings, Depends(get_settings_dependency)],
    symbol: Annotated[str | None, Query(min_length=1)] = None,
    source: Annotated[str | None, Query(min_length=1)] = None,
    horizon: Annotated[str | None, Query()] = None,
    recent_limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> SignalTimingBaselineResponse:
    """Return the measured Phase 1 baseline for actionable signal timing quality."""

    if horizon is not None and horizon not in TIMING_HORIZONS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported timing horizon. Use one of: {', '.join(TIMING_HORIZONS)}.",
        )
    normalized_symbol = symbol.strip().upper() if symbol else None
    normalized_source = source.strip() if source else None
    try:
        repository = StorageRepository(settings.database_url)
    except Exception:
        LOGGER.exception("Failed to open Phase 1 signal timing baseline storage.")
        return SignalTimingBaselineResponse(
            generated_at=datetime.now(tz=UTC),
            data_state="degraded_storage",
            status_message="Signal timing baseline storage is unavailable.",
            actionable_snapshot_count=0,
            evaluated_count=0,
            pending_count=0,
            insufficient_data_count=0,
            classification_counts={},
            overall=SignalTimingAggregateResponse(
                label="overall",
                sample_size=0,
                late_rate_pct=Decimal("0"),
                chase_rate_pct=Decimal("0"),
                useful_rate_pct=Decimal("0"),
            ),
            by_horizon=[],
            by_source=[],
            recent_samples=[],
            definitions={},
        )
    try:
        evaluate_pending_signal_timing_baselines(
            repository=repository,
            retry_insufficient=True,
        )
        report = build_signal_timing_baseline_report(
            repository=repository,
            symbol=normalized_symbol,
            source=normalized_source,
            horizon=horizon,
            recent_limit=recent_limit,
        )
        storage_degraded = repository.optional_storage_degraded
        storage_message = repository.optional_storage_message
    except Exception:
        LOGGER.exception("Failed to build Phase 1 signal timing baseline report.")
        repository.close()
        raise HTTPException(status_code=503, detail="Signal timing baseline evaluation failed.") from None
    repository.close()
    if storage_degraded:
        data_state = "degraded_storage"
        status_message = storage_message or "Signal timing baseline persistence is degraded."
    elif report.evaluated_count:
        data_state = "ready"
        status_message = "Current actionable signals have measured timing-quality evidence."
    else:
        data_state = "insufficient_data"
        status_message = (
            "Actionable snapshots need both pre-signal and matured post-signal candle history "
            "before timing quality can be measured."
        )
    return SignalTimingBaselineResponse(
        generated_at=report.generated_at,
        data_state=data_state,
        status_message=status_message,
        actionable_snapshot_count=report.actionable_snapshot_count,
        evaluated_count=report.evaluated_count,
        pending_count=report.pending_count,
        insufficient_data_count=report.insufficient_data_count,
        classification_counts=report.classification_counts,
        overall=_to_signal_timing_aggregate_response(report.overall),
        by_horizon=[_to_signal_timing_aggregate_response(item) for item in report.by_horizon],
        by_source=[_to_signal_timing_aggregate_response(item) for item in report.by_source],
        recent_samples=[SignalTimingSampleResponse(**asdict(item)) for item in report.recent_samples],
        definitions=report.definitions,
    )
