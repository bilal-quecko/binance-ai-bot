from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.analysis.symbol_sentiment import SymbolSentimentSnapshot
from app.analysis.technical import TechnicalAnalysisSnapshot, TimeframeTechnicalSummary
from app.analysis.pattern_summary import PatternAnalysisSnapshot
from app.ai.models import AIFeatureVector, AISignalSnapshot
from fastapi.testclient import TestClient

from app.api.bot_api import (
    get_bot_runtime,
    get_settings_dependency,
    get_symbol_sentiment_service,
    get_symbol_service,
)
from app.bot import BotStatus, PaperBotRuntime, WorkstationState
from app.config import Settings
from app.exchange.symbol_service import SpotSymbolRecord
from app.features.models import FeatureSnapshot
from app.main import app
from app.market_data.candles import Candle
from app.market_data.models import MarketSnapshot
from app.market_data.orderbook import TopOfBook
from app.paper.models import Position
from app.runner.models import TradeReadiness
from app.sentiment.models import SentimentComponent
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


class FakeSymbolSentimentService:
    def __init__(self, snapshot: SymbolSentimentSnapshot | None = None) -> None:
        self._snapshot = snapshot

    def analyze(
        self,
        *,
        symbol: str,
        candles=(),
        benchmark_symbol=None,
        benchmark_closes=(),
    ) -> SymbolSentimentSnapshot:
        if self._snapshot is not None:
            return self._snapshot
        return SymbolSentimentSnapshot(
            symbol=symbol,
            generated_at=datetime(2024, 3, 9, 16, 2, tzinfo=UTC),
            data_state='incomplete',
            status_message=f'Proxy sentiment for {symbol} still needs more live history.',
            score=None,
            label='insufficient_data',
            confidence=None,
            momentum_state='unknown',
            risk_flag='unknown',
            explanation=f'Symbol sentiment for {symbol} is unavailable because proxy sentiment inputs are still incomplete.',
            source_mode='proxy',
            components=(),
        )


