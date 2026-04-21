from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.ai.models import AIFeatureVector, AISignalSnapshot
from app.api.bot_api import get_bot_runtime, get_settings_dependency, get_symbol_service
from app.bot import BotStatus, WorkstationState
from app.config import Settings
from app.exchange.symbol_service import SpotSymbolRecord
from app.features.models import FeatureSnapshot
from app.main import app
from app.market_data.candles import Candle
from app.market_data.models import MarketSnapshot
from app.market_data.orderbook import TopOfBook
from app.paper.models import Position
from app.storage import StorageRepository
from app.strategies.models import StrategySignal


class FakeSymbolService:
    async def search_symbols(self, *, query: str = '', limit: int = 20):
        self.last_query = query
        self.last_limit = limit
        records = [
            SpotSymbolRecord(symbol='BTCUSDT', base_asset='BTC', quote_asset='USDT', status='TRADING'),
            SpotSymbolRecord(symbol='ETHUSDT', base_asset='ETH', quote_asset='USDT', status='TRADING'),
        ]
        if not query:
            return records[:limit]
        return [record for record in records if query.upper() in record.symbol][:limit]


class FakeRuntime:
    def __init__(self) -> None:
        self.state = BotStatus(state='stopped', timeframe='1m')
        self.reset_called = False

    def status(self) -> BotStatus:
        return self.state

    async def start(self, symbol: str) -> BotStatus:
        self.state = BotStatus(state='running', symbol=symbol, timeframe='1m', started_at=datetime(2024, 3, 9, 16, 0, tzinfo=UTC))
        return self.state

    async def stop(self) -> BotStatus:
        self.state = BotStatus(state='stopped', symbol=self.state.symbol, timeframe='1m')
        return self.state

    async def pause(self) -> BotStatus:
        self.state = BotStatus(state='paused', symbol=self.state.symbol, timeframe='1m')
        return self.state

    async def resume(self) -> BotStatus:
        self.state = BotStatus(state='running', symbol=self.state.symbol, timeframe='1m')
        return self.state

    async def reset_session(self) -> BotStatus:
        self.reset_called = True
        self.state = BotStatus(state='stopped', timeframe='1m')
        return self.state

    def workstation_state(self, symbol: str) -> WorkstationState:
        snapshot_time = datetime(2024, 3, 9, 16, 2, tzinfo=UTC)
        candle = Candle(
            symbol=symbol,
            timeframe='1m',
            open=Decimal('100'),
            high=Decimal('101'),
            low=Decimal('99'),
            close=Decimal('100.5'),
            volume=Decimal('10'),
            quote_volume=Decimal('1005'),
            open_time=datetime(2024, 3, 9, 16, 1, tzinfo=UTC),
            close_time=datetime(2024, 3, 9, 16, 1, 59, 999000, tzinfo=UTC),
            event_time=snapshot_time,
            trade_count=10,
            is_closed=True,
        )
        top_of_book = TopOfBook(
            symbol=symbol,
            bid_price=Decimal('100.4'),
            bid_quantity=Decimal('2'),
            ask_price=Decimal('100.6'),
            ask_quantity=Decimal('3'),
            event_time=snapshot_time,
        )
        return WorkstationState(
            symbol=symbol,
            is_runtime_symbol=True,
            market_snapshot=MarketSnapshot(
                symbol=symbol,
                candle=candle,
                top_of_book=top_of_book,
                last_price=Decimal('100.5'),
                event_time=snapshot_time,
                received_at=snapshot_time,
            ),
            feature_snapshot=FeatureSnapshot(
                symbol=symbol,
                timestamp=snapshot_time,
                ema_fast=Decimal('101'),
                ema_slow=Decimal('100'),
                atr=Decimal('1'),
                mid_price=Decimal('100.5'),
                bid_ask_spread=Decimal('0.2'),
                order_book_imbalance=Decimal('0.2'),
                regime='bullish',
            ),
            ai_signal=AISignalSnapshot(
                symbol=symbol,
                bias='bullish',
                confidence=72,
                entry_signal=True,
                exit_signal=False,
                suggested_action='enter',
                explanation='Fast EMA is above slow EMA and momentum is improving.',
                feature_vector=AIFeatureVector(
                    symbol=symbol,
                    timestamp=snapshot_time,
                    candle_count=5,
                    close_price=Decimal('100.5'),
                    ema_fast=Decimal('101'),
                    ema_slow=Decimal('100'),
                    rsi=Decimal('61'),
                    atr=Decimal('1'),
                    volatility_pct=Decimal('0.01'),
                    momentum=Decimal('0.02'),
                    recent_returns=(Decimal('0.01'), Decimal('0.01')),
                    wick_body_ratio=Decimal('1'),
                    upper_wick_ratio=Decimal('0.2'),
                    lower_wick_ratio=Decimal('0.1'),
                    volume_change_pct=Decimal('0.4'),
                    volume_spike_ratio=Decimal('1.4'),
                    spread_ratio=Decimal('0.001'),
                    order_book_imbalance=Decimal('0.2'),
                    microstructure_healthy=True,
                ),
            ),
            entry_signal=StrategySignal(symbol=symbol, side='BUY', confidence=Decimal('0.6'), reason_codes=('EMA_BULLISH',)),
            exit_signal=StrategySignal(symbol=symbol, side='HOLD', confidence=Decimal('1.0'), reason_codes=('POSITION_OPEN',)),
            current_position=Position(symbol=symbol, quantity=Decimal('1'), avg_entry_price=Decimal('99'), realized_pnl=Decimal('2')),
            last_cycle_result=None,
            total_pnl=Decimal('3'),
            realized_pnl=Decimal('2'),
        )


