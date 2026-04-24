"""FastAPI dependencies for request-scoped dashboard data access."""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from fastapi import Depends, HTTPException

from app.config import Settings, get_settings
from app.storage import StorageRepository
from app.storage.models import (
    DailyPnlRecord,
    DrawdownSummary,
    EquityHistoryPoint,
    FillRecord,
    MarketCandleSnapshotRecord,
    PnlHistoryPoint,
    PnlSnapshotRecord,
    PositionSnapshotRecord,
    RunnerEventRecord,
    TradeRecord,
)


@dataclass(slots=True)
class DashboardDataAccess:
    """Request-scoped dashboard data access wrapper."""

    repository: StorageRepository

    def get_trades_page(
        self,
        *,
        symbol: str | None,
        start_date: date | None,
        end_date: date | None,
        limit: int,
        offset: int,
    ) -> tuple[list[TradeRecord], int]:
        """Return a filtered trade page and its total row count."""

        return (
            self.repository.get_trade_history(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                offset=offset,
            ),
            self.repository.count_trades(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
            ),
        )

    def get_fills_page(
        self,
        *,
        symbol: str | None,
        start_date: date | None,
        end_date: date | None,
        limit: int,
        offset: int,
    ) -> tuple[list[FillRecord], int]:
        """Return a filtered fill page and its total row count."""

        return (
            self.repository.get_fill_history(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                offset=offset,
            ),
            self.repository.count_fills(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
            ),
        )

    def get_events_page(
        self,
        *,
        symbol: str | None,
        start_date: date | None,
        end_date: date | None,
        limit: int,
        offset: int,
    ) -> tuple[list[RunnerEventRecord], int]:
        """Return a filtered event page and its total row count."""

        return (
            self.repository.get_runner_events(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                offset=offset,
            ),
            self.repository.count_runner_events(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
            ),
        )

    def get_positions(self) -> list[PositionSnapshotRecord]:
        """Return current open positions."""

        return self.repository.get_current_positions()

    def get_latest_equity(self) -> PnlSnapshotRecord | None:
        """Return the latest persisted equity snapshot."""

        return self.repository.get_latest_pnl_snapshot()

    def get_latest_equity_in_range(
        self,
        *,
        start_date: date | None,
        end_date: date | None,
    ) -> PnlSnapshotRecord | None:
        """Return the latest persisted equity snapshot within an optional range."""

        return self.repository.get_latest_pnl_snapshot(
            start_date=start_date,
            end_date=end_date,
        )

    def get_daily_pnl(self, day: date | None) -> Decimal:
        """Return daily PnL for the requested UTC day."""

        return self.repository.get_daily_pnl(day)

    def get_all_trades(self) -> list[TradeRecord]:
        """Return all persisted trades for aggregate calculations."""

        return self.repository.get_trade_history()

    def get_trades(
        self,
        *,
        symbol: str | None,
        start_date: date | None = None,
        end_date: date | None,
    ) -> list[TradeRecord]:
        """Return trades needed for performance analytics calculations."""

        return self.repository.get_trade_history(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )

    def get_fills(
        self,
        *,
        symbol: str | None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[FillRecord]:
        """Return fills needed for review analytics calculations."""

        return self.repository.get_fill_history(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )

    def get_events(
        self,
        *,
        symbol: str | None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[RunnerEventRecord]:
        """Return runner events needed for review analytics calculations."""

        return self.repository.get_runner_events(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
        )

    def get_market_candles(
        self,
        *,
        symbol: str,
        end_date: date | None,
    ) -> list[MarketCandleSnapshotRecord]:
        """Return persisted closed candles for symbol-scoped attribution analytics."""

        return self.repository.get_market_candle_history(
            symbol=symbol,
            end_date=end_date,
        )

    def get_all_positions(self) -> list[PositionSnapshotRecord]:
        """Return all open positions for symbol summaries."""

        return self.repository.get_current_positions()

    def get_equity_history(
        self,
        *,
        start_date: date | None,
        end_date: date | None,
    ) -> list[EquityHistoryPoint]:
        """Return persisted equity history points."""

        return self.repository.get_equity_history(
            start_date=start_date,
            end_date=end_date,
        )

    def get_pnl_history(
        self,
        *,
        start_date: date | None,
        end_date: date | None,
    ) -> list[PnlHistoryPoint]:
        """Return persisted total and realized PnL history points."""

        return self.repository.get_pnl_history(
            start_date=start_date,
            end_date=end_date,
        )

    def get_daily_pnl_history(
        self,
        *,
        start_date: date | None,
        end_date: date | None,
    ) -> list[DailyPnlRecord]:
        """Return derived daily PnL points from persisted snapshots."""

        return self.repository.get_daily_pnl_history(
            start_date=start_date,
            end_date=end_date,
        )

    def get_drawdown_summary(
        self,
        *,
        start_date: date | None,
        end_date: date | None,
    ) -> DrawdownSummary:
        """Return derived drawdown summary from persisted equity history."""

        return self.repository.get_drawdown_summary(
            start_date=start_date,
            end_date=end_date,
        )


def get_dashboard_data_access(
    settings: Settings = Depends(get_settings),
) -> Generator[DashboardDataAccess, None, None]:
    """Provide request-scoped dashboard data access in paper mode."""

    if settings.app_mode != "paper":
        raise HTTPException(status_code=503, detail="Dashboard API is available only in paper mode.")

    repository = StorageRepository(settings.database_url)
    try:
        yield DashboardDataAccess(repository)
    finally:
        repository.close()
