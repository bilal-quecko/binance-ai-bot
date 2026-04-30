from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from app.market_data.candles import Candle
from app.services.backfill_service import HistoricalBackfillService
from app.storage import StorageRepository


def _db_path(name: str) -> Path:
    base = Path('tests/.tmp_storage')
    base.mkdir(parents=True, exist_ok=True)
    return (base / f'{name}_{uuid4().hex}.sqlite').resolve()


class FakeRestClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, int | None, int | None, int]] = []

    async def get_klines(self, *, symbol: str, interval: str, start_time_ms: int | None = None, end_time_ms: int | None = None, limit: int = 1000):
        self.calls.append((symbol, interval, start_time_ms, end_time_ms, limit))
        assert start_time_ms is not None
        first_open = start_time_ms
        rows = []
        for index in range(3):
            open_time = first_open + (index * 60_000)
            close_time = open_time + 59_000
            rows.append([
                open_time,
                '100.0',
                '101.0',
                '99.5',
                '100.5',
                '10.0',
                close_time,
                '1005.0',
                20,
                '0',
                '0',
                '0',
            ])
        return rows if len(self.calls) == 1 else []


@pytest.mark.asyncio
async def test_historical_backfill_persists_and_deduplicates_candles() -> None:
    db_path = _db_path('history')
    database_url = f'sqlite:///{db_path}'
    service = HistoricalBackfillService(rest_client=FakeRestClient(), database_url=database_url)

    status = await service.ensure_recent_history(symbol='BTCUSDT', interval='1m', lookback_days=7, force=True)
    assert status.status in {'loading', 'partial', 'ready'}

    await service._tasks[('BTCUSDT', '1m', 7)]
    repository = StorageRepository(database_url)
    try:
        records = repository.get_historical_candles(symbol='BTCUSDT', interval='1m')
        assert len(records) == 3
        repository.upsert_historical_candles([
            Candle(
                symbol='BTCUSDT',
                timeframe='1m',
                open=records[0].open_price,
                high=records[0].high_price,
                low=records[0].low_price,
                close=records[0].close_price,
                volume=records[0].volume,
                quote_volume=records[0].quote_volume,
                open_time=records[0].open_time,
                close_time=records[0].close_time,
                event_time=records[0].created_at,
                trade_count=records[0].trade_count,
                is_closed=True,
            ),
        ], source='historical_rest')
        records_after = repository.get_historical_candles(symbol='BTCUSDT', interval='1m')
        assert len(records_after) == 3
    finally:
        repository.close()


def test_backfill_status_reports_partial_when_history_is_stale() -> None:
    db_path = _db_path('stale')
    database_url = f'sqlite:///{db_path}'
    repository = StorageRepository(database_url)
    stale_time = datetime.now(tz=UTC) - timedelta(days=2)
    try:
        repository.upsert_historical_candles([
            Candle(
                symbol='ETHUSDT',
                timeframe='1m',
                open=Decimal('10'),
                high=Decimal('10.5'),
                low=Decimal('9.8'),
                close=Decimal('10.2'),
                volume=Decimal('5'),
                quote_volume=Decimal('51'),
                open_time=stale_time,
                close_time=stale_time + timedelta(seconds=59),
                event_time=stale_time + timedelta(seconds=59),
                trade_count=10,
                is_closed=True,
            ),
        ], source='historical_rest')
    finally:
        repository.close()

    service = HistoricalBackfillService(rest_client=FakeRestClient(), database_url=database_url)
    status = service.status(symbol='ETHUSDT', interval='1m', lookback_days=7)
    assert status.status == 'partial'
    assert status.candle_count == 1
