"""FastAPI monitoring and analytics endpoints for paper mode."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from app.api.dependencies import DashboardDataAccess, get_dashboard_data_access
from app.config import Settings, get_settings
from app.monitoring.metrics import build_performance_analytics
from app.monitoring.outcome_review import (
    BlockerFrequency,
    ExecutionSourceComparison,
    PaperTradeReview,
    ProfileComparison,
    SessionAnalytics,
    TuningSuggestion,
    build_paper_trade_review,
)
from app.monitoring.profile_calibration import (
    PROFILE_THRESHOLDS,
    ProfileCalibrationComparison,
    ProfileCalibrationComparisonMetrics,
    ProfileCalibrationRecommendation,
    ProfileCalibrationReport,
    ProfileTuningPreview,
    ThresholdChange,
    build_profile_calibration_comparison,
    build_profile_calibration_report,
    with_tuning_previews,
)
from app.monitoring.trade_quality import (
    HoldTimeDistributionSummary,
    TradeQualityAnalytics,
    TradeQualityDetail,
    build_trade_quality_analytics,
)
from app.monitoring.health import HealthStatus
from app.storage.models import (
    DailyPnlRecord,
    DrawdownPoint,
    DrawdownSummary,
    EquityHistoryPoint,
    FillRecord,
    PnlHistoryPoint,
    PnlSnapshotRecord,
    PositionSnapshotRecord,
    RunnerEventRecord,
    TradeRecord,
)

router = APIRouter()


class HealthResponse(BaseModel):
    """Health payload for the monitoring API."""

    name: str
    status: str
    mode: str
    storage: str


class TradeResponse(BaseModel):
    """Serialized trade history row."""

    order_id: str
    symbol: str
    side: str
    requested_quantity: Decimal
    approved_quantity: Decimal
    filled_quantity: Decimal
    status: str
    risk_decision: str
    reason_codes: tuple[str, ...]
    fill_price: Decimal
    realized_pnl: Decimal
    quote_balance: Decimal
    event_time: datetime


class FillResponse(BaseModel):
    """Serialized fill history row."""

    order_id: str
    symbol: str
    side: str
    filled_quantity: Decimal
    fill_price: Decimal
    fee_paid: Decimal
    realized_pnl: Decimal
    quote_balance: Decimal
    event_time: datetime


class PositionResponse(BaseModel):
    """Serialized current position snapshot."""

    symbol: str
    quantity: Decimal
    avg_entry_price: Decimal
    realized_pnl: Decimal
    quote_asset: str
    snapshot_time: datetime


class EquityResponse(BaseModel):
    """Latest equity snapshot payload."""

    snapshot_time: datetime | None = None
    equity: Decimal = Decimal("0")
    total_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    cash_balance: Decimal = Decimal("0")


class EventResponse(BaseModel):
    """Serialized runner event row."""

    event_type: str
    symbol: str
    message: str
    payload: dict[str, Any]
    event_time: datetime


class MetricsResponse(BaseModel):
    """Aggregate paper-trading metrics."""

    total_trades: int
    win_rate: Decimal
    realized_pnl: Decimal
    average_pnl_per_trade: Decimal
    current_equity: Decimal
    max_winning_streak: int
    max_losing_streak: int


class RangeQueryParams(BaseModel):
    """Shared date-range query parameters for chart-style history endpoints."""

    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> "RangeQueryParams":
        """Validate that the requested date range is coherent."""

        if self.start_date is not None and self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must be greater than or equal to start_date")
        return self


class HistoryQueryParams(BaseModel):
    """Shared query parameters for history table endpoints."""

    symbol: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_date_range(self) -> "HistoryQueryParams":
        """Validate that the requested date range is coherent."""

        if self.start_date is not None and self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must be greater than or equal to start_date")
        if self.symbol is not None:
            self.symbol = self.symbol.upper()
        return self


class TradePageResponse(BaseModel):
    """Paginated trade history response."""

    items: list[TradeResponse]
    total: int
    limit: int
    offset: int


class FillPageResponse(BaseModel):
    """Paginated fill history response."""

    items: list[FillResponse]
    total: int
    limit: int
    offset: int


class EventPageResponse(BaseModel):
    """Paginated runner event response."""

    items: list[EventResponse]
    total: int
    limit: int
    offset: int


class SymbolSummaryResponse(BaseModel):
    """Per-symbol performance and open exposure summary."""

    symbol: str
    total_trades: int
    buy_trades: int
    sell_trades: int
    win_rate: Decimal
    realized_pnl: Decimal
    open_quantity: Decimal
    avg_entry_price: Decimal
    open_exposure: Decimal
    last_trade_time: datetime | None = None


class EquityHistoryPointResponse(BaseModel):
    """Serialized equity history point."""

    snapshot_time: datetime
    equity: Decimal


class PnlHistoryPointResponse(BaseModel):
    """Serialized PnL history point."""

    snapshot_time: datetime
    total_pnl: Decimal
    realized_pnl: Decimal


class DailyPnlPointResponse(BaseModel):
    """Serialized daily PnL point."""

    day: date
    total_pnl: Decimal
    realized_pnl: Decimal


class PnlHistoryResponse(BaseModel):
    """Serialized PnL history response including daily trend reconstruction."""

    points: list[PnlHistoryPointResponse]
    daily: list[DailyPnlPointResponse]


class DrawdownPointResponse(BaseModel):
    """Serialized drawdown point."""

    snapshot_time: datetime
    equity: Decimal
    peak_equity: Decimal
    drawdown: Decimal
    drawdown_pct: Decimal


class DrawdownResponse(BaseModel):
    """Serialized drawdown response."""

    current_drawdown: Decimal
    current_drawdown_pct: Decimal
    max_drawdown: Decimal
    max_drawdown_pct: Decimal
    points: list[DrawdownPointResponse]


class PerformanceQueryParams(BaseModel):
    """Shared query parameters for symbol-scoped performance analytics."""

    symbol: str | None = None
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> "PerformanceQueryParams":
        """Validate the requested performance-analytics filters."""

        if self.start_date is not None and self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must be greater than or equal to start_date")
        if self.symbol is not None:
            self.symbol = self.symbol.upper()
        return self


class PerformanceAnalyticsResponse(BaseModel):
    """Symbol/date-scoped paper-trading performance analytics."""

    symbol: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    total_closed_trades: int
    expectancy_per_closed_trade: Decimal | None = None
    profit_factor: Decimal | None = None
    average_hold_seconds: int | None = None
    average_win: Decimal | None = None
    average_loss: Decimal | None = None
    session_realized_pnl: Decimal
    session_unrealized_pnl: Decimal
    symbol_realized_pnl: Decimal
    max_drawdown: Decimal
    current_drawdown: Decimal


class TradeQualityQueryParams(BaseModel):
    """Query parameters for symbol-scoped trade-quality analytics."""

    symbol: str
    start_date: date | None = None
    end_date: date | None = None
    limit: int = Field(default=5, ge=1, le=50)
    offset: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> "TradeQualityQueryParams":
        """Validate the requested trade-quality filters."""

        if self.end_date is not None and self.start_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must be greater than or equal to start_date")
        self.symbol = self.symbol.upper()
        return self


class HoldTimeDistributionResponse(BaseModel):
    """Serialized hold-time distribution summary."""

    average_seconds: int | None = None
    median_seconds: int | None = None
    p75_seconds: int | None = None
    max_seconds: int | None = None


class TradeQualityDetailResponse(BaseModel):
    """Serialized attribution details for one closed trade."""

    order_id: str
    symbol: str
    entry_time: datetime
    exit_time: datetime
    quantity: Decimal
    entry_price: Decimal
    exit_price: Decimal
    realized_pnl: Decimal
    hold_seconds: int
    mfe_pct: Decimal
    mae_pct: Decimal
    captured_move_pct: Decimal
    giveback_pct: Decimal
    entry_quality_score: Decimal
    exit_quality_score: Decimal


class TradeQualitySummaryResponse(BaseModel):
    """Symbol/date-scoped trade-quality summary metrics."""

    total_closed_trades: int
    average_mfe_pct: Decimal | None = None
    average_mae_pct: Decimal | None = None
    average_captured_move_pct: Decimal | None = None
    average_giveback_pct: Decimal | None = None
    average_entry_quality_score: Decimal | None = None
    average_exit_quality_score: Decimal | None = None
    longest_no_trade_seconds: int | None = None
    hold_time_distribution: HoldTimeDistributionResponse


class TradeQualityResponse(BaseModel):
    """Trade-quality summary plus recent attribution details."""

    symbol: str
    start_date: date | None = None
    end_date: date | None = None
    total_details: int
    limit: int
    offset: int
    summary: TradeQualitySummaryResponse
    details: list[TradeQualityDetailResponse]


class TradeReviewSymbolSummaryResponse(BaseModel):
    """Executed trade count grouped by symbol."""

    symbol: str
    trade_count: int


class SessionReviewResponse(BaseModel):
    """Session-level operator review analytics."""

    trades_per_hour: Decimal | None = None
    trades_per_symbol: list[TradeReviewSymbolSummaryResponse]
    win_rate: Decimal | None = None
    average_pnl: Decimal | None = None
    average_hold_seconds: int | None = None
    fees_paid: Decimal
    idle_duration_seconds: int | None = None
    total_closed_trades: int


class BlockerFrequencyResponse(BaseModel):
    """Frequency of one blocker category."""

    blocker_key: str
    label: str
    count: int
    frequency_pct: Decimal


class ProfileComparisonResponse(BaseModel):
    """Outcome comparison grouped by paper profile."""

    profile: str
    trade_count: int
    realized_pnl: Decimal
    win_rate: Decimal | None = None
    average_expectancy: Decimal | None = None


class ExecutionSourceComparisonResponse(BaseModel):
    """Outcome comparison grouped by manual vs auto source."""

    execution_source: str
    trade_count: int
    realized_pnl: Decimal
    win_rate: Decimal | None = None
    average_expectancy: Decimal | None = None


class TuningSuggestionResponse(BaseModel):
    """Deterministic tuning suggestion for the operator."""

    summary: str


class PaperTradeReviewResponse(BaseModel):
    """Paper trade review analytics for operator tuning."""

    symbol: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    session: SessionReviewResponse
    blockers: list[BlockerFrequencyResponse]
    profiles: list[ProfileComparisonResponse]
    execution_sources: list[ExecutionSourceComparisonResponse]
    suggestions: list[TuningSuggestionResponse]


class ThresholdChangeResponse(BaseModel):
    """One suggested threshold adjustment."""

    threshold: str
    current_value: Decimal
    suggested_value: Decimal


class ProfileCalibrationRecommendationResponse(BaseModel):
    """Calibration recommendation for one profile."""

    profile: str
    profile_health: str
    recommendation: str
    reason: str
    affected_thresholds: list[ThresholdChangeResponse]
    expected_impact: str
    sample_size_warning: str | None = None
    trade_count: int
    win_rate: Decimal | None = None
    expectancy: Decimal | None = None
    fees_paid: Decimal
    blocker_share: dict[str, Decimal]


class ProfileCalibrationResponse(BaseModel):
    """Calibration guidance for conservative, balanced, and aggressive profiles."""

    symbol: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    recommendations: list[ProfileCalibrationRecommendationResponse]
    active_tuning: "ProfileTuningPreviewResponse | None" = None
    pending_tuning: "ProfileTuningPreviewResponse | None" = None


class ProfileCalibrationApplyRequest(BaseModel):
    """Request payload for explicitly applying a tuning recommendation."""

    symbol: str = Field(min_length=1)
    profile: str = Field(min_length=1)
    selected_thresholds: list[str] | None = None
    start_date: date | None = None
    end_date: date | None = None


class ProfileTuningPreviewResponse(BaseModel):
    """Preview of one persisted tuning set."""

    version_id: str
    profile: str
    status: str
    created_at: date
    applied_at: date | None = None
    baseline_version_id: str | None = None
    reason: str
    affected_thresholds: list[ThresholdChangeResponse]


class ProfileCalibrationApplyResponse(BaseModel):
    """Response payload for an applied paper-only tuning recommendation."""

    symbol: str
    profile: str
    applied_to_next_session: bool
    status_message: str
    pending_tuning: ProfileTuningPreviewResponse


class ProfileCalibrationComparisonMetricsResponse(BaseModel):
    """Before/after metrics for a tuned paper profile."""

    session_count: int
    trade_count: int
    expectancy: Decimal | None = None
    profit_factor: Decimal | None = None
    win_rate: Decimal | None = None
    max_drawdown: Decimal | None = None
    fees_paid: Decimal
    blocker_distribution: dict[str, Decimal]


class ProfileCalibrationComparisonResponse(BaseModel):
    """Before/after comparison for an applied profile tuning."""

    symbol: str
    profile: str
    start_date: date | None = None
    end_date: date | None = None
    comparison_status: str
    status_message: str | None = None
    active_tuning: ProfileTuningPreviewResponse | None = None
    baseline_tuning: ProfileTuningPreviewResponse | None = None
    before: ProfileCalibrationComparisonMetricsResponse | None = None
    after: ProfileCalibrationComparisonMetricsResponse | None = None


def _to_trade_response(record: TradeRecord) -> TradeResponse:
    """Convert a trade record to a response model."""

    return TradeResponse(**asdict(record))


def _to_fill_response(record: FillRecord) -> FillResponse:
    """Convert a fill record to a response model."""

    return FillResponse(**asdict(record))


def _to_position_response(record: PositionSnapshotRecord) -> PositionResponse:
    """Convert a position snapshot record to a response model."""

    return PositionResponse(**asdict(record))


def _to_equity_response(record: PnlSnapshotRecord | None) -> EquityResponse:
    """Convert a PnL snapshot into an equity payload."""

    if record is None:
        return EquityResponse()
    return EquityResponse(**asdict(record))


def _to_event_response(record: RunnerEventRecord) -> EventResponse:
    """Convert a runner event record to a response model."""

    return EventResponse(
        event_type=record.event_type,
        symbol=record.symbol,
        message=record.message,
        payload=json.loads(record.payload_json),
        event_time=record.event_time,
    )


def _to_equity_history_point_response(record: EquityHistoryPoint) -> EquityHistoryPointResponse:
    """Convert an equity history point to a response model."""

    return EquityHistoryPointResponse(**asdict(record))


def _to_pnl_history_point_response(record: PnlHistoryPoint) -> PnlHistoryPointResponse:
    """Convert a PnL history point to a response model."""

    return PnlHistoryPointResponse(**asdict(record))


def _to_daily_pnl_point_response(record: DailyPnlRecord) -> DailyPnlPointResponse:
    """Convert a daily PnL record to a response model."""

    return DailyPnlPointResponse(**asdict(record))


def _to_drawdown_point_response(record: DrawdownPoint) -> DrawdownPointResponse:
    """Convert a drawdown point to a response model."""

    return DrawdownPointResponse(**asdict(record))


def _to_drawdown_response(record: DrawdownSummary) -> DrawdownResponse:
    """Convert a drawdown summary to a response model."""

    return DrawdownResponse(
        current_drawdown=record.current_drawdown,
        current_drawdown_pct=record.current_drawdown_pct,
        max_drawdown=record.max_drawdown,
        max_drawdown_pct=record.max_drawdown_pct,
        points=[_to_drawdown_point_response(point) for point in record.points],
    )


def _to_hold_time_distribution_response(record: HoldTimeDistributionSummary) -> HoldTimeDistributionResponse:
    """Convert a hold-time summary into a response model."""

    return HoldTimeDistributionResponse(**asdict(record))


def _to_trade_quality_detail_response(record: TradeQualityDetail) -> TradeQualityDetailResponse:
    """Convert one trade-quality detail into a response model."""

    return TradeQualityDetailResponse(**asdict(record))


def _to_trade_quality_response(
    *,
    symbol: str,
    start_date: date | None,
    end_date: date | None,
    limit: int,
    offset: int,
    analytics: TradeQualityAnalytics,
) -> TradeQualityResponse:
    """Convert trade-quality analytics into an API response."""

    paged_details = analytics.details[offset: offset + limit]
    return TradeQualityResponse(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        total_details=len(analytics.details),
        limit=limit,
        offset=offset,
        summary=TradeQualitySummaryResponse(
            total_closed_trades=analytics.summary.total_closed_trades,
            average_mfe_pct=analytics.summary.average_mfe_pct,
            average_mae_pct=analytics.summary.average_mae_pct,
            average_captured_move_pct=analytics.summary.average_captured_move_pct,
            average_giveback_pct=analytics.summary.average_giveback_pct,
            average_entry_quality_score=analytics.summary.average_entry_quality_score,
            average_exit_quality_score=analytics.summary.average_exit_quality_score,
            longest_no_trade_seconds=analytics.summary.longest_no_trade_seconds,
            hold_time_distribution=_to_hold_time_distribution_response(
                analytics.summary.hold_time_distribution
            ),
        ),
        details=[_to_trade_quality_detail_response(record) for record in paged_details],
    )


def _to_session_review_response(record: SessionAnalytics) -> SessionReviewResponse:
    """Convert review session analytics into an API response."""

    return SessionReviewResponse(
        trades_per_hour=record.trades_per_hour,
        trades_per_symbol=[
            TradeReviewSymbolSummaryResponse(symbol=item.symbol, trade_count=item.trade_count)
            for item in record.trades_per_symbol
        ],
        win_rate=record.win_rate,
        average_pnl=record.average_pnl,
        average_hold_seconds=record.average_hold_seconds,
        fees_paid=record.fees_paid,
        idle_duration_seconds=record.idle_duration_seconds,
        total_closed_trades=record.total_closed_trades,
    )


def _to_blocker_frequency_response(record: BlockerFrequency) -> BlockerFrequencyResponse:
    """Convert blocker analytics into an API response."""

    return BlockerFrequencyResponse(**asdict(record))


def _to_profile_comparison_response(record: ProfileComparison) -> ProfileComparisonResponse:
    """Convert profile comparison analytics into an API response."""

    return ProfileComparisonResponse(**asdict(record))


def _to_execution_source_response(record: ExecutionSourceComparison) -> ExecutionSourceComparisonResponse:
    """Convert manual-vs-auto comparison analytics into an API response."""

    return ExecutionSourceComparisonResponse(**asdict(record))


def _to_tuning_suggestion_response(record: TuningSuggestion) -> TuningSuggestionResponse:
    """Convert a tuning suggestion into an API response."""

    return TuningSuggestionResponse(**asdict(record))


def _to_paper_trade_review_response(review: PaperTradeReview) -> PaperTradeReviewResponse:
    """Convert paper trade review analytics into an API response."""

    return PaperTradeReviewResponse(
        symbol=review.symbol,
        start_date=review.start_date,
        end_date=review.end_date,
        session=_to_session_review_response(review.session),
        blockers=[_to_blocker_frequency_response(item) for item in review.blockers],
        profiles=[_to_profile_comparison_response(item) for item in review.profiles],
        execution_sources=[_to_execution_source_response(item) for item in review.execution_sources],
        suggestions=[_to_tuning_suggestion_response(item) for item in review.suggestions],
    )


def _to_threshold_change_response(record: ThresholdChange) -> ThresholdChangeResponse:
    """Convert a threshold change into an API response."""

    return ThresholdChangeResponse(**asdict(record))


def _to_profile_calibration_recommendation_response(
    record: ProfileCalibrationRecommendation,
) -> ProfileCalibrationRecommendationResponse:
    """Convert one profile calibration recommendation into an API response."""

    return ProfileCalibrationRecommendationResponse(
        profile=record.profile,
        profile_health=record.profile_health,
        recommendation=record.recommendation,
        reason=record.reason,
        affected_thresholds=[_to_threshold_change_response(item) for item in record.affected_thresholds],
        expected_impact=record.expected_impact,
        sample_size_warning=record.sample_size_warning,
        trade_count=record.trade_count,
        win_rate=record.win_rate,
        expectancy=record.expectancy,
        fees_paid=record.fees_paid,
        blocker_share=record.blocker_share,
    )


def _to_profile_calibration_response(report: ProfileCalibrationReport) -> ProfileCalibrationResponse:
    """Convert profile calibration output into an API response."""

    return ProfileCalibrationResponse(
        symbol=report.symbol,
        start_date=report.start_date,
        end_date=report.end_date,
        recommendations=[
            _to_profile_calibration_recommendation_response(item) for item in report.recommendations
        ],
        active_tuning=_to_profile_tuning_preview_response(report.active_tuning),
        pending_tuning=_to_profile_tuning_preview_response(report.pending_tuning),
    )


def _to_profile_tuning_preview_response(
    record: ProfileTuningPreview | None,
) -> ProfileTuningPreviewResponse | None:
    """Convert a persisted tuning preview into an API response."""

    if record is None:
        return None
    return ProfileTuningPreviewResponse(
        version_id=record.version_id,
        profile=record.profile,
        status=record.status,
        created_at=record.created_at,
        applied_at=record.applied_at,
        baseline_version_id=record.baseline_version_id,
        reason=record.reason,
        affected_thresholds=[
            _to_threshold_change_response(item) for item in record.affected_thresholds
        ],
    )


def _to_profile_calibration_comparison_metrics_response(
    record: ProfileCalibrationComparisonMetrics | None,
) -> ProfileCalibrationComparisonMetricsResponse | None:
    """Convert comparison metrics into an API response."""

    if record is None:
        return None
    return ProfileCalibrationComparisonMetricsResponse(**asdict(record))


def _to_profile_calibration_comparison_response(
    record: ProfileCalibrationComparison,
) -> ProfileCalibrationComparisonResponse:
    """Convert a calibration comparison into an API response."""

    return ProfileCalibrationComparisonResponse(
        symbol=record.symbol,
        profile=record.profile,
        start_date=record.start_date,
        end_date=record.end_date,
        comparison_status=record.comparison_status,
        status_message=record.status_message,
        active_tuning=_to_profile_tuning_preview_response(record.active_tuning),
        baseline_tuning=_to_profile_tuning_preview_response(record.baseline_tuning),
        before=_to_profile_calibration_comparison_metrics_response(record.before),
        after=_to_profile_calibration_comparison_metrics_response(record.after),
    )


def _build_metrics(trades: list[TradeRecord], latest_pnl: PnlSnapshotRecord | None) -> MetricsResponse:
    """Build deterministic paper-mode metrics from persisted trade history."""

    executed_trades = [trade for trade in trades if trade.status == "executed"]
    closing_trades = [trade for trade in executed_trades if trade.side == "SELL"]

    realized_pnl = latest_pnl.realized_pnl if latest_pnl is not None else Decimal("0")
    average_pnl_per_trade = Decimal("0")
    wins = 0
    max_winning_streak = 0
    max_losing_streak = 0
    current_winning_streak = 0
    current_losing_streak = 0

    if closing_trades:
        average_pnl_per_trade = realized_pnl / Decimal(len(closing_trades))
        for trade in closing_trades:
            if trade.realized_pnl > Decimal("0"):
                wins += 1
                current_winning_streak += 1
                current_losing_streak = 0
            elif trade.realized_pnl < Decimal("0"):
                current_losing_streak += 1
                current_winning_streak = 0
            else:
                current_winning_streak = 0
                current_losing_streak = 0
            max_winning_streak = max(max_winning_streak, current_winning_streak)
            max_losing_streak = max(max_losing_streak, current_losing_streak)

    win_rate = Decimal("0")
    if closing_trades:
        win_rate = (Decimal(wins) * Decimal("100")) / Decimal(len(closing_trades))

    current_equity = latest_pnl.equity if latest_pnl is not None else Decimal("0")
    return MetricsResponse(
        total_trades=len(executed_trades),
        win_rate=win_rate,
        realized_pnl=realized_pnl,
        average_pnl_per_trade=average_pnl_per_trade,
        current_equity=current_equity,
        max_winning_streak=max_winning_streak,
        max_losing_streak=max_losing_streak,
    )


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Return API health for paper-mode monitoring."""

    settings: Settings = get_settings()
    return HealthResponse(
        **HealthStatus(
            name=settings.app_name,
            status="ok",
            mode=settings.app_mode,
        ).to_dict(),
        storage="sqlite",
    )


