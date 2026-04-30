"""Background historical-candle backfill service."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import httpx

from app.data.historical_candles import SupportedInterval, interval_to_timedelta, lookback_window, now_utc, parse_rest_kline
from app.exchange.binance_rest import BinanceRestClient
from app.storage import StorageRepository
from app.storage.candle_repository import CandleBackfillStatus, CandleRepository

LOGGER = logging.getLogger(__name__)

BackfillState = Literal["not_started", "loading", "ready", "partial", "failed"]


@dataclass(slots=True)
class _TaskState:
    status: BackfillState
    message: str
    last_error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    effective_interval: SupportedInterval | None = None


class HistoricalBackfillService:
    """Fetch and persist recent Binance klines without blocking the workstation."""

    def __init__(self, *, rest_client: BinanceRestClient, database_url: str) -> None:
        self._rest_client = rest_client
        self._database_url = database_url
        self._tasks: dict[tuple[str, SupportedInterval, int], asyncio.Task[None]] = {}
        self._states: dict[tuple[str, SupportedInterval, int], _TaskState] = {}
        self._lock = asyncio.Lock()

    def status(
        self,
        *,
        symbol: str,
        interval: SupportedInterval = "1m",
        lookback_days: int = 7,
    ) -> CandleBackfillStatus:
        key = (symbol.strip().upper(), interval, lookback_days)
        state = self._states.get(key)
        repository = StorageRepository(self._database_url)
        try:
            candle_repository = CandleRepository(repository)
            return candle_repository.status(
                symbol=key[0],
                interval=interval,
                lookback_days=lookback_days,
                loading=state is not None and state.status == "loading",
                failed_message=state.last_error if state is not None and state.status == "failed" else None,
                effective_interval=state.effective_interval if state is not None else None,
            )
        finally:
            repository.close()

    async def ensure_recent_history(
        self,
        *,
        symbol: str,
        interval: SupportedInterval = "1m",
        lookback_days: int = 7,
        force: bool = False,
    ) -> CandleBackfillStatus:
        normalized_symbol = symbol.strip().upper()
        key = (normalized_symbol, interval, lookback_days)
        current_status = self.status(symbol=normalized_symbol, interval=interval, lookback_days=lookback_days)
        if force or current_status.status in {"not_started", "failed"} or _is_stale(current_status):
            async with self._lock:
                task = self._tasks.get(key)
                if task is None or task.done():
                    self._states[key] = _TaskState(
                        status="loading",
                        message=f"Historical {interval} backfill is loading for {normalized_symbol}.",
                        started_at=now_utc(),
                    )
                    self._tasks[key] = asyncio.create_task(
                        self._run_backfill(symbol=normalized_symbol, interval=interval, lookback_days=lookback_days),
                        name=f"backfill-{normalized_symbol.lower()}-{interval}-{lookback_days}d",
                    )
        return self.status(symbol=normalized_symbol, interval=interval, lookback_days=lookback_days)

    async def _run_backfill(
        self,
        *,
        symbol: str,
        interval: SupportedInterval,
        lookback_days: int,
    ) -> None:
        key = (symbol, interval, lookback_days)
        effective_interval: SupportedInterval = interval
        try:
            await self._fetch_and_persist(symbol=symbol, interval=interval, lookback_days=lookback_days)
        except httpx.HTTPError as exc:
            if interval == "1m":
                effective_interval = "5m"
                await self._fetch_and_persist(symbol=symbol, interval="5m", lookback_days=lookback_days)
                self._states[key] = _TaskState(
                    status="partial",
                    message=f"Fetched 7 days of 5m candles for {symbol} because 1m backfill was unavailable.",
                    started_at=self._states.get(key).started_at if key in self._states else now_utc(),
                    finished_at=now_utc(),
                    effective_interval="5m",
                )
                return
            raise exc
        except Exception as exc:
            LOGGER.exception("Historical candle backfill failed for %s %s.", symbol, interval)
            self._states[key] = _TaskState(
                status="failed",
                message=f"Historical {interval} backfill failed for {symbol}.",
                last_error=str(exc),
                started_at=self._states.get(key).started_at if key in self._states else now_utc(),
                finished_at=now_utc(),
                effective_interval=effective_interval,
            )
            return

        state = self.status(symbol=symbol, interval=interval, lookback_days=lookback_days)
        self._states[key] = _TaskState(
            status=state.status,
            message=state.message,
            started_at=self._states.get(key).started_at if key in self._states else now_utc(),
            finished_at=now_utc(),
            effective_interval=effective_interval,
        )

    async def _fetch_and_persist(
        self,
        *,
        symbol: str,
        interval: SupportedInterval,
        lookback_days: int,
    ) -> None:
        start_time, end_time = lookback_window(days=lookback_days)
        page_limit = 1000
        cursor_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)
        interval_ms = int(interval_to_timedelta(interval).total_seconds() * 1000)
        repository = StorageRepository(self._database_url)
        try:
            candle_repository = CandleRepository(repository)
            while cursor_ms < end_ms:
                rows = await self._rest_client.get_klines(
                    symbol=symbol,
                    interval=interval,
                    start_time_ms=cursor_ms,
                    end_time_ms=end_ms,
                    limit=page_limit,
                )
                if not rows:
                    break
                candles = [
                    parse_rest_kline(symbol, interval, row)
                    for row in rows
                    if int(row[6]) < int(now_utc().timestamp() * 1000)
                ]
                candle_repository.upsert(candles, source="historical_rest")
                last_open_ms = int(rows[-1][0])
                next_cursor = last_open_ms + interval_ms
                if next_cursor <= cursor_ms:
                    break
                cursor_ms = next_cursor
                if len(rows) < page_limit:
                    break
        finally:
            repository.close()


def _is_stale(status: CandleBackfillStatus) -> bool:
    if status.available_to is None:
        return True
    interval = status.effective_interval or status.requested_interval
    threshold = interval_to_timedelta(interval)
    if interval == "1m":
        threshold = max(threshold, interval_to_timedelta("5m"))
    return now_utc() - status.available_to > threshold
