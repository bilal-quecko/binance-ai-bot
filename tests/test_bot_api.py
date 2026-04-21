from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.bot_api import get_bot_runtime, get_symbol_service
from app.bot import BotStatus
from app.exchange.symbol_service import SpotSymbolRecord
from app.main import app


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


def test_symbol_and_bot_control_endpoints() -> None:
    fake_symbol_service = FakeSymbolService()
    fake_runtime = FakeRuntime()
    app.dependency_overrides[get_symbol_service] = lambda: fake_symbol_service
    app.dependency_overrides[get_bot_runtime] = lambda: fake_runtime
    client = TestClient(app)

    try:
        top_symbols_response = client.get('/symbols')
        symbols_response = client.get('/symbols', params={'query': 'btc', 'limit': 5})
        start_response = client.post('/bot/start', json={'symbol': 'BTCUSDT'})
        status_response = client.get('/bot/status')
        pause_response = client.post('/bot/pause')
        resume_response = client.post('/bot/resume')
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

    assert pause_response.status_code == 200
    assert pause_response.json()['state'] == 'paused'

    assert resume_response.status_code == 200
    assert resume_response.json()['state'] == 'running'

    assert stop_response.status_code == 200
    assert stop_response.json()['state'] == 'stopped'