@router.get("/trades", response_model=TradePageResponse)
def get_trades(
    query: Annotated[HistoryQueryParams, Depends()],
    data_access: Annotated[DashboardDataAccess, Depends(get_dashboard_data_access)],
) -> TradePageResponse:
    """Return filtered, paginated trade history."""

    items, total = data_access.get_trades_page(
        symbol=query.symbol,
        start_date=query.start_date,
        end_date=query.end_date,
        limit=query.limit,
        offset=query.offset,
    )
    return TradePageResponse(
        items=[_to_trade_response(record) for record in items],
        total=total,
        limit=query.limit,
        offset=query.offset,
    )


@router.get("/fills", response_model=FillPageResponse)
def get_fills(
    query: Annotated[HistoryQueryParams, Depends()],
    data_access: Annotated[DashboardDataAccess, Depends(get_dashboard_data_access)],
) -> FillPageResponse:
    """Return filtered, paginated fills."""

    items, total = data_access.get_fills_page(
        symbol=query.symbol,
        start_date=query.start_date,
        end_date=query.end_date,
        limit=query.limit,
        offset=query.offset,
    )
    return FillPageResponse(
        items=[_to_fill_response(record) for record in items],
        total=total,
        limit=query.limit,
        offset=query.offset,
    )


@router.get("/positions", response_model=list[PositionResponse])
def get_positions(
    data_access: Annotated[DashboardDataAccess, Depends(get_dashboard_data_access)],
) -> list[PositionResponse]:
    """Return the latest open positions from persisted snapshots."""

    return [_to_position_response(record) for record in data_access.get_positions()]


