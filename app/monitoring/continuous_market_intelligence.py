"""Backend-owned continuous, tiered Binance market intelligence service."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from statistics import median
from typing import Literal, TypeVar
from uuid import uuid4

from app.config import Settings
from app.data.historical_candles import interval_to_timedelta, parse_rest_kline
from app.exchange.binance_rest import BinanceRestClient
from app.exchange.binance_ws import BinanceWebSocketClient
from app.exchange.symbol_service import SpotSymbolService
from app.market_data.candles import Candle
from app.storage.models import (
    ContinuousIntelligenceCandidateRecord,
    ContinuousIntelligenceCycleRecord,
    ContinuousIntelligenceStateRecord,
    HistoricalCandleRecord,
)
from app.storage.repositories import StorageRepository

LOGGER = logging.getLogger(__name__)

MarketName = Literal["spot", "futures"]
ServiceStatus = Literal["stopped", "starting", "running", "scanning", "paused", "degraded", "error"]
T = TypeVar("T")


@dataclass(slots=True, frozen=True)
class ContinuousIntelligenceConfig:
    """Validated runtime configuration for continuous market monitoring."""

    enabled: bool = True
    markets: tuple[MarketName, ...] = ("spot", "futures")
    quote_asset: str = "USDT"
    universe_limit: int = 50
    cycle_interval_seconds: int = 300
    universe_refresh_seconds: int = 1800
    deep_candidate_limit: int = 12
    fast_score_threshold: int = 45
    concurrency: int = 4
    request_interval_ms: int = 50
    initial_delay_seconds: int = 2

    def normalized(self) -> ContinuousIntelligenceConfig:
        markets = tuple(dict.fromkeys(item for item in self.markets if item in {"spot", "futures"}))
        return replace(
            self,
            markets=markets or ("spot",),
            quote_asset=self.quote_asset.strip().upper() or "USDT",
            universe_limit=max(1, min(100, self.universe_limit)),
            cycle_interval_seconds=max(30, min(3600, self.cycle_interval_seconds)),
            universe_refresh_seconds=max(300, min(86400, self.universe_refresh_seconds)),
            deep_candidate_limit=max(1, min(30, self.deep_candidate_limit)),
            fast_score_threshold=max(0, min(100, self.fast_score_threshold)),
            concurrency=max(1, min(10, self.concurrency)),
            request_interval_ms=max(0, min(2000, self.request_interval_ms)),
            initial_delay_seconds=max(0, min(300, self.initial_delay_seconds)),
        )


@dataclass(slots=True, frozen=True)
class ContinuousIntelligenceCandidate:
    """Latest tiered intelligence for one symbol."""

    market: MarketName
    symbol: str
    stage: str
    fast_score: int
    deep_score: int | None
    direction_hint: str
    current_price: Decimal | None
    triggers: tuple[str, ...]
    metrics: dict[str, object]
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    screened_at: datetime
    deep_analyzed_at: datetime | None
    data_source: str


@dataclass(slots=True)
class ContinuousIntelligenceStatus:
    """Live and persisted health snapshot for the continuous service."""

    enabled: bool
    status: ServiceStatus
    cycle_id: str | None = None
    started_at: datetime | None = None
    last_cycle_started_at: datetime | None = None
    last_cycle_completed_at: datetime | None = None
    last_full_universe_pass_at: datetime | None = None
    last_universe_refresh_at: datetime | None = None
    last_websocket_event_at: datetime | None = None
    next_cycle_at: datetime | None = None
    last_error: str | None = None
    universe_source: str = "unavailable"
    total_symbols: int = 0
    fast_screened_symbols: int = 0
    deep_analyzed_symbols: int = 0
    deep_queue_depth: int = 0
    successful_cycles: int = 0
    failed_cycles: int = 0
    consecutive_failures: int = 0
    websocket_events: int = 0
    websocket_state: str = "connecting"
    data_lag_seconds: int | None = None
    warnings: list[str] = field(default_factory=list)
    config: ContinuousIntelligenceConfig = field(default_factory=ContinuousIntelligenceConfig)
    advisory_only: bool = True
    paper_only: bool = True


class ContinuousMarketIntelligenceService:
    """Continuously screen Binance markets and deeply analyze developing activity."""

    def __init__(
        self,
        *,
        settings: Settings,
        rest_client: BinanceRestClient,
        spot_symbol_service: SpotSymbolService,
        spot_websocket_client: BinanceWebSocketClient | None = None,
        futures_websocket_client: BinanceWebSocketClient | None = None,
        repository: StorageRepository | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._settings = settings
        self._rest_client = rest_client
        self._spot_symbol_service = spot_symbol_service
        self._spot_websocket_client = spot_websocket_client
        self._futures_websocket_client = futures_websocket_client
        self._repository = repository or StorageRepository(settings.database_url)
        self._owns_repository = repository is None
        self._now = now_provider or (lambda: datetime.now(tz=UTC))
        self._config = self._config_from_settings(settings).normalized()
        self._status = ContinuousIntelligenceStatus(
            enabled=self._config.enabled,
            status="stopped",
            config=self._config,
        )
        self._task: asyncio.Task[None] | None = None
        self._websocket_tasks: list[asyncio.Task[None]] = []
        self._closed = asyncio.Event()
        self._cycle_lock = asyncio.Lock()
        self._lifecycle_lock = asyncio.Lock()
        self._request_lock = asyncio.Lock()
        self._request_semaphore = asyncio.Semaphore(self._config.concurrency)
        self._next_request_at = 0.0
        self._universes: dict[MarketName, list[str]] = {"spot": [], "futures": []}
        self._universe_sources: dict[MarketName, str] = {"spot": "unavailable", "futures": "unavailable"}
        self._ticker_quote_volumes: dict[tuple[MarketName, str], Decimal] = {}
        self._live_prices: dict[tuple[MarketName, str], Decimal] = {}
        self._last_websocket_checkpoint_at: datetime | None = None
        self._restore_checkpoint()

    @staticmethod
    def _config_from_settings(settings: Settings) -> ContinuousIntelligenceConfig:
        return ContinuousIntelligenceConfig(
            enabled=settings.continuous_intelligence_enabled,
            markets=tuple(settings.continuous_intelligence_market_list),  # type: ignore[arg-type]
            quote_asset=settings.continuous_intelligence_quote_asset,
            universe_limit=settings.continuous_intelligence_universe_limit,
            cycle_interval_seconds=settings.continuous_intelligence_cycle_seconds,
            universe_refresh_seconds=settings.continuous_intelligence_universe_refresh_seconds,
            deep_candidate_limit=settings.continuous_intelligence_deep_candidate_limit,
            fast_score_threshold=settings.continuous_intelligence_fast_score_threshold,
            concurrency=settings.continuous_intelligence_concurrency,
            request_interval_ms=settings.continuous_intelligence_request_interval_ms,
            initial_delay_seconds=settings.continuous_intelligence_initial_delay_seconds,
        )

    @property
    def config(self) -> ContinuousIntelligenceConfig:
        return self._config

    def status(self) -> ContinuousIntelligenceStatus:
        """Return a current status copy with derived lag and WebSocket health."""

        now = self._now()
        last_data = self._status.last_websocket_event_at or self._status.last_cycle_completed_at
        lag = max(0, int((now - last_data).total_seconds())) if last_data else None
        websocket_state = "connecting"
        warnings = list(self._status.warnings)
        if self._status.last_websocket_event_at is not None:
            websocket_lag = max(0, int((now - self._status.last_websocket_event_at).total_seconds()))
            websocket_state = "live" if websocket_lag <= 90 else "stale"
            if websocket_state == "stale":
                warnings.append("WebSocket prices are stale; REST candle reconciliation remains active.")
        elif not self._websocket_tasks:
            websocket_state = "unavailable"
            warnings.append("WebSocket heartbeat is unavailable; REST candle reconciliation remains active.")
        return replace(
            self._status,
            websocket_state=websocket_state,
            data_lag_seconds=lag,
            warnings=list(dict.fromkeys(warnings)),
            config=self._config,
        )

    async def start(self, *, auto_recover: bool = False) -> ContinuousIntelligenceStatus:
        """Start autonomous monitoring; optionally preserve a recovered paused state."""

        async with self._lifecycle_lock:
            if self._task is not None and not self._task.done():
                return self.status()
            if auto_recover and not self._config.enabled:
                return self.status()
            if auto_recover and self._status.status == "paused":
                return self.status()
            self._config = replace(self._config, enabled=True)
            self._request_semaphore = asyncio.Semaphore(self._config.concurrency)
            self._closed = asyncio.Event()
            self._status.enabled = True
            self._status.status = "starting"
            self._status.started_at = self._status.started_at or self._now()
            self._status.last_error = None
            self._persist_state()
            self._task = asyncio.create_task(self._run_loop(), name="continuous-market-intelligence")
            self._start_websocket_tasks()
        return self.status()

    async def pause(self) -> ContinuousIntelligenceStatus:
        """Pause new screening cycles and live-price listeners."""

        await self._cancel_tasks()
        self._status.status = "paused"
        self._status.enabled = True
        self._persist_state()
        return self.status()

    async def resume(self) -> ContinuousIntelligenceStatus:
        """Resume a paused continuous service."""

        return await self.start(auto_recover=False)

    async def stop(self) -> ContinuousIntelligenceStatus:
        """Stop monitoring and persist the operator-disabled state."""

        await self._cancel_tasks()
        self._config = replace(self._config, enabled=False)
        self._status.enabled = False
        self._status.status = "stopped"
        self._status.next_cycle_at = None
        self._persist_state()
        return self.status()

    async def close(self) -> None:
        """Stop process tasks while preserving whether auto-start is enabled."""

        await self._cancel_tasks()
        self._status.status = "stopped"
        self._status.next_cycle_at = None
        self._persist_state()
        if self._owns_repository:
            self._repository.close()

    async def update_config(
        self,
        **updates: object,
    ) -> ContinuousIntelligenceStatus:
        """Apply validated configuration for subsequent cycles and persist it."""

        allowed = {item.name for item in self._config.__dataclass_fields__.values()}
        filtered = {key: value for key, value in updates.items() if key in allowed and value is not None}
        if "markets" in filtered:
            filtered["markets"] = tuple(filtered["markets"])  # type: ignore[arg-type]
        self._config = replace(self._config, **filtered).normalized()
        self._status.enabled = self._config.enabled
        self._status.config = self._config
        self._request_semaphore = asyncio.Semaphore(self._config.concurrency)
        self._persist_state()
        return self.status()

    async def run_cycle_once(self) -> ContinuousIntelligenceStatus:
        """Run one complete tiered universe pass, primarily for operations and tests."""

        async with self._cycle_lock:
            await self._execute_cycle()
        return self.status()

    def candidates(
        self,
        *,
        market: str | None = None,
        stage: str | None = None,
        limit: int = 100,
    ) -> list[ContinuousIntelligenceCandidate]:
        """Return the persisted latest candidates independently of browser state."""

        records = self._repository.get_continuous_intelligence_candidates(
            market=market,
            stage=stage,
            limit=limit,
        )
        return [self._candidate_from_record(item) for item in records]

    def cycles(self, *, limit: int = 20) -> list[ContinuousIntelligenceCycleRecord]:
        return self._repository.get_continuous_intelligence_cycles(limit=limit)

    async def _run_loop(self) -> None:
        if self._config.initial_delay_seconds:
            try:
                await asyncio.wait_for(
                    self._closed.wait(),
                    timeout=self._config.initial_delay_seconds,
                )
                return
            except asyncio.TimeoutError:
                pass
        while not self._closed.is_set():
            try:
                await self.run_cycle_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - final supervisor boundary
                self._record_cycle_failure(exc)
                LOGGER.exception("Continuous market-intelligence cycle failed.")
            self._status.next_cycle_at = self._now() + timedelta(seconds=self._config.cycle_interval_seconds)
            self._persist_state()
            try:
                await asyncio.wait_for(
                    self._closed.wait(),
                    timeout=self._config.cycle_interval_seconds,
                )
            except asyncio.TimeoutError:
                continue

    async def _execute_cycle(self) -> None:
        started_at = self._now()
        monotonic_started = time.perf_counter()
        cycle_id = f"continuous_{uuid4().hex}"
        self._status.status = "scanning"
        self._status.cycle_id = cycle_id
        self._status.last_cycle_started_at = started_at
        self._status.last_error = None
        self._status.warnings = []
        self._persist_state()
        self._repository.upsert_continuous_intelligence_cycle(
            ContinuousIntelligenceCycleRecord(
                cycle_id=cycle_id,
                started_at=started_at,
                completed_at=None,
                status="running",
                universe_source=self._status.universe_source,
                total_symbols=0,
                fast_screened_symbols=0,
                deep_analyzed_symbols=0,
                candidate_count=0,
                failed_symbols=(),
                error_message=None,
                duration_ms=None,
            )
        )
        failed_symbols: list[str] = []
        try:
            await self._refresh_universes_if_needed()
            symbol_jobs = [
                (market, symbol)
                for market in self._config.markets
                for symbol in self._universes[market]
            ]
            self._status.total_symbols = len(symbol_jobs)
            fast_results = await self._fast_screen_universe(symbol_jobs, failed_symbols)
            fast_results = self._apply_relative_strength(fast_results)
            deep_queue = sorted(
                [item for item in fast_results if item.fast_score >= self._config.fast_score_threshold],
                key=lambda item: (-item.fast_score, item.market, item.symbol),
            )[: self._config.deep_candidate_limit]
            self._status.deep_queue_depth = len(deep_queue)
            self._persist_state()
            deep_results = await self._deep_analyze_candidates(deep_queue, failed_symbols)
            deep_lookup = {(item.market, item.symbol): item for item in deep_results}
            final = [deep_lookup.get((item.market, item.symbol), item) for item in fast_results]
            records = [self._candidate_to_record(item) for item in final]
            self._repository.upsert_continuous_intelligence_candidates(records)
            for market in self._config.markets:
                self._repository.delete_stale_continuous_intelligence_candidates(
                    market=market,
                    active_symbols=self._universes[market],
                )
            completed_at = self._now()
            self._status.status = "degraded" if failed_symbols else "running"
            self._status.last_cycle_completed_at = completed_at
            self._status.last_full_universe_pass_at = completed_at
            self._status.fast_screened_symbols = len(fast_results)
            self._status.deep_analyzed_symbols = len(deep_results)
            self._status.deep_queue_depth = 0
            self._status.successful_cycles += 1
            self._status.consecutive_failures = 0
            if failed_symbols:
                self._status.warnings = [
                    f"{len(set(failed_symbols))} symbols failed; the completed universe pass is partial."
                ]
            duration_ms = int((time.perf_counter() - monotonic_started) * 1000)
            self._repository.upsert_continuous_intelligence_cycle(
                ContinuousIntelligenceCycleRecord(
                    cycle_id=cycle_id,
                    started_at=started_at,
                    completed_at=completed_at,
                    status="partial" if failed_symbols else "completed",
                    universe_source=self._status.universe_source,
                    total_symbols=len(symbol_jobs),
                    fast_screened_symbols=len(fast_results),
                    deep_analyzed_symbols=len(deep_results),
                    candidate_count=len(deep_queue),
                    failed_symbols=tuple(dict.fromkeys(failed_symbols)),
                    error_message=None,
                    duration_ms=duration_ms,
                )
            )
            self._persist_state()
        except Exception as exc:
            completed_at = self._now()
            self._record_cycle_failure(exc)
            self._repository.upsert_continuous_intelligence_cycle(
                ContinuousIntelligenceCycleRecord(
                    cycle_id=cycle_id,
                    started_at=started_at,
                    completed_at=completed_at,
                    status="failed",
                    universe_source=self._status.universe_source,
                    total_symbols=self._status.total_symbols,
                    fast_screened_symbols=self._status.fast_screened_symbols,
                    deep_analyzed_symbols=self._status.deep_analyzed_symbols,
                    candidate_count=0,
                    failed_symbols=tuple(dict.fromkeys(failed_symbols)),
                    error_message=f"{type(exc).__name__}: {exc}"[:500],
                    duration_ms=int((time.perf_counter() - monotonic_started) * 1000),
                )
            )
            raise

    async def _refresh_universes_if_needed(self) -> None:
        now = self._now()
        refresh = (
            self._status.last_universe_refresh_at is None
            or now - self._status.last_universe_refresh_at
            >= timedelta(seconds=self._config.universe_refresh_seconds)
            or any(not self._universes[market] for market in self._config.markets)
        )
        if not refresh:
            return
        sources: list[str] = []
        for market in self._config.markets:
            try:
                if market == "spot":
                    symbols, volumes = await self._load_spot_universe()
                else:
                    symbols, volumes = await self._load_futures_universe()
                if not symbols:
                    raise ValueError(f"No active {market} symbols were returned.")
                self._universes[market] = symbols
                self._ticker_quote_volumes.update({(market, symbol): value for symbol, value in volumes.items()})
                self._universe_sources[market] = "live"
            except Exception as exc:
                fallback = self._fallback_universe(market)
                if not fallback:
                    raise
                self._universes[market] = fallback
                self._universe_sources[market] = "persisted_fallback"
                self._status.warnings.append(
                    f"{market.title()} universe refresh failed; using persisted/configured fallback: {type(exc).__name__}."
                )
            sources.append(f"{market}:{self._universe_sources[market]}")
        self._status.universe_source = ",".join(sources)
        self._status.last_universe_refresh_at = now
        self._persist_state()

    async def _load_spot_universe(self) -> tuple[list[str], dict[str, Decimal]]:
        records = await self._call_with_retry(lambda: self._spot_symbol_service.list_symbols(refresh=True))
        supported = [
            item.symbol
            for item in records
            if item.quote_asset.upper() == self._config.quote_asset and item.status.upper() == "TRADING"
        ]
        tickers = await self._call_with_retry(self._rest_client.get_ticker_24h)
        return self._rank_universe(supported, tickers)

    async def _load_futures_universe(self) -> tuple[list[str], dict[str, Decimal]]:
        payload = await self._call_with_retry(self._rest_client.get_futures_exchange_info)
        raw_symbols = payload.get("symbols", []) if isinstance(payload, Mapping) else []
        supported = [
            str(item.get("symbol", "")).upper()
            for item in raw_symbols
            if isinstance(item, Mapping)
            and str(item.get("quoteAsset", "")).upper() == self._config.quote_asset
            and str(item.get("status", "")).upper() == "TRADING"
            and str(item.get("contractType", "PERPETUAL")).upper() == "PERPETUAL"
        ]
        tickers = await self._call_with_retry(self._rest_client.get_futures_ticker_24h)
        return self._rank_universe(supported, tickers)

    def _rank_universe(
        self,
        supported: Sequence[str],
        tickers: Sequence[Mapping[str, object]],
    ) -> tuple[list[str], dict[str, Decimal]]:
        allowed = set(supported)
        volumes = {
            str(item.get("symbol", "")).upper(): _decimal_or_zero(item.get("quoteVolume"))
            for item in tickers
            if str(item.get("symbol", "")).upper() in allowed
        }
        ranked = sorted(allowed, key=lambda symbol: (-volumes.get(symbol, Decimal("0")), symbol))
        return ranked[: self._config.universe_limit], volumes

    def _fallback_universe(self, market: MarketName) -> list[str]:
        persisted = [
            item.symbol
            for item in self._repository.get_continuous_intelligence_candidates(
                market=market,
                limit=self._config.universe_limit,
            )
        ]
        configured = [
            symbol
            for symbol in self._settings.symbol_list
            if symbol.endswith(self._config.quote_asset)
        ]
        return list(dict.fromkeys(persisted + configured))[: self._config.universe_limit]

    async def _fast_screen_universe(
        self,
        jobs: Sequence[tuple[MarketName, str]],
        failed_symbols: list[str],
    ) -> list[ContinuousIntelligenceCandidate]:
        async def screen(market: MarketName, symbol: str) -> ContinuousIntelligenceCandidate | None:
            try:
                candles, source = await self._load_candles(
                    market=market,
                    symbol=symbol,
                    interval="5m",
                    limit=60,
                )
                return self._fast_screen_symbol(
                    market=market,
                    symbol=symbol,
                    candles=candles,
                    data_source=source,
                )
            except Exception as exc:
                failed_symbols.append(f"{market}:{symbol}")
                LOGGER.warning("Continuous fast screen failed market=%s symbol=%s error=%s", market, symbol, exc)
                return None

        results = await asyncio.gather(*(screen(market, symbol) for market, symbol in jobs))
        return [item for item in results if item is not None]

    def _fast_screen_symbol(
        self,
        *,
        market: MarketName,
        symbol: str,
        candles: Sequence[Candle],
        data_source: str,
    ) -> ContinuousIntelligenceCandidate:
        now = self._now()
        if len(candles) < 24:
            return ContinuousIntelligenceCandidate(
                market=market,
                symbol=symbol,
                stage="insufficient_data",
                fast_score=0,
                deep_score=None,
                direction_hint="neutral",
                current_price=candles[-1].close if candles else self._live_prices.get((market, symbol)),
                triggers=(),
                metrics={"candle_count": len(candles)},
                reasons=("At least 24 closed 5m candles are required for fast screening.",),
                warnings=("Fast screen has insufficient candle history.",),
                screened_at=now,
                deep_analyzed_at=None,
                data_source=data_source,
            )
        recent = list(candles[-24:])
        close = recent[-1].close
        return_3 = _return_pct(recent[-4].close, close)
        return_12 = _return_pct(recent[-13].close, close)
        prior_return_3 = _return_pct(recent[-7].close, recent[-4].close)
        recent_range = _average_range_ratio(recent[-6:])
        prior_range = _average_range_ratio(recent[:18])
        compression_ratio = recent_range / prior_range if prior_range > 0 else Decimal("1")
        average_volume = sum((item.volume for item in recent[-12:-1]), Decimal("0")) / Decimal("11")
        volume_ratio = recent[-1].volume / average_volume if average_volume > 0 else Decimal("0")
        range_low = min(item.low for item in recent)
        range_high = max(item.high for item in recent)
        range_position = (
            ((close - range_low) / (range_high - range_low)) * Decimal("100")
            if range_high > range_low
            else Decimal("50")
        )
        quote_volume = self._ticker_quote_volumes.get((market, symbol), Decimal("0"))
        liquidity_score = _liquidity_score(quote_volume)
        triggers: list[str] = []
        score = liquidity_score
        if compression_ratio <= Decimal("0.70"):
            triggers.append("volatility_compression")
            score += 25
        if abs(return_3) >= abs(prior_return_3) * Decimal("1.5") and abs(return_3) >= Decimal("0.25"):
            triggers.append("momentum_acceleration")
            score += 20
        if volume_ratio >= Decimal("1.30"):
            triggers.append("volume_expansion")
            score += 20
        if range_position <= Decimal("15"):
            triggers.append("lower_range_edge")
            score += 15
        elif range_position >= Decimal("85"):
            triggers.append("upper_range_edge")
            score += 15
        score += min(10, int(abs(return_12) * Decimal("2")))
        direction = _direction_hint(return_3=return_3, return_12=return_12, range_position=range_position)
        price = self._live_prices.get((market, symbol), close)
        return ContinuousIntelligenceCandidate(
            market=market,
            symbol=symbol,
            stage="screened",
            fast_score=max(0, min(100, score)),
            deep_score=None,
            direction_hint=direction,
            current_price=price,
            triggers=tuple(triggers),
            metrics={
                "candle_count": len(candles),
                "return_3_candles_pct": _q(return_3),
                "return_12_candles_pct": _q(return_12),
                "compression_ratio": _q(compression_ratio),
                "volume_expansion_ratio": _q(volume_ratio),
                "range_position_pct": _q(range_position),
                "quote_volume_24h": quote_volume,
                "liquidity_score": liquidity_score,
            },
            reasons=tuple(_fast_reasons(triggers, direction)),
            warnings=(),
            screened_at=now,
            deep_analyzed_at=None,
            data_source=data_source,
        )

    def _apply_relative_strength(
        self,
        candidates: Sequence[ContinuousIntelligenceCandidate],
    ) -> list[ContinuousIntelligenceCandidate]:
        updated: list[ContinuousIntelligenceCandidate] = []
        for market in self._config.markets:
            market_items = [item for item in candidates if item.market == market]
            returns = [
                Decimal(str(item.metrics["return_12_candles_pct"]))
                for item in market_items
                if "return_12_candles_pct" in item.metrics
            ]
            benchmark = Decimal(str(median(returns))) if returns else Decimal("0")
            for item in market_items:
                if "return_12_candles_pct" not in item.metrics:
                    updated.append(item)
                    continue
                relative = Decimal(str(item.metrics["return_12_candles_pct"])) - benchmark
                triggers = list(item.triggers)
                score = item.fast_score
                if relative >= Decimal("1"):
                    triggers.append("relative_strength")
                    score += 10
                elif relative <= Decimal("-1"):
                    triggers.append("relative_weakness")
                    score += 10
                metrics = dict(item.metrics)
                metrics["market_median_return_12_pct"] = _q(benchmark)
                metrics["relative_return_12_pct"] = _q(relative)
                updated.append(
                    replace(
                        item,
                        fast_score=min(100, score),
                        triggers=tuple(dict.fromkeys(triggers)),
                        metrics=metrics,
                        reasons=tuple(_fast_reasons(triggers, item.direction_hint)),
                    )
                )
        return updated

    async def _deep_analyze_candidates(
        self,
        candidates: Sequence[ContinuousIntelligenceCandidate],
        failed_symbols: list[str],
    ) -> list[ContinuousIntelligenceCandidate]:
        async def analyze(item: ContinuousIntelligenceCandidate) -> ContinuousIntelligenceCandidate | None:
            try:
                candles_15m, source_15m = await self._load_candles(
                    market=item.market,
                    symbol=item.symbol,
                    interval="15m",
                    limit=96,
                )
                candles_1h, source_1h = await self._load_candles(
                    market=item.market,
                    symbol=item.symbol,
                    interval="1h",
                    limit=72,
                )
                return self._deep_analyze_symbol(
                    candidate=item,
                    candles_15m=candles_15m,
                    candles_1h=candles_1h,
                    data_source=f"{source_15m}+{source_1h}",
                )
            except Exception as exc:
                failed_symbols.append(f"{item.market}:{item.symbol}:deep")
                LOGGER.warning("Continuous deep analysis failed market=%s symbol=%s error=%s", item.market, item.symbol, exc)
                return replace(
                    item,
                    stage="deep_failed",
                    warnings=(f"Deep analysis failed: {type(exc).__name__}.",),
                )
            finally:
                self._status.deep_queue_depth = max(0, self._status.deep_queue_depth - 1)

        results = await asyncio.gather(*(analyze(item) for item in candidates))
        return [item for item in results if item is not None]

    def _deep_analyze_symbol(
        self,
        *,
        candidate: ContinuousIntelligenceCandidate,
        candles_15m: Sequence[Candle],
        candles_1h: Sequence[Candle],
        data_source: str,
    ) -> ContinuousIntelligenceCandidate:
        if len(candles_15m) < 24 or len(candles_1h) < 21:
            return replace(
                candidate,
                stage="deep_insufficient_data",
                warnings=("Deep analysis requires 24 closed 15m candles and 21 closed 1h candles.",),
                deep_analyzed_at=self._now(),
                data_source=data_source,
            )
        closes_15m = [item.close for item in candles_15m]
        closes_1h = [item.close for item in candles_1h]
        short_15m = _average(closes_15m[-9:])
        long_15m = _average(closes_15m[-21:])
        short_1h = _average(closes_1h[-9:])
        long_1h = _average(closes_1h[-21:])
        trend_15m = _trend(short_15m, long_15m)
        trend_1h = _trend(short_1h, long_1h)
        momentum = _return_pct(closes_15m[-5], closes_15m[-1])
        recent = list(candles_15m[-48:])
        support = min(item.low for item in recent)
        resistance = max(item.high for item in recent)
        price = closes_15m[-1]
        range_position = (
            ((price - support) / (resistance - support)) * Decimal("100")
            if resistance > support
            else Decimal("50")
        )
        volatility = _average_range_ratio(candles_15m[-24:]) * Decimal("100")
        direction = candidate.direction_hint
        if trend_15m == trend_1h and trend_15m != "neutral":
            direction = trend_15m
        score = Decimal(candidate.fast_score) * Decimal("0.35")
        reasons = list(candidate.reasons)
        warnings: list[str] = []
        if trend_15m == trend_1h and trend_15m != "neutral":
            score += Decimal("25")
            reasons.append(f"15m and 1h trends align {trend_15m}.")
        elif trend_15m != trend_1h:
            warnings.append("15m and 1h trend directions conflict.")
        if direction == "bullish" and momentum > Decimal("0.25"):
            score += Decimal("20")
            reasons.append("15m momentum confirms the bullish direction.")
        elif direction == "bearish" and momentum < Decimal("-0.25"):
            score += Decimal("20")
            reasons.append("15m momentum confirms the bearish direction.")
        if range_position <= Decimal("20") or range_position >= Decimal("80"):
            score += Decimal("15")
            reasons.append("Price is interacting with a multi-hour range boundary.")
        if Decimal("0.10") <= volatility <= Decimal("2.50"):
            score += Decimal("10")
        else:
            warnings.append("Volatility is outside the preferred deep-analysis band.")
        deep_score = max(0, min(100, int(score.quantize(Decimal("1"), rounding=ROUND_HALF_UP))))
        stage = "deep_candidate" if deep_score >= 55 and direction != "neutral" else "deep_watch"
        metrics = dict(candidate.metrics)
        metrics.update(
            {
                "trend_15m": trend_15m,
                "trend_1h": trend_1h,
                "momentum_15m_pct": _q(momentum),
                "support": support,
                "resistance": resistance,
                "deep_range_position_pct": _q(range_position),
                "realized_range_volatility_pct": _q(volatility),
                "multi_timeframe_aligned": trend_15m == trend_1h and trend_15m != "neutral",
            }
        )
        return replace(
            candidate,
            stage=stage,
            deep_score=deep_score,
            direction_hint=direction,
            current_price=self._live_prices.get((candidate.market, candidate.symbol), price),
            metrics=metrics,
            reasons=tuple(dict.fromkeys(reasons)),
            warnings=tuple(warnings),
            deep_analyzed_at=self._now(),
            data_source=data_source,
        )

    async def _load_candles(
        self,
        *,
        market: MarketName,
        symbol: str,
        interval: str,
        limit: int,
    ) -> tuple[list[Candle], str]:
        end = self._now()
        duration = interval_to_timedelta(interval)  # type: ignore[arg-type]
        start = end - duration * (limit + 4)
        loader = (
            self._repository.get_futures_historical_candles
            if market == "futures"
            else self._repository.get_historical_candles
        )
        stored_records = loader(
            symbol=symbol,
            interval=interval,
            start_time=start,
            end_time=end,
            limit=None,
        )
        stored = [_record_to_candle(item) for item in stored_records][-limit:]
        fresh = bool(
            stored
            and len(stored) >= min(24, limit)
            and end - stored[-1].close_time <= duration + timedelta(seconds=45)
        )
        if fresh:
            return stored, f"{market}_sqlite_cache"
        try:
            if market == "futures":
                rows = await self._call_with_retry(
                    lambda: self._rest_client.get_futures_klines(
                        symbol=symbol,
                        interval=interval,
                        start_time_ms=int(start.timestamp() * 1000),
                        end_time_ms=int(end.timestamp() * 1000),
                        limit=limit,
                    )
                )
            else:
                rows = await self._call_with_retry(
                    lambda: self._rest_client.get_klines(
                        symbol=symbol,
                        interval=interval,
                        start_time_ms=int(start.timestamp() * 1000),
                        end_time_ms=int(end.timestamp() * 1000),
                        limit=limit,
                    )
                )
            fetched = [
                parse_rest_kline(symbol, interval, row)  # type: ignore[arg-type]
                for row in rows
                if len(row) >= 9 and int(row[6]) < int(end.timestamp() * 1000)
            ]
            if fetched:
                if market == "futures":
                    self._repository.upsert_futures_historical_candles(
                        fetched,
                        source="continuous_intelligence_rest",
                    )
                else:
                    self._repository.upsert_historical_candles(
                        fetched,
                        source="continuous_intelligence_rest",
                    )
                return fetched[-limit:], f"binance_{market}_rest"
        except Exception:
            if not stored:
                raise
            LOGGER.warning("Using stale continuous-intelligence candle cache market=%s symbol=%s interval=%s", market, symbol, interval)
        return stored, f"{market}_sqlite_stale_fallback"

    async def _call_with_retry(
        self,
        operation: Callable[[], Awaitable[T]],
        *,
        attempts: int = 3,
        timeout_seconds: float = 10.0,
    ) -> T:
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                async with self._request_semaphore:
                    await self._respect_request_interval()
                    return await asyncio.wait_for(operation(), timeout=timeout_seconds)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_error = exc
                if attempt + 1 < attempts:
                    await asyncio.sleep(0.2 * (attempt + 1))
        assert last_error is not None
        raise last_error

    async def _respect_request_interval(self) -> None:
        async with self._request_lock:
            now = time.monotonic()
            delay = self._next_request_at - now
            if delay > 0:
                await asyncio.sleep(delay)
            self._next_request_at = time.monotonic() + self._config.request_interval_ms / 1000

    def _start_websocket_tasks(self) -> None:
        clients = {
            "spot": self._spot_websocket_client,
            "futures": self._futures_websocket_client,
        }
        self._websocket_tasks = [
            asyncio.create_task(
                self._websocket_loop(market, clients[market]),
                name=f"continuous-{market}-mini-ticker",
            )
            for market in self._config.markets
            if clients[market] is not None
        ]

    async def _websocket_loop(
        self,
        market: MarketName,
        client: BinanceWebSocketClient | None,
    ) -> None:
        if client is None:
            return
        try:
            async for payload in client.messages(["!miniTicker@arr"]):
                self.process_websocket_payload(market=market, payload=payload)
                if self._closed.is_set():
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - client already reconnects
            self._status.warnings.append(f"{market.title()} WebSocket listener failed: {type(exc).__name__}.")
            LOGGER.exception("Continuous %s mini-ticker listener stopped.", market)

    def process_websocket_payload(self, *, market: MarketName, payload: object) -> int:
        """Apply one all-market mini-ticker payload and return accepted event count."""

        raw = payload.get("data", payload) if isinstance(payload, Mapping) else payload
        items = raw if isinstance(raw, list) else [raw]
        accepted = 0
        watched = set(self._universes.get(market, []))
        if not watched:
            return 0
        latest_event: datetime | None = None
        for item in items:
            if not isinstance(item, Mapping):
                continue
            symbol = str(item.get("s", "")).upper()
            if watched and symbol not in watched:
                continue
            try:
                price = Decimal(str(item.get("c")))
            except (InvalidOperation, TypeError, ValueError):
                continue
            if not symbol or price <= 0:
                continue
            event_ms = item.get("E")
            event_time = (
                datetime.fromtimestamp(int(event_ms) / 1000, tz=UTC)
                if event_ms is not None
                else self._now()
            )
            self._live_prices[(market, symbol)] = price
            latest_event = max(latest_event, event_time) if latest_event else event_time
            accepted += 1
        if accepted:
            self._status.last_websocket_event_at = latest_event or self._now()
            self._status.websocket_events += accepted
            checkpoint_time = self._now()
            if (
                self._last_websocket_checkpoint_at is None
                or checkpoint_time - self._last_websocket_checkpoint_at >= timedelta(seconds=30)
            ):
                self._last_websocket_checkpoint_at = checkpoint_time
                self._persist_state()
        return accepted

    async def _cancel_tasks(self) -> None:
        self._closed.set()
        tasks = [item for item in [self._task, *self._websocket_tasks] if item is not None]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._task = None
        self._websocket_tasks = []

    def _record_cycle_failure(self, exc: Exception) -> None:
        self._status.status = "error" if self._status.consecutive_failures >= 2 else "degraded"
        self._status.last_error = f"{type(exc).__name__}: {exc}"[:500]
        self._status.failed_cycles += 1
        self._status.consecutive_failures += 1
        self._status.deep_queue_depth = 0
        self._persist_state()

    def _restore_checkpoint(self) -> None:
        persisted = self._repository.get_continuous_intelligence_state()
        if persisted is None:
            self._persist_state()
            return
        try:
            raw = json.loads(persisted.config_json)
            persisted_config = ContinuousIntelligenceConfig(
                enabled=bool(raw.get("enabled", persisted.enabled)),
                markets=tuple(raw.get("markets", self._config.markets)),
                quote_asset=str(raw.get("quote_asset", self._config.quote_asset)),
                universe_limit=int(raw.get("universe_limit", self._config.universe_limit)),
                cycle_interval_seconds=int(raw.get("cycle_interval_seconds", self._config.cycle_interval_seconds)),
                universe_refresh_seconds=int(raw.get("universe_refresh_seconds", self._config.universe_refresh_seconds)),
                deep_candidate_limit=int(raw.get("deep_candidate_limit", self._config.deep_candidate_limit)),
                fast_score_threshold=int(raw.get("fast_score_threshold", self._config.fast_score_threshold)),
                concurrency=int(raw.get("concurrency", self._config.concurrency)),
                request_interval_ms=int(raw.get("request_interval_ms", self._config.request_interval_ms)),
                initial_delay_seconds=int(raw.get("initial_delay_seconds", self._config.initial_delay_seconds)),
            ).normalized()
            self._config = persisted_config
        except (TypeError, ValueError, json.JSONDecodeError):
            LOGGER.warning("Ignoring invalid persisted continuous-intelligence configuration.")
        recovered_status: ServiceStatus = "paused" if persisted.status == "paused" else "stopped"
        self._status = ContinuousIntelligenceStatus(
            enabled=persisted.enabled,
            status=recovered_status,
            cycle_id=persisted.cycle_id,
            started_at=persisted.started_at,
            last_cycle_started_at=persisted.last_cycle_started_at,
            last_cycle_completed_at=persisted.last_cycle_completed_at,
            last_full_universe_pass_at=persisted.last_full_universe_pass_at,
            last_universe_refresh_at=persisted.last_universe_refresh_at,
            last_websocket_event_at=persisted.last_websocket_event_at,
            next_cycle_at=None,
            last_error=persisted.last_error,
            universe_source=persisted.universe_source,
            total_symbols=persisted.total_symbols,
            fast_screened_symbols=persisted.fast_screened_symbols,
            deep_analyzed_symbols=persisted.deep_analyzed_symbols,
            deep_queue_depth=0,
            successful_cycles=persisted.successful_cycles,
            failed_cycles=persisted.failed_cycles,
            consecutive_failures=persisted.consecutive_failures,
            config=self._config,
        )

    def _persist_state(self) -> None:
        now = self._now()
        self._repository.upsert_continuous_intelligence_state(
            ContinuousIntelligenceStateRecord(
                enabled=self._status.enabled,
                status=self._status.status,
                cycle_id=self._status.cycle_id,
                started_at=self._status.started_at,
                last_cycle_started_at=self._status.last_cycle_started_at,
                last_cycle_completed_at=self._status.last_cycle_completed_at,
                last_full_universe_pass_at=self._status.last_full_universe_pass_at,
                last_universe_refresh_at=self._status.last_universe_refresh_at,
                last_websocket_event_at=self._status.last_websocket_event_at,
                next_cycle_at=self._status.next_cycle_at,
                last_error=self._status.last_error,
                universe_source=self._status.universe_source,
                total_symbols=self._status.total_symbols,
                fast_screened_symbols=self._status.fast_screened_symbols,
                deep_analyzed_symbols=self._status.deep_analyzed_symbols,
                deep_queue_depth=self._status.deep_queue_depth,
                successful_cycles=self._status.successful_cycles,
                failed_cycles=self._status.failed_cycles,
                consecutive_failures=self._status.consecutive_failures,
                config_json=json.dumps(asdict(self._config)),
                updated_at=now,
            )
        )

    @staticmethod
    def _candidate_to_record(
        item: ContinuousIntelligenceCandidate,
    ) -> ContinuousIntelligenceCandidateRecord:
        return ContinuousIntelligenceCandidateRecord(
            market=item.market,
            symbol=item.symbol,
            stage=item.stage,
            fast_score=item.fast_score,
            deep_score=item.deep_score,
            direction_hint=item.direction_hint,
            current_price=item.current_price,
            triggers=item.triggers,
            metrics_json=json.dumps(item.metrics, default=str, sort_keys=True),
            reasons=item.reasons,
            warnings=item.warnings,
            screened_at=item.screened_at,
            deep_analyzed_at=item.deep_analyzed_at,
            data_source=item.data_source,
        )

    @staticmethod
    def _candidate_from_record(
        item: ContinuousIntelligenceCandidateRecord,
    ) -> ContinuousIntelligenceCandidate:
        try:
            metrics = json.loads(item.metrics_json)
        except json.JSONDecodeError:
            metrics = {}
        return ContinuousIntelligenceCandidate(
            market=item.market,  # type: ignore[arg-type]
            symbol=item.symbol,
            stage=item.stage,
            fast_score=item.fast_score,
            deep_score=item.deep_score,
            direction_hint=item.direction_hint,
            current_price=item.current_price,
            triggers=item.triggers,
            metrics=metrics if isinstance(metrics, dict) else {},
            reasons=item.reasons,
            warnings=item.warnings,
            screened_at=item.screened_at,
            deep_analyzed_at=item.deep_analyzed_at,
            data_source=item.data_source,
        )


def _record_to_candle(record: HistoricalCandleRecord) -> Candle:
    return Candle(
        symbol=record.symbol,
        timeframe=record.interval,
        open=record.open_price,
        high=record.high_price,
        low=record.low_price,
        close=record.close_price,
        volume=record.volume,
        quote_volume=record.quote_volume,
        open_time=record.open_time,
        close_time=record.close_time,
        event_time=record.created_at,
        trade_count=record.trade_count,
        is_closed=True,
    )


def _return_pct(start: Decimal, end: Decimal) -> Decimal:
    return ((end - start) / start) * Decimal("100") if start > 0 else Decimal("0")


def _average(values: Sequence[Decimal]) -> Decimal:
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else Decimal("0")


def _average_range_ratio(candles: Sequence[Candle]) -> Decimal:
    values = [(item.high - item.low) / item.close for item in candles if item.close > 0]
    return _average(values)


def _liquidity_score(quote_volume: Decimal) -> int:
    if quote_volume >= Decimal("100000000"):
        return 20
    if quote_volume >= Decimal("10000000"):
        return 16
    if quote_volume >= Decimal("1000000"):
        return 12
    if quote_volume >= Decimal("100000"):
        return 6
    return 0


def _direction_hint(*, return_3: Decimal, return_12: Decimal, range_position: Decimal) -> str:
    combined = return_3 * Decimal("0.6") + return_12 * Decimal("0.4")
    if combined >= Decimal("0.15") or (range_position >= Decimal("85") and return_3 > 0):
        return "bullish"
    if combined <= Decimal("-0.15") or (range_position <= Decimal("15") and return_3 < 0):
        return "bearish"
    return "neutral"


def _fast_reasons(triggers: Sequence[str], direction: str) -> list[str]:
    labels = {
        "volatility_compression": "Volatility is compressing before a potential expansion.",
        "momentum_acceleration": "Short-horizon momentum is accelerating.",
        "volume_expansion": "Latest closed-candle volume expanded above its recent baseline.",
        "lower_range_edge": "Price is near the lower edge of its recent range.",
        "upper_range_edge": "Price is near the upper edge of its recent range.",
        "relative_strength": "The symbol is outperforming the current market universe.",
        "relative_weakness": "The symbol is underperforming the current market universe.",
    }
    reasons = [labels[item] for item in triggers if item in labels]
    if direction != "neutral":
        reasons.append(f"Fast-screen direction is {direction}.")
    return reasons or ["No priority fast-screen trigger is active."]


def _trend(short_average: Decimal, long_average: Decimal) -> str:
    if long_average <= 0:
        return "neutral"
    gap = (short_average - long_average) / long_average
    if gap >= Decimal("0.001"):
        return "bullish"
    if gap <= Decimal("-0.001"):
        return "bearish"
    return "neutral"


def _decimal_or_zero(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
