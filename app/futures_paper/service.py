"""Paper Futures runtime service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from app.futures_paper.broker import FuturesPaperBroker
from app.futures_paper.models import FuturesFillResult, FuturesOrderRequest, FuturesPosition, FuturesSignal, FuturesSignalInput
from app.futures_paper.risk import FuturesPaperRiskEngine
from app.futures_paper.signal_engine import FuturesSignalEngine
from app.storage.models import FuturesPaperPositionRecord
from app.storage.repositories import StorageRepository


@dataclass(slots=True)
class FuturesPaperStatus:
    """Current Futures paper runtime status."""

    active: bool
    mode: str
    paper_only: bool
    positions: list[FuturesPosition]
    realized_pnl: Decimal


class FuturesPaperService:
    """Paper-only Futures service with deterministic risk checks."""

    def __init__(
        self,
        *,
        repository: StorageRepository,
        broker: FuturesPaperBroker | None = None,
        risk_engine: FuturesPaperRiskEngine | None = None,
        signal_engine: FuturesSignalEngine | None = None,
    ) -> None:
        self.repository = repository
        self.broker = broker or FuturesPaperBroker()
        self.risk_engine = risk_engine or FuturesPaperRiskEngine()
        self.signal_engine = signal_engine or FuturesSignalEngine()
        self.active = False
        self.broker.load_positions([self._from_record(record) for record in repository.get_futures_paper_positions()])

    def status(self) -> FuturesPaperStatus:
        """Return runtime status."""

        return FuturesPaperStatus(
            active=self.active,
            mode="paper",
            paper_only=True,
            positions=list(self.broker.positions().values()),
            realized_pnl=self.broker.realized_pnl,
        )

    def start(self) -> FuturesPaperStatus:
        """Start paper Futures runtime."""

        self.active = True
        self._event("runtime_started", "ALL", {"paper_only": True})
        return self.status()

    def stop(self) -> FuturesPaperStatus:
        """Stop paper Futures runtime."""

        self.active = False
        self._event("runtime_stopped", "ALL", {"paper_only": True})
        return self.status()

    def signal(self, signal_input: FuturesSignalInput) -> FuturesSignal:
        """Evaluate deterministic Futures signal."""

        signal = self.signal_engine.evaluate(signal_input)
        self._event(
            "signal_generated",
            signal.symbol,
            {"side": signal.side, "confidence": signal.confidence, "reason_codes": signal.reason_codes},
        )
        return signal

    def manual_open(
        self,
        *,
        symbol: str,
        side: str,
        quantity: Decimal,
        market_price: Decimal,
        leverage: int = 2,
    ) -> FuturesFillResult:
        """Open a manual LONG or SHORT paper Futures position."""

        order = FuturesOrderRequest(
            symbol=symbol.upper(),
            side=side,  # type: ignore[arg-type]
            quantity=quantity,
            market_price=market_price,
            leverage=leverage,
            mode="paper",
        )
        return self._execute(order)

    def manual_close(self, *, symbol: str, market_price: Decimal) -> FuturesFillResult:
        """Close the current paper Futures position."""

        position = self.broker.get_position(symbol)
        order = FuturesOrderRequest(
            symbol=symbol.upper(),
            side="CLOSE",
            quantity=position.quantity if position is not None else Decimal("1"),
            market_price=market_price,
            leverage=position.leverage if position is not None else self.risk_engine.default_leverage,
            mode="paper",
        )
        return self._execute(order)

    def performance(self, symbol: str | None = None) -> dict[str, object]:
        """Return simple paper Futures performance summary."""

        fills = self.repository.get_futures_paper_fills(symbol=symbol, limit=500)
        realized = sum((fill.realized_pnl for fill in fills), Decimal("0"))
        return {
            "symbol": symbol.upper() if symbol else None,
            "paper_only": True,
            "total_fills": len(fills),
            "realized_pnl": realized,
            "positions": list(self.broker.positions().values()),
            "recent_fills": fills[:25],
        }

    def _execute(self, order: FuturesOrderRequest) -> FuturesFillResult:
        position = self.broker.get_position(order.symbol)
        liquidation_distance = self._liquidation_distance(order, position)
        decision = self.risk_engine.evaluate(
            order,
            current_position=position,
            open_position_count=len(self.broker.positions()),
            liquidation_distance_pct=liquidation_distance,
        )
        result = self.broker.execute(order, approved=decision.approved, reason_codes=decision.reason_codes)
        now = datetime.now(UTC)
        self.repository.insert_futures_paper_fill(
            order_id=result.order_id,
            status=result.status,
            symbol=result.symbol,
            side=result.side,
            filled_quantity=result.filled_quantity,
            fill_price=result.fill_price,
            fee_paid=result.fee_paid,
            realized_pnl=result.realized_pnl,
            reason_codes=result.reason_codes,
            event_time=now,
        )
        updated_position = self.broker.mark_position(order.symbol, order.market_price)
        if result.status == "executed" and order.side == "CLOSE":
            self.repository.delete_futures_paper_position(order.symbol)
        elif updated_position is not None:
            self.repository.upsert_futures_paper_position(self._to_record(updated_position))
        self.repository.insert_futures_paper_pnl_snapshot(
            symbol=order.symbol,
            snapshot_time=now,
            unrealized_pnl=updated_position.unrealized_pnl if updated_position is not None else Decimal("0"),
            realized_pnl=self.broker.realized_pnl,
        )
        self._event(
            "execution_result",
            order.symbol,
            {
                "status": result.status,
                "side": result.side,
                "reason_codes": result.reason_codes,
                "paper_only": True,
            },
            event_time=now,
        )
        return result

    def _event(
        self,
        event_type: str,
        symbol: str,
        payload: dict[str, object],
        *,
        event_time: datetime | None = None,
    ) -> None:
        self.repository.insert_futures_paper_event(
            event_type=event_type,
            symbol=symbol.upper(),
            payload=payload,
            event_time=event_time or datetime.now(UTC),
        )

    @staticmethod
    def _liquidation_distance(order: FuturesOrderRequest, position: FuturesPosition | None) -> Decimal | None:
        reference_price = position.entry_price if position is not None else order.market_price
        if reference_price <= Decimal("0"):
            return None
        liquidation = FuturesPaperBroker._liquidation_estimate(
            position.side if position is not None else order.side,
            reference_price,
            order.leverage,
        )
        return abs(order.market_price - liquidation) / order.market_price * Decimal("100")

    @staticmethod
    def _from_record(record: FuturesPaperPositionRecord) -> FuturesPosition:
        return FuturesPosition(
            symbol=record.symbol,
            side=record.side,  # type: ignore[arg-type]
            quantity=record.quantity,
            entry_price=record.entry_price,
            mark_price=record.mark_price,
            leverage=record.leverage,
            margin_mode="isolated",
            margin_used=record.margin_used,
            unrealized_pnl=record.unrealized_pnl,
            realized_pnl=record.realized_pnl,
            liquidation_price_estimate=record.liquidation_price_estimate,
            opened_at=record.opened_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _to_record(position: FuturesPosition) -> FuturesPaperPositionRecord:
        return FuturesPaperPositionRecord(
            symbol=position.symbol,
            side=position.side,
            quantity=position.quantity,
            entry_price=position.entry_price,
            mark_price=position.mark_price,
            leverage=position.leverage,
            margin_mode=position.margin_mode,
            margin_used=position.margin_used,
            unrealized_pnl=position.unrealized_pnl,
            realized_pnl=position.realized_pnl,
            liquidation_price_estimate=position.liquidation_price_estimate,
            opened_at=position.opened_at,
            updated_at=position.updated_at,
        )