@router.get("/equity", response_model=EquityResponse)
def get_equity(
    data_access: Annotated[DashboardDataAccess, Depends(get_dashboard_data_access)],
) -> EquityResponse:
    """Return the latest persisted equity snapshot."""

    return _to_equity_response(data_access.get_latest_equity())


@router.get("/equity/history", response_model=list[EquityHistoryPointResponse])
def get_equity_history(
    query: Annotated[RangeQueryParams, Depends()],
    data_access: Annotated[DashboardDataAccess, Depends(get_dashboard_data_access)],
) -> list[EquityHistoryPointResponse]:
    """Return persisted equity history for charting."""

    return [
        _to_equity_history_point_response(record)
        for record in data_access.get_equity_history(
            start_date=query.start_date,
            end_date=query.end_date,
        )
    ]


@router.get("/daily-pnl", response_model=Decimal)
def get_daily_pnl(
    data_access: Annotated[DashboardDataAccess, Depends(get_dashboard_data_access)],
    day: date | None = None,
) -> Decimal:
    """Return the latest total PnL for the requested UTC day."""

    return data_access.get_daily_pnl(day)


@router.get("/pnl/history", response_model=PnlHistoryResponse)
def get_pnl_history(
    query: Annotated[RangeQueryParams, Depends()],
    data_access: Annotated[DashboardDataAccess, Depends(get_dashboard_data_access)],
) -> PnlHistoryResponse:
    """Return total/realized PnL history and derived daily trend."""

    return PnlHistoryResponse(
        points=[
            _to_pnl_history_point_response(record)
            for record in data_access.get_pnl_history(
                start_date=query.start_date,
                end_date=query.end_date,
            )
        ],
        daily=[
            _to_daily_pnl_point_response(record)
            for record in data_access.get_daily_pnl_history(
                start_date=query.start_date,
                end_date=query.end_date,
            )
        ],
    )