class FakeRuntime:
    def __init__(self) -> None:
        self.state = BotStatus(state='stopped', mode='stopped', timeframe='1m')
        self.reset_called = False
        self._storage_degraded = False
        self._storage_message: str | None = None
        self._persistence_last_ok_at: datetime | None = datetime(2024, 3, 9, 16, 2, tzinfo=UTC)
        self._persistence_recovery_source: str | None = None

    def status(self) -> BotStatus:
        return self.state

    def storage_degraded(self) -> bool:
        return False

    def storage_status_message(self) -> str | None:
        return self._storage_message

    def persistence_state(self) -> str:
        if self._storage_degraded:
            if self.state.state in {'running', 'paused'} or self.state.recovered_from_prior_session or self.state.broker_state_restored:
                return 'degraded_in_memory_only'
            return 'unavailable'
        if self.state.recovered_from_prior_session or self.state.broker_state_restored:
            return 'recovered_from_persistence'
        return 'healthy'

    def persistence_status_message(self) -> str:
        if self._storage_degraded:
            return self._storage_message or 'Persistence is degraded. Current paper state is only safe in memory.'
        if self.state.recovered_from_prior_session or self.state.broker_state_restored:
            return self.state.recovery_message or 'Recovered session state from persisted storage.'
        return 'Runtime state and paper broker state are persisting normally.'

    def persistence_last_ok_at(self) -> datetime | None:
        return self._persistence_last_ok_at

    def persistence_recovery_source(self) -> str | None:
        return self._persistence_recovery_source

    async def start(self, symbol: str) -> BotStatus:
        self.state = BotStatus(
            state='running',
            mode='auto_paper',
            symbol=symbol,
            timeframe='1m',
            session_id='session-btcusdt',
            started_at=datetime(2024, 3, 9, 16, 0, tzinfo=UTC),
        )
        return self.state

    async def stop(self) -> BotStatus:
        self.state = BotStatus(
            state='stopped',
            mode='stopped',
            symbol=self.state.symbol,
            timeframe='1m',
            session_id=self.state.session_id,
        )
        return self.state

    async def pause(self) -> BotStatus:
        self.state = BotStatus(
            state='paused',
            mode='paused',
            symbol=self.state.symbol,
            timeframe='1m',
            session_id=self.state.session_id,
        )
        return self.state

    async def resume(self) -> BotStatus:
        self.state = BotStatus(
            state='running',
            mode='auto_paper',
            symbol=self.state.symbol,
            timeframe='1m',
            session_id=self.state.session_id,
        )
        return self.state

    async def reset_session(self) -> BotStatus:
        self.reset_called = True
        self.state = BotStatus(state='stopped', mode='stopped', timeframe='1m')
        return self.state

    def candle_history(self, symbol: str) -> list[Candle]:
        return []

    def technical_analysis(self, symbol: str) -> TechnicalAnalysisSnapshot | None:
        snapshot_time = datetime(2024, 3, 9, 16, 2, tzinfo=UTC)
        return TechnicalAnalysisSnapshot(
            symbol=symbol,
            timestamp=snapshot_time,
            data_state='ready',
            status_message=f'Technical analysis is ready for {symbol}.',
            trend_direction='bullish',
            trend_strength='moderate',
            trend_strength_score=61,
            support_levels=[Decimal('99.5'), Decimal('100')],
            resistance_levels=[Decimal('101.5'), Decimal('102')],
            momentum_state='bullish',
            volatility_regime='normal',
            breakout_readiness='medium',
            breakout_bias='upside',
            reversal_risk='low',
            multi_timeframe_agreement='bullish_alignment',
            timeframe_summaries=[
                TimeframeTechnicalSummary(timeframe='1m', trend_direction='bullish', trend_strength='moderate'),
                TimeframeTechnicalSummary(timeframe='5m', trend_direction='bullish', trend_strength='moderate'),
            ],
            explanation='Trend is bullish with moderate strength and improving momentum.',
        )

    def pattern_analysis(self, symbol: str) -> PatternAnalysisSnapshot | None:
        return PatternAnalysisSnapshot(
            symbol=symbol,
            horizon='7d',
            generated_at=datetime(2024, 3, 9, 16, 2, tzinfo=UTC),
            data_state='ready',
            status_message=f'Pattern analysis is ready for {symbol} over 7D.',
            coverage_start=datetime(2024, 3, 2, 16, 2, tzinfo=UTC),
            coverage_end=datetime(2024, 3, 9, 16, 2, tzinfo=UTC),
            coverage_ratio_pct=Decimal('100'),
            partial_coverage=False,
            overall_direction='bullish',
            net_return_pct=Decimal('5.5'),
            up_moves=8,
            down_moves=3,
            flat_moves=1,
            up_move_ratio_pct=Decimal('66.67'),
            down_move_ratio_pct=Decimal('25'),
            realized_volatility_pct=Decimal('1.2'),
            max_drawdown_pct=Decimal('2.5'),
            trend_character='persistent',
            breakout_tendency='breakout_prone',
            reversal_tendency='low',
            explanation='BTCUSDT trended higher over the selected horizon with contained drawdowns.',
        )

    def workstation_state(self, symbol: str) -> WorkstationState:
        snapshot_time = datetime(2024, 3, 9, 16, 2, tzinfo=UTC)
        next_action = 'enter' if self.state.mode == 'auto_paper' else 'resume_auto_trade'
        reason_if_not_trading = None if self.state.mode == 'auto_paper' else 'An entry signal exists, but auto paper trading is paused.'
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
            trade_readiness=TradeReadiness(
                selected_symbol=symbol,
                runtime_active=True,
                mode=self.state.mode,
                enough_candle_history=True,
                deterministic_entry_signal=True,
                deterministic_exit_signal=False,
                risk_ready=True,
                risk_blocked=False,
                broker_ready=True,
                next_action=next_action,
                reason_if_not_trading=reason_if_not_trading,
                risk_reason_codes=('APPROVED',),
                expected_edge_pct=Decimal('0.02985074626865671641791044776'),
                estimated_round_trip_cost_pct=Decimal('0.001'),
            ),
            entry_signal=StrategySignal(symbol=symbol, side='BUY', confidence=Decimal('0.6'), reason_codes=('EMA_BULLISH',)),
            exit_signal=StrategySignal(symbol=symbol, side='HOLD', confidence=Decimal('1.0'), reason_codes=('POSITION_OPEN',)),
            current_position=Position(symbol=symbol, quantity=Decimal('1'), avg_entry_price=Decimal('99'), realized_pnl=Decimal('2')),
            last_cycle_result=None,
            total_pnl=Decimal('3'),
            realized_pnl=Decimal('2'),
        )


class NeutralRuntime(FakeRuntime):
    def technical_analysis(self, symbol: str) -> TechnicalAnalysisSnapshot | None:
        return None

    def workstation_state(self, symbol: str) -> WorkstationState:
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
            total_pnl=Decimal('0'),
            realized_pnl=Decimal('0'),
        )


class BrokenRuntime(NeutralRuntime):
    def workstation_state(self, symbol: str) -> WorkstationState:
        raise RuntimeError("simulated workstation failure")


