"""FastAPI endpoints for paper-bot symbol discovery and runtime control."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.ai import AIOutcomeEvaluator
from app.bot import BotStatus, PaperBotRuntime, WorkstationState
from app.config import Settings, get_settings
from app.exchange.symbol_service import SpotSymbolRecord, SpotSymbolService
from app.storage import StorageRepository

router = APIRouter()
LOGGER = logging.getLogger(__name__)

DataState = Literal["ready", "waiting_for_runtime", "waiting_for_history", "degraded_storage"]


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
    symbol: str | None = None
    timeframe: str
    paper_only: bool
    started_at: datetime | None = None
    last_event_time: datetime | None = None
    last_error: str | None = None


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


class AISignalResponse(BaseModel):
    """Serialized AI advisory market read."""

    symbol: str
    timestamp: datetime
    bias: str
    confidence: int
    entry_signal: bool
    exit_signal: bool
    suggested_action: str
    explanation: str
    features: AIFeatureResponse


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
    last_price: Decimal | None = None
    current_candle: CandleSummaryResponse | None = None
    top_of_book: TopOfBookResponse | None = None
    feature: FeatureSummaryResponse | None = None
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


def get_symbol_service(request: Request) -> SpotSymbolService:
    """Return the shared symbol service instance from FastAPI app state."""

    return request.app.state.symbol_service


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


def _to_status_response(status: BotStatus) -> BotStatusResponse:
    """Convert runtime status to an API response."""

    return BotStatusResponse(
        state=status.state,
        symbol=status.symbol,
        timeframe=status.timeframe,
        paper_only=status.paper_only,
        started_at=status.started_at,
        last_event_time=status.last_event_time,
        last_error=status.last_error,
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
        explanation=explanation,
        features=AIFeatureResponse(
            candle_count=candle_count,
            close_price=close_price,
            volatility_pct=volatility_pct,
            momentum=momentum,
            volume_change_pct=volume_change_pct,
            volume_spike_ratio=volume_spike_ratio,
            spread_ratio=spread_ratio,
            microstructure_healthy=microstructure_healthy,
        ),
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
            )
            for item in recent_samples
        ],
    )


def _to_workstation_response(
    *,
    state: WorkstationState,
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
        runtime_status=_to_status_response(status),
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

    return _to_status_response(runtime.status())


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
    return _to_status_response(status)


@router.post("/bot/stop", response_model=BotStatusResponse)
async def stop_bot(
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
) -> BotStatusResponse:
    """Stop the live paper bot."""

    return _to_status_response(await runtime.stop())


@router.post("/bot/pause", response_model=BotStatusResponse)
async def pause_bot(
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
) -> BotStatusResponse:
    """Pause the live paper bot while keeping market-data ingestion alive."""

    try:
        status = await runtime.pause()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_status_response(status)


@router.post("/bot/resume", response_model=BotStatusResponse)
async def resume_bot(
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
) -> BotStatusResponse:
    """Resume the live paper bot after a pause."""

    try:
        status = await runtime.resume()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_status_response(status)


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
    return _to_status_response(status)


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
        status=status,
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