@router.get("/drawdown", response_model=DrawdownResponse)
def get_drawdown(
    query: Annotated[RangeQueryParams, Depends()],
    data_access: Annotated[DashboardDataAccess, Depends(get_dashboard_data_access)],
) -> DrawdownResponse:
    """Return derived drawdown summary and time series."""

    return _to_drawdown_response(
        data_access.get_drawdown_summary(
            start_date=query.start_date,
            end_date=query.end_date,
        )
    )


@router.get("/events", response_model=EventPageResponse)
def get_events(
    query: Annotated[HistoryQueryParams, Depends()],
    data_access: Annotated[DashboardDataAccess, Depends(get_dashboard_data_access)],
) -> EventPageResponse:
    """Return filtered, paginated runner events."""

    items, total = data_access.get_events_page(
        symbol=query.symbol,
        start_date=query.start_date,
        end_date=query.end_date,
        limit=query.limit,
        offset=query.offset,
    )
    return EventPageResponse(
        items=[_to_event_response(record) for record in items],
        total=total,
        limit=query.limit,
        offset=query.offset,
    )


@router.get("/metrics", response_model=MetricsResponse)
def get_metrics(
    data_access: Annotated[DashboardDataAccess, Depends(get_dashboard_data_access)],
) -> MetricsResponse:
    """Return aggregate paper-trading metrics from persisted history."""

    trades = data_access.get_all_trades()
    latest_pnl = data_access.get_latest_equity()
    return _build_metrics(trades, latest_pnl)