class DegradedPersistenceRuntime(FakeRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.state = BotStatus(
            state='running',
            mode='auto_paper',
            symbol='BTCUSDT',
            timeframe='1m',
            session_id='session-btcusdt',
            started_at=datetime(2024, 3, 9, 16, 0, tzinfo=UTC),
        )
        self._storage_degraded = True
        self._storage_message = 'Persistence is temporarily unavailable. Live paper state is still running in memory.'


class UnavailablePersistenceRuntime(NeutralRuntime):
    def __init__(self) -> None:
        super().__init__()
        self._storage_degraded = True
        self._storage_message = 'Persistence is unavailable. No recoverable session state is currently available.'


class RecoveredPersistenceRuntime(FakeRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.state = BotStatus(
            state='paused',
            mode='paused',
            symbol='BTCUSDT',
            timeframe='1m',
            session_id='recovered-session',
            started_at=datetime(2024, 3, 9, 15, 50, tzinfo=UTC),
            last_event_time=datetime(2024, 3, 9, 15, 59, tzinfo=UTC),
            recovered_from_prior_session=True,
            broker_state_restored=True,
            recovery_message='Recovered a prior paper session after backend restart. Manual resume is required before auto trading continues.',
        )
        self._persistence_recovery_source = 'sqlite_runtime_session+paper_broker_state'


class HistoryWaitingRuntime(FakeRuntime):
    def __init__(self) -> None:
        super().__init__()
        self.state = BotStatus(
            state='running',
            mode='auto_paper',
            symbol='BTCUSDT',
            timeframe='1m',
            session_id='session-btcusdt',
            started_at=datetime(2024, 3, 9, 16, 0, tzinfo=UTC),
        )

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
            trade_readiness=TradeReadiness(
                selected_symbol=symbol,
                runtime_active=True,
                mode='auto_paper',
                enough_candle_history=False,
                deterministic_entry_signal=False,
                deterministic_exit_signal=False,
                risk_ready=False,
                risk_blocked=False,
                broker_ready=True,
                next_action='wait_for_history',
                reason_if_not_trading=f'Waiting for enough closed candle history to build deterministic signals for {symbol}.',
                risk_reason_codes=(),
            ),
            entry_signal=None,
            exit_signal=None,
            current_position=None,
            last_cycle_result=None,
            total_pnl=Decimal('0'),
            realized_pnl=Decimal('0'),
        )

    def technical_analysis(self, symbol: str) -> TechnicalAnalysisSnapshot | None:
        return TechnicalAnalysisSnapshot(
            symbol=symbol,
            timestamp=datetime(2024, 3, 9, 16, 2, tzinfo=UTC),
            data_state='incomplete',
            status_message=f'Technical analysis for {symbol} needs more closed candles before trend and structure can be assessed.',
            trend_direction=None,
            trend_strength=None,
            trend_strength_score=None,
            support_levels=[],
            resistance_levels=[],
            momentum_state=None,
            volatility_regime=None,
            breakout_readiness=None,
            breakout_bias=None,
            reversal_risk=None,
            multi_timeframe_agreement=None,
            timeframe_summaries=[],
            explanation=None,
        )


def _db_path() -> Path:
    base = Path("tests/.tmp_storage")
    base.mkdir(parents=True, exist_ok=True)
    return (base / f"bot_api_{uuid4().hex}.sqlite").resolve()


def _persistence_json(
    *,
    state: str,
    message: str,
    last_ok_at: str | None = '2024-03-09T16:02:00Z',
    recovery_source: str | None = None,
) -> dict[str, str | None]:
    return {
        'persistence_state': state,
        'persistence_message': message,
        'persistence_last_ok_at': last_ok_at,
        'recovery_source': recovery_source,
    }


class IdleStreamManager:
    async def stream(self, streams: list[str], *, websocket_client=None):
        if False:
            yield streams


def _insert_close_series(
    repository: StorageRepository,
    *,
    symbol: str,
    closes: list[Decimal],
    start: datetime,
) -> None:
    for index, close_price in enumerate(closes):
        open_time = start + timedelta(minutes=index)
        repository.insert_market_candle_snapshot(
            Candle(
                symbol=symbol,
                timeframe='1m',
                open=close_price,
                high=close_price,
                low=close_price,
                close=close_price,
                volume=Decimal('10'),
                quote_volume=close_price * Decimal('10'),
                open_time=open_time,
                close_time=open_time + timedelta(minutes=1),
                event_time=open_time + timedelta(minutes=1),
                trade_count=10,
                is_closed=True,
            )
        )


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
            open=Decimal('95'),
            high=Decimal('96'),
            low=Decimal('94'),
            close=Decimal('95'),
            volume=Decimal('10'),
            quote_volume=Decimal('950'),
            open_time=datetime(2024, 3, 8, 16, 4, 0, 1000, tzinfo=UTC),
            close_time=datetime(2024, 3, 8, 16, 5, tzinfo=UTC),
            event_time=datetime(2024, 3, 8, 16, 5, tzinfo=UTC),
            trade_count=10,
            is_closed=True,
        )
    )
    repository.insert_market_candle_snapshot(
        Candle(
            symbol='BTCUSDT',
            timeframe='1m',
            open=Decimal('97'),
            high=Decimal('98'),
            low=Decimal('96'),
            close=Decimal('97'),
            volume=Decimal('10'),
            quote_volume=Decimal('970'),
            open_time=datetime(2024, 3, 8, 20, 4, 0, 1000, tzinfo=UTC),
            close_time=datetime(2024, 3, 8, 20, 5, tzinfo=UTC),
            event_time=datetime(2024, 3, 8, 20, 5, tzinfo=UTC),
            trade_count=10,
            is_closed=True,
        )
    )
    repository.insert_market_candle_snapshot(
        Candle(
            symbol='BTCUSDT',
            timeframe='1m',
            open=Decimal('99'),
            high=Decimal('100'),
            low=Decimal('98'),
            close=Decimal('99'),
            volume=Decimal('10'),
            quote_volume=Decimal('990'),
            open_time=datetime(2024, 3, 9, 8, 4, 0, 1000, tzinfo=UTC),
            close_time=datetime(2024, 3, 9, 8, 5, tzinfo=UTC),
            event_time=datetime(2024, 3, 9, 8, 5, tzinfo=UTC),
            trade_count=10,
            is_closed=True,
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
        technical_analysis_response = client.get('/bot/technical-analysis', params={'symbol': 'BTCUSDT'})
        pattern_analysis_response = client.get('/bot/pattern-analysis', params={'symbol': 'BTCUSDT', 'horizon': '1d'})
        ai_signal_response = client.get('/bot/ai-signal', params={'symbol': 'BTCUSDT'})
        ai_history_response = client.get('/bot/ai-signal/history', params={'symbol': 'BTCUSDT', 'limit': 10, 'offset': 0})
        ai_evaluation_response = client.get('/bot/ai-signal/evaluation', params={'symbol': 'BTCUSDT'})
        pause_response = client.post('/bot/pause')
        paused_workstation_response = client.get('/bot/workstation', params={'symbol': 'BTCUSDT'})
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
    assert start_response.json()['mode'] == 'auto_paper'
    assert start_response.json()['symbol'] == 'BTCUSDT'
    assert start_response.json()['session_id'] == 'session-btcusdt'

    assert status_response.status_code == 200
    assert status_response.json()['state'] == 'running'
    assert status_response.json()['session_id'] == 'session-btcusdt'

    assert workstation_response.status_code == 200
    assert workstation_response.json()['symbol'] == 'BTCUSDT'
    assert workstation_response.json()['data_state'] == 'ready'
    assert workstation_response.json()['runtime_status']['mode'] == 'auto_paper'
    assert workstation_response.json()['entry_signal']['side'] == 'BUY'
    assert workstation_response.json()['trade_readiness']['next_action'] == 'enter'
    assert workstation_response.json()['trade_readiness']['risk_ready'] is True
    assert workstation_response.json()['ai_signal']['bias'] == 'bullish'

    assert technical_analysis_response.status_code == 200
    assert technical_analysis_response.json()['data_state'] == 'ready'
    assert technical_analysis_response.json()['trend_direction'] == 'bullish'
    assert technical_analysis_response.json()['support_levels'] == ['99.5', '100']
    assert technical_analysis_response.json()['timeframe_summaries'][0]['timeframe'] == '1m'
    assert pattern_analysis_response.status_code == 200
    assert pattern_analysis_response.json()['symbol'] == 'BTCUSDT'
    assert pattern_analysis_response.json()['horizon'] == '1d'
    assert pattern_analysis_response.json()['overall_direction'] == 'bullish'
    assert 'net_return_pct' in pattern_analysis_response.json()

    assert ai_signal_response.status_code == 200
    assert ai_signal_response.json()['confidence'] == 72
    assert ai_signal_response.json()['timestamp'] == '2024-03-09T16:02:00Z'
    assert ai_signal_response.json()['features']['candle_count'] == 5
    assert ai_signal_response.json()['regime'] == 'insufficient_data'
    assert ai_signal_response.json()['noise_level'] == 'unknown'
    assert ai_signal_response.json()['abstain'] is False
    assert isinstance(ai_signal_response.json()['horizons'], list)

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
    assert pause_response.json()['mode'] == 'paused'
    assert paused_workstation_response.status_code == 200
    assert paused_workstation_response.json()['trade_readiness']['next_action'] == 'resume_auto_trade'

    assert resume_response.status_code == 200
    assert resume_response.json()['state'] == 'running'
    assert resume_response.json()['mode'] == 'auto_paper'

    assert reset_response.status_code == 200
    assert reset_response.json()['state'] == 'stopped'
    assert fake_runtime.reset_called is True

    assert stop_response.status_code == 200
    assert stop_response.json()['state'] == 'stopped'


def test_runtime_status_remains_stable_across_repeated_reads() -> None:
    db_path = _db_path()
    settings = Settings(DATABASE_URL=f"sqlite:///{db_path}")
    fake_runtime = FakeRuntime()
    app.dependency_overrides[get_symbol_service] = lambda: FakeSymbolService()
    app.dependency_overrides[get_bot_runtime] = lambda: fake_runtime
    app.dependency_overrides[get_settings_dependency] = lambda: settings
    client = TestClient(app)

    try:
        start_response = client.post('/bot/start', json={'symbol': 'BTCUSDT'})
        status_response_a = client.get('/bot/status')
        status_response_b = client.get('/bot/status')
        workstation_response = client.get('/bot/workstation', params={'symbol': 'BTCUSDT'})
    finally:
        app.dependency_overrides.clear()

    assert start_response.status_code == 200
    assert status_response_a.status_code == 200
    assert status_response_b.status_code == 200
    assert status_response_a.json()['session_id'] == 'session-btcusdt'
    assert status_response_b.json()['session_id'] == 'session-btcusdt'
    assert status_response_a.json()['symbol'] == 'BTCUSDT'
    assert status_response_b.json()['symbol'] == 'BTCUSDT'
    assert workstation_response.status_code == 200
    assert workstation_response.json()['runtime_status']['session_id'] == 'session-btcusdt'


def test_market_sentiment_endpoint_returns_ready_shape() -> None:
    db_path = _db_path()
    settings = Settings(DATABASE_URL=f"sqlite:///{db_path}")
    repository = StorageRepository(settings.database_url)
    try:
        start = datetime(2024, 3, 9, 12, 0, tzinfo=UTC)
        _insert_close_series(
            repository,
            symbol='BTCUSDT',
            closes=[Decimal('100') + (Decimal('0.35') * Decimal(index)) for index in range(90)],
            start=start,
        )
        _insert_close_series(
            repository,
            symbol='ETHUSDT',
            closes=[Decimal('50') + (Decimal('0.20') * Decimal(index)) for index in range(90)],
            start=start,
        )
        _insert_close_series(
            repository,
            symbol='SOLUSDT',
            closes=[Decimal('20') + (Decimal('0.16') * Decimal(index)) for index in range(90)],
            start=start,
        )
        _insert_close_series(
            repository,
            symbol='BNBUSDT',
            closes=[Decimal('30') + (Decimal('0.10') * Decimal(index)) for index in range(90)],
            start=start,
        )
        _insert_close_series(
            repository,
            symbol='XRPUSDT',
            closes=[Decimal('10') + (Decimal('0.04') * Decimal(index)) for index in range(90)],
            start=start,
        )
    finally:
        repository.close()

    app.dependency_overrides[get_symbol_service] = lambda: FakeSymbolService()
    app.dependency_overrides[get_bot_runtime] = lambda: NeutralRuntime()
    app.dependency_overrides[get_settings_dependency] = lambda: settings
    client = TestClient(app)

    try:
        response = client.get('/bot/market-sentiment', params={'symbol': 'SOLUSDT'})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload['symbol'] == 'SOLUSDT'
    assert payload['data_state'] == 'ready'
    assert payload['market_state'] == 'risk_on'
    assert payload['btc_bias'] == 'bullish'
    assert payload['eth_bias'] == 'bullish'
    assert payload['market_breadth_state'] == 'positive'
    assert payload['selected_symbol_relative_strength'] == 'outperforming_btc'
    assert isinstance(payload['sentiment_score'], int)
    assert 'explanation' in payload


def test_recovered_runtime_state_is_visible_after_restart_style_reconstruction() -> None:
    db_path = _db_path()
    settings = Settings(DATABASE_URL=f"sqlite:///{db_path}", APP_MODE='paper')
    repository = StorageRepository(settings.database_url)
    try:
        repository.upsert_runtime_session_state(
            state='running',
            mode='auto_paper',
            symbol='BTCUSDT',
            session_id='recovered-session',
            started_at=datetime(2024, 3, 9, 16, 0, tzinfo=UTC),
            last_event_time=datetime(2024, 3, 9, 16, 5, tzinfo=UTC),
            last_error=None,
        )
        repository.upsert_paper_broker_state(
            balances={'USDT': Decimal('9950')},
            positions={
                'BTCUSDT': Position(
                    symbol='BTCUSDT',
                    quantity=Decimal('0.5'),
                    avg_entry_price=Decimal('100'),
                    realized_pnl=Decimal('12'),
                    quote_asset='USDT',
                )
            },
            realized_pnl=Decimal('12'),
            snapshot_time=datetime(2024, 3, 9, 16, 6, tzinfo=UTC),
        )
    finally:
        repository.close()

    runtime = PaperBotRuntime(settings=settings, websocket_client=None, stream_manager=IdleStreamManager())  # type: ignore[arg-type]
    app.dependency_overrides[get_symbol_service] = lambda: FakeSymbolService()
    app.dependency_overrides[get_bot_runtime] = lambda: runtime
    app.dependency_overrides[get_settings_dependency] = lambda: settings
    client = TestClient(app)

    try:
        status_response = client.get('/bot/status')
        workstation_response = client.get('/bot/workstation', params={'symbol': 'BTCUSDT'})
    finally:
        app.dependency_overrides.clear()

    assert status_response.status_code == 200
    assert status_response.json()['state'] == 'paused'
    assert status_response.json()['mode'] == 'paused'
    assert status_response.json()['symbol'] == 'BTCUSDT'
    assert status_response.json()['recovered_from_prior_session'] is True
    assert status_response.json()['broker_state_restored'] is True
    assert 'Manual resume is required' in status_response.json()['recovery_message']
    assert status_response.json()['persistence']['persistence_state'] == 'recovered_from_persistence'
    assert 'Manual resume is required' in status_response.json()['persistence']['persistence_message']
    assert status_response.json()['persistence']['recovery_source'] == 'sqlite_runtime_session+paper_broker_state'
    assert status_response.json()['persistence']['persistence_last_ok_at'] is not None

    assert workstation_response.status_code == 200
    assert workstation_response.json()['data_state'] == 'waiting_for_history'
    assert workstation_response.json()['runtime_status']['recovered_from_prior_session'] is True
    assert workstation_response.json()['runtime_status']['broker_state_restored'] is True
    assert workstation_response.json()['persistence']['persistence_state'] == 'recovered_from_persistence'
    assert 'Manual resume is required' in workstation_response.json()['persistence']['persistence_message']
    assert workstation_response.json()['persistence']['recovery_source'] == 'sqlite_runtime_session+paper_broker_state'
    assert workstation_response.json()['persistence']['persistence_last_ok_at'] is not None
    assert workstation_response.json()['current_position']['quantity'] == '0.5'
    assert workstation_response.json()['trade_readiness']['next_action'] == 'resume_runtime'
    assert 'Manual resume is required' in workstation_response.json()['trade_readiness']['reason_if_not_trading']


def test_workstation_endpoints_return_empty_states_without_runtime_data() -> None:
    db_path = _db_path()
    settings = Settings(DATABASE_URL=f"sqlite:///{db_path}")
    fake_symbol_service = FakeSymbolService()
    neutral_runtime = NeutralRuntime()
    app.dependency_overrides[get_symbol_service] = lambda: fake_symbol_service
    app.dependency_overrides[get_symbol_sentiment_service] = lambda: FakeSymbolSentimentService()
    app.dependency_overrides[get_bot_runtime] = lambda: neutral_runtime
    app.dependency_overrides[get_settings_dependency] = lambda: settings
    client = TestClient(app)

    try:
        workstation_response = client.get('/bot/workstation', params={'symbol': 'ETHUSDT'})
        technical_analysis_response = client.get('/bot/technical-analysis', params={'symbol': 'ETHUSDT'})
        pattern_analysis_response = client.get('/bot/pattern-analysis', params={'symbol': 'ETHUSDT', 'horizon': '7d'})
        market_sentiment_response = client.get('/bot/market-sentiment', params={'symbol': 'ETHUSDT'})
        symbol_sentiment_response = client.get('/bot/symbol-sentiment', params={'symbol': 'ETHUSDT'})
        fusion_signal_response = client.get('/bot/fusion-signal', params={'symbol': 'ETHUSDT'})
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
            'mode': 'stopped',
            'symbol': None,
            'timeframe': '1m',
            'paper_only': True,
            'session_id': None,
            'started_at': None,
            'last_event_time': None,
            'last_error': None,
            'recovered_from_prior_session': False,
            'broker_state_restored': False,
            'recovery_message': None,
            'persistence': _persistence_json(
                state='healthy',
                message='Runtime state and paper broker state are persisting normally.',
                recovery_source=None,
            ),
        },
        'persistence': _persistence_json(
            state='healthy',
            message='Runtime state and paper broker state are persisting normally.',
            recovery_source=None,
        ),
        'last_price': None,
        'current_candle': None,
        'top_of_book': None,
        'feature': None,
        'trade_readiness': {
            'selected_symbol': 'ETHUSDT',
            'runtime_active': False,
            'mode': 'stopped',
            'enough_candle_history': False,
            'deterministic_entry_signal': False,
            'deterministic_exit_signal': False,
            'risk_ready': False,
            'risk_blocked': False,
            'broker_ready': False,
            'next_action': 'start_runtime',
            'reason_if_not_trading': 'Start the live runtime for ETHUSDT before auto paper trading can act.',
            'risk_reason_codes': [],
            'expected_edge_pct': None,
            'estimated_round_trip_cost_pct': None,
        },
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
    assert technical_analysis_response.status_code == 200
    assert technical_analysis_response.json()['data_state'] == 'waiting_for_runtime'
    assert technical_analysis_response.json()['trend_direction'] is None
    assert pattern_analysis_response.status_code == 200
    assert pattern_analysis_response.json()['data_state'] == 'waiting_for_runtime'
    assert pattern_analysis_response.json()['overall_direction'] is None
    assert market_sentiment_response.status_code == 200
    assert market_sentiment_response.json()['data_state'] == 'waiting_for_runtime'
    assert market_sentiment_response.json()['market_state'] == 'insufficient_data'
    assert symbol_sentiment_response.status_code == 200
    assert symbol_sentiment_response.json()['data_state'] == 'waiting_for_runtime'
    assert symbol_sentiment_response.json()['label'] == 'insufficient_data'
    assert symbol_sentiment_response.json()['components'] == []
    assert fusion_signal_response.status_code == 200
    assert fusion_signal_response.json()['data_state'] == 'waiting_for_runtime'
    assert fusion_signal_response.json()['final_signal'] == 'wait'
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


def test_symbol_sentiment_endpoint_returns_ready_shape_with_source_backing() -> None:
    db_path = _db_path()
    settings = Settings(DATABASE_URL=f"sqlite:///{db_path}")
    snapshot = SymbolSentimentSnapshot(
        symbol='XRPUSDT',
        generated_at=datetime(2024, 3, 9, 16, 2, tzinfo=UTC),
        data_state='ready',
        status_message='Proxy sentiment is ready for XRPUSDT.',
        score=74,
        label='bullish',
        confidence=67,
        momentum_state='rising',
        risk_flag='normal',
        explanation='Proxy symbol sentiment for XRPUSDT reads bullish. Price acceleration and exchange activity both support the move.',
        source_mode='proxy',
        components=(
            SentimentComponent(
                name='price_acceleration',
                score=Decimal('0.74'),
                weight=Decimal('0.30'),
                explanation='Price acceleration proxy is bullish with strengthening returns.',
            ),
            SentimentComponent(
                name='exchange_activity_proxy',
                score=Decimal('0.43'),
                weight=Decimal('0.20'),
                explanation='Exchange-activity proxy is bullish with stronger trade participation.',
            ),
        ),
    )
    app.dependency_overrides[get_symbol_service] = lambda: FakeSymbolService()
    app.dependency_overrides[get_symbol_sentiment_service] = lambda: FakeSymbolSentimentService(snapshot)
    app.dependency_overrides[get_bot_runtime] = lambda: NeutralRuntime()
    app.dependency_overrides[get_settings_dependency] = lambda: settings
    client = TestClient(app)

    try:
        response = client.get('/bot/symbol-sentiment', params={'symbol': 'XRPUSDT'})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        'symbol': 'XRPUSDT',
        'generated_at': '2024-03-09T16:02:00Z',
        'data_state': 'ready',
        'status_message': 'Proxy sentiment is ready for XRPUSDT.',
        'score': 74,
        'label': 'bullish',
        'confidence': 67,
        'momentum_state': 'rising',
        'risk_flag': 'normal',
        'source_mode': 'proxy',
        'components': [
            'Price acceleration proxy is bullish with strengthening returns.',
            'Exchange-activity proxy is bullish with stronger trade participation.',
        ],
        'explanation': 'Proxy symbol sentiment for XRPUSDT reads bullish. Price acceleration and exchange activity both support the move.',
    }


