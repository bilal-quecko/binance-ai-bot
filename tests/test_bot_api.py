from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.ai.models import AIFeatureVector, AISignalSnapshot
from fastapi.testclient import TestClient

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

    def storage_degraded(self) -> bool:
        return False

    def storage_status_message(self) -> str | None:
        return None

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


class NeutralRuntime(FakeRuntime):
    def workstation_state(self, symbol: str) -> WorkstationState:
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
            total_pnl=Decimal('0'),
            realized_pnl=Decimal('0'),
        )


class BrokenRuntime(NeutralRuntime):
    def workstation_state(self, symbol: str) -> WorkstationState:
        raise RuntimeError("simulated workstation failure")


class HistoryWaitingRuntime(FakeRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.state = BotStatus(state='running', symbol='BTCUSDT', timeframe='1m', started_at=datetime(2024, 3, 9, 16, 0, tzinfo=UTC))

    def workstation_state(self, symbol: str) -> WorkstationState:
        return WorkstationState(
            symbol=symbol,
            is_runtime_symbol=True,
            market_snapshot=MarketSnapshot(
                symbol=symbol,
                candle=None,
                top_of_book=None,
                last_price=Decimal('100.5'),
                event_time=datetime(2024, 3, 9, 16, 2, tzinfo=UTC),
                received_at=datetime(2024, 3, 9, 16, 2, tzinfo=UTC),
            ),
            feature_snapshot=None,
            ai_signal=None,
            entry_signal=None,
            exit_signal=None,
            current_position=None,
            last_cycle_result=None,
            total_pnl=Decimal('0'),
            realized_pnl=Decimal('0'),
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
    repository.insert_ai_signal_snapshot(
        AISignalSnapshot(
            symbol='BTCUSDT',
            bias='bullish',
            confidence=68,
            entry_signal=True,
            exit_signal=False,
            suggested_action='enter',
            explanation='Momentum is constructive.',
            feature_vector=AIFeatureVector(
                symbol='BTCUSDT',
                timestamp=datetime(2024, 3, 9, 15, 59, tzinfo=UTC),
                candle_count=4,
                close_price=Decimal('100'),
                ema_fast=Decimal('101'),
                ema_slow=Decimal('100'),
                rsi=Decimal('60'),
                atr=Decimal('1'),
                volatility_pct=Decimal('0.01'),
                momentum=Decimal('0.01'),
                recent_returns=(Decimal('0.01'),),
                wick_body_ratio=Decimal('1'),
                upper_wick_ratio=Decimal('0.2'),
                lower_wick_ratio=Decimal('0.1'),
                volume_change_pct=Decimal('0.2'),
                volume_spike_ratio=Decimal('1.1'),
                spread_ratio=Decimal('0.001'),
                order_book_imbalance=Decimal('0.2'),
                microstructure_healthy=True,
            ),
        )
    )
    repository.insert_market_candle_snapshot(
        Candle(
            symbol='BTCUSDT',
            timeframe='1m',
            open=Decimal('100'),
            high=Decimal('101'),
            low=Decimal('99'),
            close=Decimal('101'),
            volume=Decimal('10'),
            quote_volume=Decimal('1010'),
            open_time=datetime(2024, 3, 9, 16, 4, 0, 1000, tzinfo=UTC),
            close_time=datetime(2024, 3, 9, 16, 5, tzinfo=UTC),
            event_time=datetime(2024, 3, 9, 16, 5, tzinfo=UTC),
            trade_count=10,
            is_closed=True,
        )
    )
    repository.insert_ai_signal_snapshot(
        AISignalSnapshot(
            symbol='BTCUSDT',
            bias='sideways',
            confidence=55,
            entry_signal=False,
            exit_signal=False,
            suggested_action='wait',
            explanation='Confirmation is still missing.',
            feature_vector=AIFeatureVector(
                symbol='BTCUSDT',
                timestamp=datetime(2024, 3, 9, 16, 1, tzinfo=UTC),
                candle_count=5,
                close_price=Decimal('100.5'),
                ema_fast=Decimal('100.4'),
                ema_slow=Decimal('100.3'),
                rsi=Decimal('52'),
                atr=Decimal('1'),
                volatility_pct=Decimal('0.01'),
                momentum=Decimal('0.005'),
                recent_returns=(Decimal('0.002'),),
                wick_body_ratio=Decimal('1'),
                upper_wick_ratio=Decimal('0.2'),
                lower_wick_ratio=Decimal('0.1'),
                volume_change_pct=Decimal('0.1'),
                volume_spike_ratio=Decimal('1.0'),
                spread_ratio=Decimal('0.001'),
                order_book_imbalance=Decimal('0.1'),
                microstructure_healthy=True,
            ),
        )
    )
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
        ai_history_response = client.get('/bot/ai-signal/history', params={'symbol': 'BTCUSDT', 'limit': 10, 'offset': 0})
        ai_evaluation_response = client.get('/bot/ai-signal/evaluation', params={'symbol': 'BTCUSDT'})
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
    assert workstation_response.json()['data_state'] == 'ready'
    assert workstation_response.json()['entry_signal']['side'] == 'BUY'
    assert workstation_response.json()['ai_signal']['bias'] == 'bullish'

    assert ai_signal_response.status_code == 200
    assert ai_signal_response.json()['confidence'] == 72
    assert ai_signal_response.json()['timestamp'] == '2024-03-09T16:02:00Z'
    assert ai_signal_response.json()['features']['candle_count'] == 5

    assert ai_history_response.status_code == 200
    assert ai_history_response.json()['total'] == 2
    assert ai_history_response.json()['data_state'] == 'ready'
    assert ai_history_response.json()['items'][0]['bias'] == 'sideways'
    assert ai_history_response.json()['items'][1]['symbol'] == 'BTCUSDT'

    assert ai_evaluation_response.status_code == 200
    assert ai_evaluation_response.json()['symbol'] == 'BTCUSDT'
    assert ai_evaluation_response.json()['data_state'] == 'ready'
    assert ai_evaluation_response.json()['horizons'][0]['horizon'] == '5m'
    assert 'directional_accuracy_pct' in ai_evaluation_response.json()['horizons'][0]

    assert pause_response.status_code == 200
    assert pause_response.json()['state'] == 'paused'

    assert resume_response.status_code == 200
    assert resume_response.json()['state'] == 'running'

    assert reset_response.status_code == 200
    assert reset_response.json()['state'] == 'stopped'
    assert fake_runtime.reset_called is True

    assert stop_response.status_code == 200
    assert stop_response.json()['state'] == 'stopped'


def test_workstation_endpoints_return_empty_states_without_runtime_data() -> None:
    db_path = _db_path()
    settings = Settings(DATABASE_URL=f"sqlite:///{db_path}")
    fake_symbol_service = FakeSymbolService()
    neutral_runtime = NeutralRuntime()
    app.dependency_overrides[get_symbol_service] = lambda: fake_symbol_service
    app.dependency_overrides[get_bot_runtime] = lambda: neutral_runtime
    app.dependency_overrides[get_settings_dependency] = lambda: settings
    client = TestClient(app)

    try:
        workstation_response = client.get('/bot/workstation', params={'symbol': 'ETHUSDT'})
        ai_signal_response = client.get('/bot/ai-signal', params={'symbol': 'ETHUSDT'})
        ai_history_response = client.get('/bot/ai-signal/history', params={'symbol': 'ETHUSDT', 'limit': 10, 'offset': 0})
        ai_evaluation_response = client.get('/bot/ai-signal/evaluation', params={'symbol': 'ETHUSDT'})
    finally:
        app.dependency_overrides.clear()

    assert workstation_response.status_code == 200
    assert workstation_response.json() == {
        'symbol': 'ETHUSDT',
        'data_state': 'waiting_for_runtime',
        'status_message': 'Start or attach the live runtime for ETHUSDT to populate symbol-scoped workstation data.',
        'is_runtime_symbol': False,
        'runtime_status': {
            'state': 'stopped',
            'symbol': None,
            'timeframe': '1m',
            'paper_only': True,
            'started_at': None,
            'last_event_time': None,
            'last_error': None,
        },
        'last_price': None,
        'current_candle': None,
        'top_of_book': None,
        'feature': None,
        'ai_signal': None,
        'trend_bias': None,
        'entry_signal': None,
        'exit_signal': None,
        'explanation': None,
        'current_position': None,
        'last_action': None,
        'last_market_event': None,
        'total_pnl': '0',
        'realized_pnl': '0',
    }
    assert ai_signal_response.status_code == 200
    assert ai_signal_response.json() is None
    assert ai_history_response.status_code == 200
    assert ai_history_response.json() == {
        'items': [],
        'total': 0,
        'limit': 10,
        'offset': 0,
        'data_state': 'waiting_for_runtime',
        'status_message': 'Start the runtime for ETHUSDT to generate persisted AI history.',
    }
    assert ai_evaluation_response.status_code == 200
    assert ai_evaluation_response.json()['data_state'] == 'waiting_for_runtime'
    assert [item['sample_size'] for item in ai_evaluation_response.json()['horizons']] == [0, 0, 0]
    assert ai_evaluation_response.json()['recent_samples'] == []


def test_workstation_endpoint_does_not_crash_when_runtime_state_errors() -> None:
    db_path = _db_path()
    settings = Settings(DATABASE_URL=f"sqlite:///{db_path}")
    app.dependency_overrides[get_symbol_service] = lambda: FakeSymbolService()
    app.dependency_overrides[get_bot_runtime] = lambda: BrokenRuntime()
    app.dependency_overrides[get_settings_dependency] = lambda: settings
    client = TestClient(app)

    try:
        workstation_response = client.get('/bot/workstation', params={'symbol': 'BTCUSDT'})
        ai_signal_response = client.get('/bot/ai-signal', params={'symbol': 'BTCUSDT'})
    finally:
        app.dependency_overrides.clear()

    assert workstation_response.status_code == 200
    assert workstation_response.json()['data_state'] == 'degraded_storage'
    assert workstation_response.json()['is_runtime_symbol'] is False
    assert ai_signal_response.status_code == 200
    assert ai_signal_response.json() is None


def test_workstation_reports_waiting_for_history_when_runtime_is_live_but_features_are_missing() -> None:
    db_path = _db_path()
    settings = Settings(DATABASE_URL=f"sqlite:///{db_path}")
    app.dependency_overrides[get_symbol_service] = lambda: FakeSymbolService()
    app.dependency_overrides[get_bot_runtime] = lambda: HistoryWaitingRuntime()
    app.dependency_overrides[get_settings_dependency] = lambda: settings
    client = TestClient(app)

    try:
        workstation_response = client.get('/bot/workstation', params={'symbol': 'BTCUSDT'})
        ai_history_response = client.get('/bot/ai-signal/history', params={'symbol': 'BTCUSDT', 'limit': 5, 'offset': 0})
        ai_evaluation_response = client.get('/bot/ai-signal/evaluation', params={'symbol': 'BTCUSDT'})
    finally:
        app.dependency_overrides.clear()

    assert workstation_response.status_code == 200
    assert workstation_response.json()['data_state'] == 'waiting_for_history'
    assert ai_history_response.status_code == 200
    assert ai_history_response.json()['data_state'] == 'waiting_for_history'
    assert ai_evaluation_response.status_code == 200
    assert ai_evaluation_response.json()['data_state'] == 'waiting_for_history'


def test_reset_session_followed_by_workstation_read_stays_safe() -> None:
    db_path = _db_path()
    settings = Settings(DATABASE_URL=f"sqlite:///{db_path}")
    fake_runtime = NeutralRuntime()
    app.dependency_overrides[get_symbol_service] = lambda: FakeSymbolService()
    app.dependency_overrides[get_bot_runtime] = lambda: fake_runtime
    app.dependency_overrides[get_settings_dependency] = lambda: settings
    client = TestClient(app)

    try:
        reset_response = client.post('/bot/reset')
        workstation_response = client.get('/bot/workstation', params={'symbol': 'BTCUSDT'})
        ai_history_response = client.get('/bot/ai-signal/history', params={'symbol': 'BTCUSDT', 'limit': 5, 'offset': 0})
    finally:
        app.dependency_overrides.clear()

    assert reset_response.status_code == 200
    assert workstation_response.status_code == 200
    assert workstation_response.json()['data_state'] == 'waiting_for_runtime'
    assert workstation_response.json()['is_runtime_symbol'] is False
    assert ai_history_response.status_code == 200
    assert ai_history_response.json()['items'] == []


def test_ai_evaluation_returns_empty_metrics_when_no_candle_history_exists() -> None:
    db_path = _db_path()
    settings = Settings(DATABASE_URL=f"sqlite:///{db_path}")
    repository = StorageRepository(settings.database_url)
    try:
        repository.insert_ai_signal_snapshot(
            AISignalSnapshot(
                symbol='BTCUSDT',
                bias='bullish',
                confidence=70,
                entry_signal=True,
                exit_signal=False,
                suggested_action='enter',
                explanation='Momentum is improving.',
                feature_vector=AIFeatureVector(
                    symbol='BTCUSDT',
                    timestamp=datetime(2024, 3, 9, 16, 0, tzinfo=UTC),
                    candle_count=5,
                    close_price=Decimal('100'),
                    ema_fast=Decimal('101'),
                    ema_slow=Decimal('100'),
                    rsi=Decimal('60'),
                    atr=Decimal('1'),
                    volatility_pct=Decimal('0.01'),
                    momentum=Decimal('0.02'),
                    recent_returns=(Decimal('0.01'),),
                    wick_body_ratio=Decimal('1'),
                    upper_wick_ratio=Decimal('0.2'),
                    lower_wick_ratio=Decimal('0.1'),
                    volume_change_pct=Decimal('0.2'),
                    volume_spike_ratio=Decimal('1.1'),
                    spread_ratio=Decimal('0.001'),
                    order_book_imbalance=Decimal('0.2'),
                    microstructure_healthy=True,
                ),
            )
        )
    finally:
        repository.close()

    app.dependency_overrides[get_symbol_service] = lambda: FakeSymbolService()
    app.dependency_overrides[get_bot_runtime] = lambda: NeutralRuntime()
    app.dependency_overrides[get_settings_dependency] = lambda: settings
    client = TestClient(app)

    try:
        response = client.get('/bot/ai-signal/evaluation', params={'symbol': 'BTCUSDT'})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()['data_state'] == 'waiting_for_runtime'
    assert [item['sample_size'] for item in response.json()['horizons']] == [0, 0, 0]
    assert response.json()['recent_samples'] == []


def test_ai_history_and_evaluation_report_degraded_storage_when_repository_open_fails(monkeypatch) -> None:
    db_path = _db_path()
    settings = Settings(DATABASE_URL=f"sqlite:///{db_path}")

    def raise_storage_error(*args, **kwargs):
        raise RuntimeError('simulated storage open failure')

    monkeypatch.setattr('app.api.bot_api.StorageRepository', raise_storage_error)
    app.dependency_overrides[get_symbol_service] = lambda: FakeSymbolService()
    app.dependency_overrides[get_bot_runtime] = lambda: NeutralRuntime()
    app.dependency_overrides[get_settings_dependency] = lambda: settings
    client = TestClient(app)

    try:
        ai_history_response = client.get('/bot/ai-signal/history', params={'symbol': 'BTCUSDT', 'limit': 5, 'offset': 0})
        ai_evaluation_response = client.get('/bot/ai-signal/evaluation', params={'symbol': 'BTCUSDT'})
    finally:
        app.dependency_overrides.clear()

    assert ai_history_response.status_code == 200
    assert ai_history_response.json()['data_state'] == 'degraded_storage'
    assert ai_evaluation_response.status_code == 200
    assert ai_evaluation_response.json()['data_state'] == 'degraded_storage'


def test_workstation_endpoints_tolerate_old_sqlite_schema() -> None:
    db_path = _db_path()
    repository = StorageRepository(f"sqlite:///{db_path}")
    try:
        repository._connection.execute("DROP TABLE ai_signal_snapshots")
        repository._connection.execute("DROP TABLE market_candle_snapshots")
        repository._connection.execute(
            """
            CREATE TABLE ai_signal_snapshots (
                symbol TEXT NOT NULL,
                snapshot_time TEXT NOT NULL,
                bias TEXT NOT NULL,
                confidence INTEGER NOT NULL,
                entry_signal INTEGER NOT NULL,
                exit_signal INTEGER NOT NULL,
                suggested_action TEXT NOT NULL,
                explanation TEXT NOT NULL
            )
            """
        )
        repository._connection.execute(
            """
            CREATE TABLE market_candle_snapshots (
                symbol TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                open_time TEXT NOT NULL,
                close_price TEXT NOT NULL
            )
            """
        )
        repository._connection.commit()
    finally:
        repository.close()

    settings = Settings(DATABASE_URL=f"sqlite:///{db_path}")
    app.dependency_overrides[get_symbol_service] = lambda: FakeSymbolService()
    app.dependency_overrides[get_bot_runtime] = lambda: NeutralRuntime()
    app.dependency_overrides[get_settings_dependency] = lambda: settings
    client = TestClient(app)

    try:
        ai_signal_response = client.get('/bot/ai-signal', params={'symbol': 'BTCUSDT'})
        ai_history_response = client.get('/bot/ai-signal/history', params={'symbol': 'BTCUSDT', 'limit': 5, 'offset': 0})
        ai_evaluation_response = client.get('/bot/ai-signal/evaluation', params={'symbol': 'BTCUSDT'})
    finally:
        app.dependency_overrides.clear()

    assert ai_signal_response.status_code == 200
    assert ai_signal_response.json() is None
    assert ai_history_response.status_code == 200
    assert ai_history_response.json()['data_state'] == 'waiting_for_runtime'
    assert ai_history_response.json()['items'] == []
    assert ai_evaluation_response.status_code == 200
    assert ai_evaluation_response.json()['data_state'] == 'waiting_for_runtime'
    assert all(item['sample_size'] == 0 for item in ai_evaluation_response.json()['horizons'])