@router.get("/performance", response_model=PerformanceAnalyticsResponse)
def get_performance_analytics(
    query: Annotated[PerformanceQueryParams, Depends()],
    data_access: Annotated[DashboardDataAccess, Depends(get_dashboard_data_access)],
) -> PerformanceAnalyticsResponse:
    """Return symbol/date-scoped paper-trading performance analytics."""

    analytics = build_performance_analytics(
        trades=data_access.get_trades(
            symbol=query.symbol,
            end_date=query.end_date,
        ),
        latest_pnl=data_access.get_latest_equity_in_range(
            start_date=query.start_date,
            end_date=query.end_date,
        ),
        drawdown=data_access.get_drawdown_summary(
            start_date=query.start_date,
            end_date=query.end_date,
        ),
        start_date=query.start_date,
        end_date=query.end_date,
    )
    return PerformanceAnalyticsResponse(
        symbol=query.symbol,
        start_date=query.start_date,
        end_date=query.end_date,
        total_closed_trades=analytics.total_closed_trades,
        expectancy_per_closed_trade=analytics.expectancy_per_closed_trade,
        profit_factor=analytics.profit_factor,
        average_hold_seconds=analytics.average_hold_seconds,
        average_win=analytics.average_win,
        average_loss=analytics.average_loss,
        session_realized_pnl=analytics.session_realized_pnl,
        session_unrealized_pnl=analytics.session_unrealized_pnl,
        symbol_realized_pnl=analytics.symbol_realized_pnl,
        max_drawdown=analytics.max_drawdown,
        current_drawdown=analytics.current_drawdown,
    )