def _db_path() -> Path:
    base = Path("tests/.tmp_storage")
    base.mkdir(parents=True, exist_ok=True)
    return (base / f"bot_api_{uuid4().hex}.sqlite").resolve()


def test_symbol_and_bot_control_endpoints() -> None:
    db_path = _db_path()
    settings = Settings(DATABASE_URL=f"sqlite:///{db_path}")
    repository = StorageRepository(settings.database_url)
    repository.clear_all()
    repository.close()

    fake_symbol_service = FakeSymbolService()
    fake_runtime = FakeRuntime()
    app.dependency_overrides[get_symbol_service] = lambda: fake_symbol_service
    app.dependency_overrides[get_bot_runtime] = lambda: fake_runtime
    app.dependency_overrides[get_settings_dependency] = lambda: settings
    client = TestClient(app)

    try:
        top_symbols_response = client.get('/symbols')
        symbols_response = client.get('/symbols', params={'query': 'btc', 'limit': 5})
        start_response = client.post('/bot/start', json={'symbol': 'BTCUSDT'})
        status_response = client.get('/bot/status')
        workstation_response = client.get('/bot/workstation', params={'symbol': 'BTCUSDT'})
        ai_signal_response = client.get('/bot/ai-signal', params={'symbol': 'BTCUSDT'})
        pause_response = client.post('/bot/pause')
        resume_response = client.post('/bot/resume')
        reset_response = client.post('/bot/reset')
        stop_response = client.post('/bot/stop')
    finally:
        app.dependency_overrides.clear()

    assert top_symbols_response.status_code == 200
    assert len(top_symbols_response.json()) == 2
    assert fake_symbol_service.last_query == 'btc'
    assert fake_symbol_service.last_limit == 5

    assert symbols_response.status_code == 200
    assert symbols_response.json() == [
        {
            'symbol': 'BTCUSDT',
            'base_asset': 'BTC',
            'quote_asset': 'USDT',
            'status': 'TRADING',
        }
    ]

    assert start_response.status_code == 200
    assert start_response.json()['state'] == 'running'
    assert start_response.json()['symbol'] == 'BTCUSDT'

    assert status_response.status_code == 200
    assert status_response.json()['state'] == 'running'

    assert workstation_response.status_code == 200
    assert workstation_response.json()['symbol'] == 'BTCUSDT'
    assert workstation_response.json()['entry_signal']['side'] == 'BUY'
    assert workstation_response.json()['ai_signal']['bias'] == 'bullish'

    assert ai_signal_response.status_code == 200
    assert ai_signal_response.json()['confidence'] == 72
    assert ai_signal_response.json()['features']['candle_count'] == 5

    assert pause_response.status_code == 200
    assert pause_response.json()['state'] == 'paused'

    assert resume_response.status_code == 200
    assert resume_response.json()['state'] == 'running'

    assert reset_response.status_code == 200
    assert reset_response.json()['state'] == 'stopped'
    assert fake_runtime.reset_called is True

    assert stop_response.status_code == 200
    assert stop_response.json()['state'] == 'stopped'