def test_fusion_signal_endpoint_returns_ready_shape() -> None:
    db_path = _db_path()
    settings = Settings(DATABASE_URL=f"sqlite:///{db_path}")
    snapshot = SymbolSentimentSnapshot(
        symbol='BTCUSDT',
        generated_at=datetime(2024, 3, 9, 16, 2, tzinfo=UTC),
        data_state='ready',
        status_message='Proxy sentiment is ready for BTCUSDT.',
        score=58,
        label='bullish',
        confidence=71,
        momentum_state='rising',
        risk_flag='normal',
        explanation='Proxy symbol sentiment for BTCUSDT reads bullish from aligned proxy drivers.',
        source_mode='proxy',
        components=(
            SentimentComponent(
                name='price_acceleration',
                score=Decimal('0.58'),
                weight=Decimal('0.30'),
                explanation='Price acceleration proxy is bullish with strengthening returns.',
            ),
        ),
    )
    runtime = FakeRuntime()
    runtime.state = BotStatus(state='running', mode='auto_paper', symbol='BTCUSDT', timeframe='1m')
    app.dependency_overrides[get_symbol_service] = lambda: FakeSymbolService()
    app.dependency_overrides[get_symbol_sentiment_service] = lambda: FakeSymbolSentimentService(snapshot)
    app.dependency_overrides[get_bot_runtime] = lambda: runtime
    app.dependency_overrides[get_settings_dependency] = lambda: settings
    client = TestClient(app)

    try:
        response = client.get('/bot/fusion-signal', params={'symbol': 'BTCUSDT'})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload['symbol'] == 'BTCUSDT'
    assert payload['data_state'] in {'ready', 'waiting_for_history'}
    assert payload['final_signal'] in {'long', 'wait'}
    assert isinstance(payload['confidence'], int)
    assert payload['preferred_horizon'] in {'5m', '15m', '1h'}
    assert isinstance(payload['top_reasons'], list)
    assert isinstance(payload['warnings'], list)


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
    assert workstation_response.json()['persistence']['persistence_state'] == 'healthy'
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
        technical_analysis_response = client.get('/bot/technical-analysis', params={'symbol': 'BTCUSDT'})
        pattern_analysis_response = client.get('/bot/pattern-analysis', params={'symbol': 'BTCUSDT', 'horizon': '7d'})
        market_sentiment_response = client.get('/bot/market-sentiment', params={'symbol': 'BTCUSDT'})
        ai_history_response = client.get('/bot/ai-signal/history', params={'symbol': 'BTCUSDT', 'limit': 5, 'offset': 0})
        ai_evaluation_response = client.get('/bot/ai-signal/evaluation', params={'symbol': 'BTCUSDT'})
    finally:
        app.dependency_overrides.clear()

    assert workstation_response.status_code == 200
    assert workstation_response.json()['data_state'] == 'waiting_for_history'
    assert workstation_response.json()['trade_readiness']['next_action'] == 'wait_for_history'
    assert technical_analysis_response.status_code == 200
    assert technical_analysis_response.json()['data_state'] == 'waiting_for_history'
    assert pattern_analysis_response.status_code == 200
    assert pattern_analysis_response.json()['data_state'] == 'waiting_for_history'
    assert market_sentiment_response.status_code == 200
    assert market_sentiment_response.json()['data_state'] == 'waiting_for_history'
    assert ai_history_response.status_code == 200
    assert ai_history_response.json()['data_state'] == 'waiting_for_history'
    assert ai_evaluation_response.status_code == 200
    assert ai_evaluation_response.json()['data_state'] == 'waiting_for_history'