@router.get("/performance/trade-quality", response_model=TradeQualityResponse)
def get_trade_quality_analytics(
    query: Annotated[TradeQualityQueryParams, Depends()],
    data_access: Annotated[DashboardDataAccess, Depends(get_dashboard_data_access)],
) -> TradeQualityResponse:
    """Return symbol/date-scoped trade-quality attribution analytics."""

    analytics = build_trade_quality_analytics(
        trades=data_access.get_trades(
            symbol=query.symbol,
            start_date=None,
            end_date=query.end_date,
        ),
        candles=data_access.get_market_candles(
            symbol=query.symbol,
            end_date=query.end_date,
        ),
        start_date=query.start_date,
        end_date=query.end_date,
    )
    return _to_trade_quality_response(
        symbol=query.symbol,
        start_date=query.start_date,
        end_date=query.end_date,
        limit=query.limit,
        offset=query.offset,
        analytics=analytics,
    )


@router.get("/performance/review", response_model=PaperTradeReviewResponse)
def get_paper_trade_review(
    query: Annotated[PerformanceQueryParams, Depends()],
    data_access: DashboardDataAccess = Depends(get_dashboard_data_access),
) -> PaperTradeReviewResponse:
    """Return operator-facing paper trade review analytics for one symbol/date scope."""

    review = build_paper_trade_review(
        symbol=query.symbol,
        start_date=query.start_date,
        end_date=query.end_date,
        trades=data_access.get_trades(
            symbol=query.symbol,
            start_date=query.start_date,
            end_date=query.end_date,
        ),
        fills=data_access.get_fills(
            symbol=query.symbol,
            start_date=query.start_date,
            end_date=query.end_date,
        ),
        events=data_access.get_events(
            symbol=query.symbol,
            start_date=query.start_date,
            end_date=query.end_date,
        ),
    )
    return _to_paper_trade_review_response(review)


