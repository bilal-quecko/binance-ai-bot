import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from app.bot.runtime import PaperBotRuntime
from app.config import Settings
from app.exchange.binance_rest import BinanceRestClient
from app.exchange.symbol_service import SpotSymbolService
from app.market_data.candles import Candle
from app.market_data.models import MarketSnapshot
from app.paper.models import Position
from app.storage import StorageRepository


def _db_path(name: str) -> Path:
    base = Path("tests/.tmp_storage")
    base.mkdir(parents=True, exist_ok=True)
    return (base / f"{name}_{uuid4().hex}.sqlite").resolve()


@pytest.mark.asyncio
async def test_symbol_service_filters_trading_usdt_spot_symbols_and_searches() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == '/api/v3/exchangeInfo':
            return httpx.Response(
                200,
                json={
                    'timezone': 'UTC',
                    'serverTime': 1700000000999,
                    'symbols': [
                        {
                            'symbol': 'BTCUSDT',
                            'status': 'TRADING',
                            'baseAsset': 'BTC',
                            'quoteAsset': 'USDT',
                            'baseAssetPrecision': 8,
                            'quoteAssetPrecision': 8,
                            'orderTypes': ['LIMIT', 'MARKET'],
                            'permissions': [],
                            'permissionSets': [['SPOT']],
                            'isSpotTradingAllowed': True,
                            'filters': [],
                        },
                        {
                            'symbol': 'ETHUSDT',
                            'status': 'TRADING',
                            'baseAsset': 'ETH',
                            'quoteAsset': 'USDT',
                            'baseAssetPrecision': 8,
                            'quoteAssetPrecision': 8,
                            'orderTypes': ['LIMIT'],
                            'permissions': [],
                            'permissionSets': [['SPOT']],
                            'isSpotTradingAllowed': True,
                            'filters': [],
                        },
                        {
                            'symbol': 'BNBBTC',
                            'status': 'TRADING',
                            'baseAsset': 'BNB',
                            'quoteAsset': 'BTC',
                            'baseAssetPrecision': 8,
                            'quoteAssetPrecision': 8,
                            'orderTypes': ['LIMIT'],
                            'permissions': ['SPOT'],
                            'filters': [],
                        },
                        {
                            'symbol': 'ARBUSDT',
                            'status': 'TRADING',
                            'baseAsset': 'ARB',
                            'quoteAsset': 'USDT',
                            'baseAssetPrecision': 8,
                            'quoteAssetPrecision': 8,
                            'orderTypes': ['LIMIT'],
                            'permissions': [],
                            'permissionSets': [['SPOT', 'MARGIN']],
                            'isSpotTradingAllowed': True,
                            'filters': [],
                        },
                        {
                            'symbol': 'SOLUSDT',
                            'status': 'TRADING',
                            'baseAsset': 'SOL',
                            'quoteAsset': 'USDT',
                            'baseAssetPrecision': 8,
                            'quoteAssetPrecision': 8,
                            'orderTypes': ['LIMIT'],
                            'permissions': [],
                            'permissionSets': [['SPOT']],
                            'isSpotTradingAllowed': True,
                            'filters': [],
                        },
                        {
                            'symbol': 'TIAUSDT',
                            'status': 'TRADING',
                            'baseAsset': 'TIA',
                            'quoteAsset': 'USDT',
                            'baseAssetPrecision': 8,
                            'quoteAssetPrecision': 8,
                            'orderTypes': ['LIMIT'],
                            'permissions': [],
                            'permissionSets': [['SPOT']],
                            'isSpotTradingAllowed': True,
                            'filters': [],
                        },
                    ],
                },
            )
        if request.url.path == '/api/v3/ticker/24hr':
            return httpx.Response(
                200,
                json=[
                    {'symbol': 'SOLUSDT', 'quoteVolume': '5000'},
                    {'symbol': 'ETHUSDT', 'quoteVolume': '9000'},
                    {'symbol': 'BTCUSDT', 'quoteVolume': '15000'},
                    {'symbol': 'ARBUSDT', 'quoteVolume': '1000'},
                    {'symbol': 'TIAUSDT', 'quoteVolume': '3000'},
                ],
            )
        raise AssertionError(f'Unexpected path: {request.url.path}')

    settings = Settings(BINANCE_BASE_URL='https://api.binance.com')
    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(base_url=settings.binance_base_url, transport=transport) as http_client:
        client = BinanceRestClient(settings=settings, client=http_client)
        service = SpotSymbolService(client, cache_ttl_seconds=60)

        symbols = await service.list_symbols(refresh=True)
        top_symbols = await service.search_symbols(query='', limit=3)
        exact_search = await service.search_symbols(query='ETHUSDT', limit=10)
        lowercase_search = await service.search_symbols(query='ethusdt', limit=10)
        search = await service.search_symbols(query='btc', limit=10)
        prefix_search = await service.search_symbols(query='eth', limit=10)
        substring_search = await service.search_symbols(query='us', limit=10)

    prefix_then_substring = await service.search_symbols(query='t', limit=10)

    assert [symbol.symbol for symbol in symbols] == ['ARBUSDT', 'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'TIAUSDT']
    assert [symbol.symbol for symbol in top_symbols] == ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    assert [symbol.symbol for symbol in exact_search] == ['ETHUSDT']
    assert [symbol.symbol for symbol in lowercase_search] == ['ETHUSDT']
    assert [symbol.symbol for symbol in search] == ['BTCUSDT']
    assert [symbol.symbol for symbol in prefix_search] == ['ETHUSDT']
    assert [symbol.symbol for symbol in substring_search] == ['ARBUSDT', 'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'TIAUSDT']
    assert prefix_then_substring[0].symbol == 'TIAUSDT'
    assert any(symbol.symbol == 'BTCUSDT' for symbol in prefix_then_substring[1:])


@pytest.mark.asyncio
async def test_symbol_service_falls_back_to_deterministic_active_list_when_ticker_fails() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == '/api/v3/exchangeInfo':
            return httpx.Response(
                200,
                json={
                    'timezone': 'UTC',
                    'serverTime': 1700000000999,
                    'symbols': [
                        {
                            'symbol': 'DOGEUSDT',
                            'status': 'TRADING',
                            'baseAsset': 'DOGE',
                            'quoteAsset': 'USDT',
                            'baseAssetPrecision': 8,
                            'quoteAssetPrecision': 8,
                            'orderTypes': ['LIMIT'],
                            'permissions': [],
                            'permissionSets': [['SPOT']],
                            'isSpotTradingAllowed': True,
                            'filters': [],
                        },
                        {
                            'symbol': 'BTCUSDT',
                            'status': 'TRADING',
                            'baseAsset': 'BTC',
                            'quoteAsset': 'USDT',
                            'baseAssetPrecision': 8,
                            'quoteAssetPrecision': 8,
                            'orderTypes': ['LIMIT'],
                            'permissions': [],
                            'permissionSets': [['SPOT']],
                            'isSpotTradingAllowed': True,
                            'filters': [],
                        },
                        {
                            'symbol': 'XRPUSDT',
                            'status': 'TRADING',
                            'baseAsset': 'XRP',
                            'quoteAsset': 'USDT',
                            'baseAssetPrecision': 8,
                            'quoteAssetPrecision': 8,
                            'orderTypes': ['LIMIT'],
                            'permissions': [],
                            'permissionSets': [['SPOT']],
                            'isSpotTradingAllowed': True,
                            'filters': [],
                        },
                    ],
                },
            )
        if request.url.path == '/api/v3/ticker/24hr':
            return httpx.Response(503, json={'code': -1000, 'msg': 'temporary failure'})
        raise AssertionError(f'Unexpected path: {request.url.path}')

    settings = Settings(BINANCE_BASE_URL='https://api.binance.com')
    transport = httpx.MockTransport(handler)

    async with httpx.AsyncClient(base_url=settings.binance_base_url, transport=transport) as http_client:
        client = BinanceRestClient(settings=settings, client=http_client)
        service = SpotSymbolService(client, cache_ttl_seconds=60)
        top_symbols = await service.search_symbols(query='', limit=3)

    assert [symbol.symbol for symbol in top_symbols] == ['BTCUSDT', 'XRPUSDT', 'DOGEUSDT']


class FakeRunner:
    def __init__(self) -> None:
        self.ingested: list[MarketSnapshot] = []
        self.processed: list[MarketSnapshot] = []

    def ingest_snapshot(self, snapshot: MarketSnapshot) -> None:
        self.ingested.append(snapshot)

    def process_snapshot(self, snapshot: MarketSnapshot) -> None:
        self.processed.append(snapshot)

    def get_balances(self) -> dict[str, Decimal]:
        return {"USDT": Decimal("10000")}

    def get_open_positions(self) -> dict[str, Position]:
        return {}

    def realized_pnl(self) -> Decimal:
        return Decimal("0")


class FakeStreamManager:
    def __init__(self, snapshots: list[MarketSnapshot]) -> None:
        self._snapshots = snapshots
        self.streams_seen: list[list[str]] = []

    async def stream(self, streams: list[str], *, websocket_client=None):
        self.streams_seen.append(list(streams))
        for snapshot in self._snapshots:
            yield snapshot


@pytest.mark.asyncio
async def test_paper_bot_runtime_ingests_live_snapshots_and_processes_closed_candles() -> None:
    closed_time = datetime(2024, 3, 9, 16, 0, 59, tzinfo=UTC)
    candle = Candle(
        symbol='BTCUSDT',
        timeframe='1m',
        open=Decimal('100'),
        high=Decimal('101'),
        low=Decimal('99'),
        close=Decimal('100.5'),
        volume=Decimal('10'),
        quote_volume=Decimal('1005'),
        open_time=datetime(2024, 3, 9, 16, 0, 0, tzinfo=UTC),
        close_time=closed_time,
        event_time=closed_time,
        trade_count=42,
        is_closed=True,
    )
    trade_snapshot = MarketSnapshot(
        symbol='BTCUSDT',
        last_price=Decimal('100.2'),
        event_time=closed_time,
        received_at=closed_time,
    )
    candle_snapshot = MarketSnapshot(
        symbol='BTCUSDT',
        candle=candle,
        last_price=Decimal('100.5'),
        event_time=closed_time,
        received_at=closed_time,
    )

    fake_runner = FakeRunner()
    stream_manager = FakeStreamManager([trade_snapshot, candle_snapshot])
    db_path = _db_path("runtime_ingest")
    runtime = PaperBotRuntime(
        settings=Settings(APP_MODE='paper', DATABASE_URL=f"sqlite:///{db_path}"),
        websocket_client=object(),
        stream_manager=stream_manager,
    )
    runtime._build_runner = lambda: fake_runner  # type: ignore[method-assign]

    status = await runtime.start('BTCUSDT')
    await asyncio.sleep(0)
    await runtime.stop()

    assert status.state == 'running'
    assert stream_manager.streams_seen == [['btcusdt@kline_1m', 'btcusdt@bookTicker', 'btcusdt@aggTrade']]
    assert len(fake_runner.ingested) == 2
    assert len(fake_runner.processed) == 1
    assert fake_runner.processed[0].candle is not None


@pytest.mark.asyncio
async def test_paper_bot_runtime_ignores_duplicate_and_out_of_order_closed_klines() -> None:
    first_candle = Candle(
        symbol='BTCUSDT',
        timeframe='1m',
        open=Decimal('100'),
        high=Decimal('101'),
        low=Decimal('99'),
        close=Decimal('100.5'),
        volume=Decimal('10'),
        quote_volume=Decimal('1005'),
        open_time=datetime(2024, 3, 9, 16, 0, 0, tzinfo=UTC),
        close_time=datetime(2024, 3, 9, 16, 0, 59, 999000, tzinfo=UTC),
        event_time=datetime(2024, 3, 9, 16, 0, 59, 999000, tzinfo=UTC),
        trade_count=10,
        is_closed=True,
    )
    duplicate_first_candle = Candle(
        symbol='BTCUSDT',
        timeframe='1m',
        open=Decimal('100'),
        high=Decimal('101'),
        low=Decimal('99'),
        close=Decimal('100.6'),
        volume=Decimal('12'),
        quote_volume=Decimal('1207.2'),
        open_time=first_candle.open_time,
        close_time=first_candle.close_time,
        event_time=datetime(2024, 3, 9, 16, 1, 0, tzinfo=UTC),
        trade_count=12,
        is_closed=True,
    )
    second_candle = Candle(
        symbol='BTCUSDT',
        timeframe='1m',
        open=Decimal('101'),
        high=Decimal('102'),
        low=Decimal('100'),
        close=Decimal('101.5'),
        volume=Decimal('11'),
        quote_volume=Decimal('1116.5'),
        open_time=datetime(2024, 3, 9, 16, 1, 0, tzinfo=UTC),
        close_time=datetime(2024, 3, 9, 16, 1, 59, 999000, tzinfo=UTC),
        event_time=datetime(2024, 3, 9, 16, 1, 59, 999000, tzinfo=UTC),
        trade_count=11,
        is_closed=True,
    )
    stale_first_candle = Candle(
        symbol='BTCUSDT',
        timeframe='1m',
        open=Decimal('100'),
        high=Decimal('101'),
        low=Decimal('99'),
        close=Decimal('100.4'),
        volume=Decimal('9'),
        quote_volume=Decimal('903.6'),
        open_time=first_candle.open_time,
        close_time=first_candle.close_time,
        event_time=datetime(2024, 3, 9, 16, 0, 58, tzinfo=UTC),
        trade_count=9,
        is_closed=True,
    )

    snapshots = [
        MarketSnapshot(symbol='BTCUSDT', candle=first_candle, event_time=first_candle.event_time, received_at=first_candle.event_time),
        MarketSnapshot(symbol='BTCUSDT', candle=duplicate_first_candle, event_time=duplicate_first_candle.event_time, received_at=duplicate_first_candle.event_time),
        MarketSnapshot(symbol='BTCUSDT', candle=second_candle, event_time=second_candle.event_time, received_at=second_candle.event_time),
        MarketSnapshot(symbol='BTCUSDT', candle=stale_first_candle, event_time=stale_first_candle.event_time, received_at=stale_first_candle.event_time),
    ]

    fake_runner = FakeRunner()
    stream_manager = FakeStreamManager(snapshots)
    settings = Settings(APP_MODE='paper', DATABASE_URL=f"sqlite:///{_db_path('runtime_ordering')}")
    runtime = PaperBotRuntime(settings=settings, websocket_client=None, stream_manager=stream_manager)  # type: ignore[arg-type]
    runtime._build_runner = lambda: fake_runner  # type: ignore[method-assign]

    await runtime.start('BTCUSDT')
    await asyncio.sleep(0)
    await runtime.stop()

    assert len(fake_runner.ingested) == 4
    assert len(fake_runner.processed) == 2
    assert [snapshot.candle.open_time for snapshot in fake_runner.processed if snapshot.candle is not None] == [
        first_candle.open_time,
        second_candle.open_time,
    ]


def test_paper_bot_runtime_recovers_session_and_broker_state_as_safe_pause() -> None:
    db_path = _db_path("runtime_recovery")
    settings = Settings(APP_MODE="paper", DATABASE_URL=f"sqlite:///{db_path}")
    repository = StorageRepository(settings.database_url)
    try:
        repository.upsert_runtime_session_state(
            state="running",
            mode="auto_paper",
            symbol="BTCUSDT",
            session_id="recovered-session",
            started_at=datetime(2024, 3, 9, 16, 0, tzinfo=UTC),
            last_event_time=datetime(2024, 3, 9, 16, 5, tzinfo=UTC),
            last_error=None,
        )
        repository.upsert_paper_broker_state(
            balances={"USDT": Decimal("9950")},
            positions={
                "BTCUSDT": Position(
                    symbol="BTCUSDT",
                    quantity=Decimal("0.5"),
                    avg_entry_price=Decimal("100"),
                    realized_pnl=Decimal("12"),
                    quote_asset="USDT",
                )
            },
            realized_pnl=Decimal("12"),
            snapshot_time=datetime(2024, 3, 9, 16, 6, tzinfo=UTC),
        )
    finally:
        repository.close()

    runtime = PaperBotRuntime(settings=settings, websocket_client=None, stream_manager=FakeStreamManager([]))  # type: ignore[arg-type]

    status = runtime.status()
    workstation = runtime.workstation_state("BTCUSDT")

    assert status.state == "paused"
    assert status.mode == "paused"
    assert status.symbol == "BTCUSDT"
    assert status.session_id == "recovered-session"
    assert status.recovered_from_prior_session is True
    assert status.broker_state_restored is True
    assert status.recovery_message is not None

    assert workstation.is_runtime_symbol is True
    assert workstation.current_position is not None
    assert workstation.current_position.quantity == Decimal("0.5")
    assert workstation.current_position.avg_entry_price == Decimal("100")
    assert workstation.realized_pnl == Decimal("12")
    assert workstation.recovery_message == status.recovery_message


def test_paper_bot_runtime_ignores_corrupt_recovery_state_and_stays_safe() -> None:
    db_path = _db_path("runtime_recovery_corrupt")
    settings = Settings(APP_MODE="paper", DATABASE_URL=f"sqlite:///{db_path}")
    repository = StorageRepository(settings.database_url)
    try:
        repository.upsert_runtime_session_state(
            state="running",
            mode="auto_paper",
            symbol="BTCUSDT",
            session_id="recovered-session",
            started_at=datetime(2024, 3, 9, 16, 0, tzinfo=UTC),
            last_event_time=datetime(2024, 3, 9, 16, 5, tzinfo=UTC),
            last_error=None,
        )
        repository._connection.execute(  # noqa: SLF001 - targeted corrupt recovery coverage
            """
            INSERT INTO paper_broker_state (singleton_id, balances_json, realized_pnl, snapshot_time)
            VALUES (1, ?, ?, ?)
            """,
            ("not-json", "12", "2024-03-09T16:06:00+00:00"),
        )
        repository._connection.commit()
    finally:
        repository.close()

    runtime = PaperBotRuntime(settings=settings, websocket_client=None, stream_manager=FakeStreamManager([]))  # type: ignore[arg-type]

    status = runtime.status()
    workstation = runtime.workstation_state("BTCUSDT")

    assert status.state == "paused"
    assert status.mode == "paused"
    assert status.recovered_from_prior_session is True
    assert status.broker_state_restored is False
    assert workstation.current_position is None