def test_status_and_workstation_report_degraded_in_memory_only_persistence() -> None:
    db_path = _db_path()
    settings = Settings(DATABASE_URL=f"sqlite:///{db_path}")
    runtime = DegradedPersistenceRuntime()
    app.dependency_overrides[get_symbol_service] = lambda: FakeSymbolService()
    app.dependency_overrides[get_bot_runtime] = lambda: runtime
    app.dependency_overrides[get_settings_dependency] = lambda: settings
    client = TestClient(app)

    try:
        status_response = client.get('/bot/status')
        workstation_response = client.get('/bot/workstation', params={'symbol': 'BTCUSDT'})
    finally:
        app.dependency_overrides.clear()

    assert status_response.status_code == 200
    assert status_response.json()['persistence']['persistence_state'] == 'degraded_in_memory_only'
    assert 'still running in memory' in status_response.json()['persistence']['persistence_message']
    assert workstation_response.status_code == 200
    assert workstation_response.json()['persistence']['persistence_state'] == 'degraded_in_memory_only'
    assert 'still running in memory' in workstation_response.json()['persistence']['persistence_message']


def test_status_reports_unavailable_persistence_when_storage_is_not_usable() -> None:
    db_path = _db_path()
    settings = Settings(DATABASE_URL=f"sqlite:///{db_path}")
    runtime = UnavailablePersistenceRuntime()
    app.dependency_overrides[get_symbol_service] = lambda: FakeSymbolService()
    app.dependency_overrides[get_bot_runtime] = lambda: runtime
    app.dependency_overrides[get_settings_dependency] = lambda: settings
    client = TestClient(app)

    try:
        status_response = client.get('/bot/status')
        workstation_response = client.get('/bot/workstation', params={'symbol': 'BTCUSDT'})
    finally:
        app.dependency_overrides.clear()

    assert status_response.status_code == 200
    assert status_response.json()['persistence']['persistence_state'] == 'unavailable'
    assert 'No recoverable session state' in status_response.json()['persistence']['persistence_message']
    assert workstation_response.status_code == 200
    assert workstation_response.json()['persistence']['persistence_state'] == 'unavailable'


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
    assert workstation_response.json()['trade_readiness']['next_action'] == 'start_runtime'
    assert ai_history_response.status_code == 200
    assert ai_history_response.json()['items'] == []