@router.get("/performance/profile-calibration", response_model=ProfileCalibrationResponse)
def get_profile_calibration(
    query: Annotated[PerformanceQueryParams, Depends()],
    profile: str | None = None,
    data_access: DashboardDataAccess = Depends(get_dashboard_data_access),
) -> ProfileCalibrationResponse:
    """Return profile calibration recommendations from observed paper outcomes."""

    requested_profile = profile.strip().lower() if profile is not None else "balanced"
    active_tuning = (
        data_access.repository.get_latest_profile_tuning_set(
            symbol=query.symbol,
            profile=requested_profile,
            status="applied",
        )
        if query.symbol
        else None
    )
    pending_tuning = (
        data_access.repository.get_latest_profile_tuning_set(
            symbol=query.symbol,
            profile=requested_profile,
            status="pending",
        )
        if query.symbol
        else None
    )
    report = build_profile_calibration_report(
        symbol=query.symbol,
        start_date=query.start_date,
        end_date=query.end_date,
        trades=data_access.get_trades(
            symbol=query.symbol,
            start_date=query.start_date,
            end_date=query.end_date,
        ),
        fills=data_access.get_fills(
            symbol=query.symbol,
            start_date=query.start_date,
            end_date=query.end_date,
        ),
        events=data_access.get_events(
            symbol=query.symbol,
            start_date=query.start_date,
            end_date=query.end_date,
        ),
        drawdown=data_access.get_drawdown_summary(
            start_date=query.start_date,
            end_date=query.end_date,
        ),
    )
    return _to_profile_calibration_response(
        with_tuning_previews(
            report,
            active_tuning=active_tuning,
            pending_tuning=pending_tuning,
        )
    )


@router.post("/performance/profile-calibration/apply", response_model=ProfileCalibrationApplyResponse)
def apply_profile_calibration(
    request: ProfileCalibrationApplyRequest,
    data_access: DashboardDataAccess = Depends(get_dashboard_data_access),
    settings: Settings = Depends(get_settings),
) -> ProfileCalibrationApplyResponse:
    """Persist an explicit paper-only profile tuning for the next session."""

    if settings.app_mode != "paper":
        raise HTTPException(status_code=409, detail="Profile tuning can only be applied in paper mode.")

    symbol = request.symbol.strip().upper()
    profile = request.profile.strip().lower()
    report = build_profile_calibration_report(
        symbol=symbol,
        start_date=request.start_date,
        end_date=request.end_date,
        trades=data_access.get_trades(
            symbol=symbol,
            start_date=request.start_date,
            end_date=request.end_date,
        ),
        fills=data_access.get_fills(
            symbol=symbol,
            start_date=request.start_date,
            end_date=request.end_date,
        ),
        events=data_access.get_events(
            symbol=symbol,
            start_date=request.start_date,
            end_date=request.end_date,
        ),
        drawdown=data_access.get_drawdown_summary(
            start_date=request.start_date,
            end_date=request.end_date,
        ),
    )
    recommendation = next(
        (item for item in report.recommendations if item.profile == profile),
        None,
    )
    if recommendation is None:
        raise HTTPException(status_code=404, detail=f"No calibration recommendation exists for profile {profile}.")
    if not recommendation.affected_thresholds:
        raise HTTPException(status_code=400, detail="No threshold changes are currently recommended for this profile.")

    selected_thresholds = set(request.selected_thresholds or [])
    baseline_tuning = data_access.repository.get_latest_profile_tuning_set(
        symbol=symbol,
        profile=profile,
        status="applied",
    )
    if baseline_tuning is not None:
        baseline_config = json.loads(baseline_tuning.config_json)
        baseline_version_id = baseline_tuning.version_id
    else:
        baseline_config = {
            change.threshold: str(change.current_value)
            for change in recommendation.affected_thresholds
        }
        for threshold_name, default_value in PROFILE_THRESHOLDS[profile].items():
            baseline_config.setdefault(threshold_name, str(default_value))
        baseline_version_id = None

    next_config = dict(baseline_config)
    selected_changes = [
        change
        for change in recommendation.affected_thresholds
        if not selected_thresholds or change.threshold in selected_thresholds
    ]
    if not selected_changes:
        raise HTTPException(status_code=400, detail="Select at least one recommended threshold to apply.")
    for change in selected_changes:
        next_config[change.threshold] = str(change.suggested_value)

    tuning_set = data_access.repository.create_profile_tuning_set(
        symbol=symbol,
        profile=profile,
        config_json=json.dumps(next_config, sort_keys=True),
        baseline_config_json=json.dumps(baseline_config, sort_keys=True),
        baseline_version_id=baseline_version_id,
        reason=recommendation.reason,
    )
    preview = _to_profile_tuning_preview_response(
        ProfileTuningPreview(
            version_id=tuning_set.version_id,
            profile=tuning_set.profile,
            status=tuning_set.status,
            created_at=tuning_set.created_at.date(),
            applied_at=tuning_set.applied_at.date() if tuning_set.applied_at is not None else None,
            baseline_version_id=tuning_set.baseline_version_id,
            reason=tuning_set.reason,
            affected_thresholds=selected_changes,
        )
    )
    assert preview is not None
    return ProfileCalibrationApplyResponse(
        symbol=symbol,
        profile=profile,
        applied_to_next_session=True,
        status_message="Recommendation saved. It will apply to the next paper session only after you start a new run.",
        pending_tuning=preview,
    )


@router.get("/performance/profile-calibration/comparison", response_model=ProfileCalibrationComparisonResponse)
def get_profile_calibration_comparison(
    symbol: Annotated[str, Query(min_length=1)],
    profile: Annotated[str, Query(min_length=1)],
    start_date: date | None = None,
    end_date: date | None = None,
    session_id: str | None = None,
    data_access: DashboardDataAccess = Depends(get_dashboard_data_access),
) -> ProfileCalibrationComparisonResponse:
    """Return before/after comparison for the latest applied profile tuning."""

    normalized_symbol = symbol.strip().upper()
    normalized_profile = profile.strip().lower()
    active_tuning = data_access.repository.get_latest_profile_tuning_set(
        symbol=normalized_symbol,
        profile=normalized_profile,
        status="applied",
    )
    baseline_tuning = (
        data_access.repository.get_profile_tuning_set_by_version(active_tuning.baseline_version_id)
        if active_tuning is not None and active_tuning.baseline_version_id is not None
        else None
    )
    comparison = build_profile_calibration_comparison(
        symbol=normalized_symbol,
        profile=normalized_profile,
        start_date=start_date,
        end_date=end_date,
        session_runs=data_access.repository.get_paper_session_runs(
            symbol=normalized_symbol,
            trading_profile=normalized_profile,
        ),
        trades=data_access.get_trades(
            symbol=normalized_symbol,
            start_date=start_date,
            end_date=end_date,
        ),
        fills=data_access.get_fills(
            symbol=normalized_symbol,
            start_date=start_date,
            end_date=end_date,
        ),
        events=data_access.get_events(
            symbol=normalized_symbol,
            start_date=start_date,
            end_date=end_date,
        ),
        active_tuning=active_tuning,
        baseline_tuning=baseline_tuning,
        session_id=session_id,
    )
    return _to_profile_calibration_comparison_response(comparison)


@router.get("/summary/symbols", response_model=list[SymbolSummaryResponse])
def get_symbol_summaries(
    data_access: Annotated[DashboardDataAccess, Depends(get_dashboard_data_access)],
    symbols: Annotated[list[str] | None, Query()] = None,
) -> list[SymbolSummaryResponse]:
    """Return per-symbol performance and open exposure summaries."""

    requested_symbols = {symbol.upper() for symbol in symbols} if symbols else None
    positions_by_symbol = {position.symbol: position for position in data_access.get_all_positions()}
    summary_by_symbol: dict[str, dict[str, Any]] = {}

    for trade in data_access.get_all_trades():
        if trade.status != "executed":
            continue
        symbol = trade.symbol
        if requested_symbols is not None and symbol not in requested_symbols:
            continue

        summary = summary_by_symbol.setdefault(
            symbol,
            {
                "symbol": symbol,
                "total_trades": 0,
                "buy_trades": 0,
                "sell_trades": 0,
                "win_rate": Decimal("0"),
                "realized_pnl": Decimal("0"),
                "open_quantity": Decimal("0"),
                "avg_entry_price": Decimal("0"),
                "open_exposure": Decimal("0"),
                "last_trade_time": None,
                "_wins": 0,
            },
        )
        summary["total_trades"] += 1
        summary["realized_pnl"] += trade.realized_pnl
        summary["last_trade_time"] = trade.event_time
        if trade.side == "BUY":
            summary["buy_trades"] += 1
        elif trade.side == "SELL":
            summary["sell_trades"] += 1
            if trade.realized_pnl > Decimal("0"):
                summary["_wins"] += 1

    for symbol, position in positions_by_symbol.items():
        if requested_symbols is not None and symbol not in requested_symbols:
            continue
        summary = summary_by_symbol.setdefault(
            symbol,
            {
                "symbol": symbol,
                "total_trades": 0,
                "buy_trades": 0,
                "sell_trades": 0,
                "win_rate": Decimal("0"),
                "realized_pnl": Decimal("0"),
                "open_quantity": Decimal("0"),
                "avg_entry_price": Decimal("0"),
                "open_exposure": Decimal("0"),
                "last_trade_time": None,
                "_wins": 0,
            },
        )
        summary["open_quantity"] = position.quantity
        summary["avg_entry_price"] = position.avg_entry_price
        summary["open_exposure"] = position.quantity * position.avg_entry_price

    responses: list[SymbolSummaryResponse] = []
    for symbol in sorted(summary_by_symbol):
        summary = summary_by_symbol[symbol]
        if summary["sell_trades"] > 0:
            summary["win_rate"] = (
                Decimal(summary["_wins"]) * Decimal("100")
            ) / Decimal(summary["sell_trades"])
        summary.pop("_wins")
        responses.append(SymbolSummaryResponse(**summary))
    return responses