def test_reset_clears_persisted_runtime_and_broker_recovery_state() -> None:
    db_path = _db_path()
    settings = Settings(DATABASE_URL=f"sqlite:///{db_path}", APP_MODE='paper')
    repository = StorageRepository(settings.database_url)
    try:
        repository.upsert_runtime_session_state(
            state='running',
            mode='auto_paper',
            symbol='BTCUSDT',
            session_id='recovered-session',
            started_at=datetime(2024, 3, 9, 16, 0, tzinfo=UTC),
            last_event_time=datetime(2024, 3, 9, 16, 5, tzinfo=UTC),
            last_error=None,
        )
        repository.upsert_paper_broker_state(
            balances={'USDT': Decimal('9950')},
            positions={
                'BTCUSDT': Position(
                    symbol='BTCUSDT',
                    quantity=Decimal('0.5'),
                    avg_entry_price=Decimal('100'),
                    realized_pnl=Decimal('12'),
                    quote_asset='USDT',
                )
            },
            realized_pnl=Decimal('12'),
            snapshot_time=datetime(2024, 3, 9, 16, 6, tzinfo=UTC),
        )
    finally:
        repository.close()

    runtime = PaperBotRuntime(settings=settings, websocket_client=None, stream_manager=IdleStreamManager())  # type: ignore[arg-type]
    app.dependency_overrides[get_symbol_service] = lambda: FakeSymbolService()
    app.dependency_overrides[get_bot_runtime] = lambda: runtime
    app.dependency_overrides[get_settings_dependency] = lambda: settings
    client = TestClient(app)

    try:
        reset_response = client.post('/bot/reset')
        status_response = client.get('/bot/status')
        workstation_response = client.get('/bot/workstation', params={'symbol': 'BTCUSDT'})
    finally:
        app.dependency_overrides.clear()

    reopened = StorageRepository(settings.database_url)
    try:
        persisted_status = reopened.get_runtime_session_state()
        persisted_broker = reopened.get_paper_broker_state()
    finally:
        reopened.close()

    assert reset_response.status_code == 200
    assert status_response.status_code == 200
    assert status_response.json()['state'] == 'stopped'
    assert status_response.json()['recovered_from_prior_session'] is False
    assert status_response.json()['broker_state_restored'] is False
    assert status_response.json()['recovery_message'] is None
    assert workstation_response.status_code == 200
    assert workstation_response.json()['current_position'] is None
    assert workstation_response.json()['trade_readiness']['next_action'] == 'start_runtime'
    assert persisted_status is None
    assert persisted_broker is None


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
