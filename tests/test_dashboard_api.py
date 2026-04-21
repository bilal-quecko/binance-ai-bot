from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dashboard_api import get_dashboard_data_access
from app.api.dependencies import DashboardDataAccess
from app.main import app
from app.paper.models import FillResult, Position
from app.risk.models import RiskDecision
from app.storage import StorageRepository
from app.storage.models import TradeRecord


def _db_path() -> Path:
    base = Path("tests/.tmp_storage")
    base.mkdir(parents=True, exist_ok=True)
    return (base / f"dashboard_{uuid4().hex}.sqlite").resolve()


def _seed_repository(repository: StorageRepository) -> None:
    base_time = datetime(2024, 3, 9, 16, 0, 0, tzinfo=UTC)
    next_day = datetime(2024, 3, 10, 10, 0, 0, tzinfo=UTC)
    trade_inputs = (
        ("PAPER-000001", "BTCUSDT", "BUY", Decimal("0"), Decimal("100"), Decimal("899.90"), base_time),
        ("PAPER-000002", "BTCUSDT", "SELL", Decimal("10"), Decimal("110"), Decimal("1009.79"), base_time + timedelta(minutes=1)),
        ("PAPER-000003", "ETHUSDT", "BUY", Decimal("0"), Decimal("105"), Decimal("799.58"), base_time + timedelta(minutes=2)),
        ("PAPER-000004", "ETHUSDT", "SELL", Decimal("-5"), Decimal("100"), Decimal("1004.48"), base_time + timedelta(minutes=3)),
        ("PAPER-000005", "BTCUSDT", "BUY", Decimal("0"), Decimal("120"), Decimal("884.36"), next_day),
    )
    for order_id, symbol, side, realized_pnl, fill_price, quote_balance, event_time in trade_inputs:
        fill = FillResult(
            order_id=order_id,
            status="executed",
            symbol=symbol,
            side=side,
            requested_quantity=Decimal("1"),
            filled_quantity=Decimal("1"),
            fill_price=fill_price,
            fee_paid=Decimal("0.1"),
            realized_pnl=realized_pnl,
            quote_balance=quote_balance,
            reason_codes=("EXECUTED",),
            position=None,
        )
        decision = RiskDecision(
            decision="approve",
            approved_quantity=Decimal("1"),
            reason_codes=("APPROVED",),
        )
        repository.insert_trade(
            fill_result=fill,
            risk_decision=decision,
            approved_quantity=Decimal("1"),
            event_time=event_time,
        )
        repository.insert_fill(fill, event_time)

    repository.insert_position_snapshot(None, base_time + timedelta(minutes=1), "BTCUSDT")
    repository.insert_position_snapshot(None, base_time + timedelta(minutes=3), "ETHUSDT")
    repository.insert_position_snapshot(
        Position(
            symbol="BTCUSDT",
            quantity=Decimal("1"),
            avg_entry_price=Decimal("120"),
            realized_pnl=Decimal("10"),
        ),
        next_day + timedelta(minutes=1),
        "BTCUSDT",
    )
    repository.insert_position_snapshot(
        Position(
            symbol="SOLUSDT",
            quantity=Decimal("3"),
            avg_entry_price=Decimal("20"),
            realized_pnl=Decimal("0"),
        ),
        next_day + timedelta(minutes=2),
        "SOLUSDT",
    )
    repository.insert_pnl_snapshot(
        snapshot_time=base_time - timedelta(hours=4),
        equity=Decimal("1000"),
        total_pnl=Decimal("0"),
        realized_pnl=Decimal("0"),
        cash_balance=Decimal("1000"),
    )
    repository.insert_pnl_snapshot(
        snapshot_time=base_time + timedelta(minutes=3),
        equity=Decimal("1005"),
        total_pnl=Decimal("5"),
        realized_pnl=Decimal("5"),
        cash_balance=Decimal("1004.48"),
    )
    repository.insert_pnl_snapshot(
        snapshot_time=next_day - timedelta(hours=1),
        equity=Decimal("1120"),
        total_pnl=Decimal("120"),
        realized_pnl=Decimal("5"),
        cash_balance=Decimal("900"),
    )
    repository.insert_pnl_snapshot(
        snapshot_time=next_day - timedelta(minutes=30),
        equity=Decimal("980"),
        total_pnl=Decimal("-20"),
        realized_pnl=Decimal("5"),
        cash_balance=Decimal("760"),
    )
    repository.insert_pnl_snapshot(
        snapshot_time=next_day + timedelta(minutes=2),
        equity=Decimal("1064"),
        total_pnl=Decimal("64"),
        realized_pnl=Decimal("5"),
        cash_balance=Decimal("824.36"),
    )
    repository.insert_event(
        event_type="signal_generated",
        symbol="BTCUSDT",
        message="signal=BUY",
        payload={"side": "BUY", "reason_codes": ("BULLISH_TREND",)},
        event_time=base_time,
    )
    repository.insert_event(
        event_type="execution_result",
        symbol="BTCUSDT",
        message="status=executed",
        payload={"status": "executed", "filled_quantity": "1"},
        event_time=base_time + timedelta(minutes=1),
    )
    repository.insert_event(
        event_type="signal_generated",
        symbol="ETHUSDT",
        message="signal=BUY",
        payload={"side": "BUY", "reason_codes": ("BULLISH_TREND",)},
        event_time=base_time + timedelta(minutes=2),
    )
    repository.insert_event(
        event_type="execution_result",
        symbol="ETHUSDT",
        message="status=executed",
        payload={"status": "executed", "filled_quantity": "1"},
        event_time=base_time + timedelta(minutes=3),
    )
    repository.insert_event(
        event_type="signal_generated",
        symbol="BTCUSDT",
        message="signal=BUY",
        payload={"side": "BUY", "reason_codes": ("BULLISH_TREND",)},
        event_time=next_day,
    )


def _make_client(db_path: Path) -> TestClient:
    def override_data_access():
        repository = StorageRepository(f"sqlite:///{db_path}")
        try:
            yield DashboardDataAccess(repository)
        finally:
            repository.close()

    app.dependency_overrides[get_dashboard_data_access] = override_data_access
    return TestClient(app)


def test_dashboard_api_core_endpoints() -> None:
    db_path = _db_path()
    repository = StorageRepository(f"sqlite:///{db_path}")
    try:
        _seed_repository(repository)
    finally:
        repository.close()

    client = _make_client(db_path)
    try:
        health_response = client.get("/health")
        positions_response = client.get("/positions")
        equity_response = client.get("/equity")
        daily_pnl_response = client.get("/daily-pnl", params={"day": "2024-03-10"})
        equity_history_response = client.get("/equity/history", params={"start_date": "2024-03-10"})
        pnl_history_response = client.get("/pnl/history")
        drawdown_response = client.get("/drawdown")
        metrics_response = client.get("/metrics")
        performance_response = client.get("/performance", params={"symbol": "BTCUSDT"})
    finally:
        app.dependency_overrides.clear()

    assert health_response.status_code == 200
    assert health_response.json()["storage"] == "sqlite"

    assert positions_response.status_code == 200
    assert positions_response.json() == [
        {
            "symbol": "BTCUSDT",
            "quantity": "1",
            "avg_entry_price": "120",
            "realized_pnl": "10",
            "quote_asset": "USDT",
            "snapshot_time": "2024-03-10T10:01:00Z",
        },
        {
            "symbol": "SOLUSDT",
            "quantity": "3",
            "avg_entry_price": "20",
            "realized_pnl": "0",
            "quote_asset": "USDT",
            "snapshot_time": "2024-03-10T10:02:00Z",
        },
    ]

    assert equity_response.status_code == 200
    assert equity_response.json() == {
        "snapshot_time": "2024-03-10T10:02:00Z",
        "equity": "1064",
        "total_pnl": "64",
        "realized_pnl": "5",
        "cash_balance": "824.36",
    }

    assert daily_pnl_response.status_code == 200
    assert daily_pnl_response.json() == "64"

    assert equity_history_response.status_code == 200
    assert equity_history_response.json() == [
        {
            "snapshot_time": "2024-03-10T09:00:00Z",
            "equity": "1120",
        },
        {
            "snapshot_time": "2024-03-10T09:30:00Z",
            "equity": "980",
        },
        {
            "snapshot_time": "2024-03-10T10:02:00Z",
            "equity": "1064",
        },
    ]

    assert pnl_history_response.status_code == 200
    assert pnl_history_response.json() == {
        "points": [
            {
                "snapshot_time": "2024-03-09T12:00:00Z",
                "total_pnl": "0",
                "realized_pnl": "0",
            },
            {
                "snapshot_time": "2024-03-09T16:03:00Z",
                "total_pnl": "5",
                "realized_pnl": "5",
            },
            {
                "snapshot_time": "2024-03-10T09:00:00Z",
                "total_pnl": "120",
                "realized_pnl": "5",
            },
            {
                "snapshot_time": "2024-03-10T09:30:00Z",
                "total_pnl": "-20",
                "realized_pnl": "5",
            },
            {
                "snapshot_time": "2024-03-10T10:02:00Z",
                "total_pnl": "64",
                "realized_pnl": "5",
            },
        ],
        "daily": [
            {
                "day": "2024-03-09",
                "total_pnl": "5",
                "realized_pnl": "5",
            },
            {
                "day": "2024-03-10",
                "total_pnl": "64",
                "realized_pnl": "5",
            },
        ],
    }

    assert drawdown_response.status_code == 200
    assert drawdown_response.json() == {
        "current_drawdown": "56",
        "current_drawdown_pct": "0.05",
        "max_drawdown": "140",
        "max_drawdown_pct": "0.125",
        "points": [
            {
                "snapshot_time": "2024-03-09T12:00:00Z",
                "equity": "1000",
                "peak_equity": "1000",
                "drawdown": "0",
                "drawdown_pct": "0",
            },
            {
                "snapshot_time": "2024-03-09T16:03:00Z",
                "equity": "1005",
                "peak_equity": "1005",
                "drawdown": "0",
                "drawdown_pct": "0",
            },
            {
                "snapshot_time": "2024-03-10T09:00:00Z",
                "equity": "1120",
                "peak_equity": "1120",
                "drawdown": "0",
                "drawdown_pct": "0",
            },
            {
                "snapshot_time": "2024-03-10T09:30:00Z",
                "equity": "980",
                "peak_equity": "1120",
                "drawdown": "140",
                "drawdown_pct": "0.125",
            },
            {
                "snapshot_time": "2024-03-10T10:02:00Z",
                "equity": "1064",
                "peak_equity": "1120",
                "drawdown": "56",
                "drawdown_pct": "0.05",
            },
        ],
    }

    assert metrics_response.status_code == 200
    assert metrics_response.json() == {
        "total_trades": 5,
        "win_rate": "50",
        "realized_pnl": "5",
        "average_pnl_per_trade": "2.5",
        "current_equity": "1064",
        "max_winning_streak": 1,
        "max_losing_streak": 1,
    }

    assert performance_response.status_code == 200
    assert performance_response.json() == {
        "symbol": "BTCUSDT",
        "start_date": None,
        "end_date": None,
        "total_closed_trades": 1,
        "expectancy_per_closed_trade": "10",
        "profit_factor": None,
        "average_hold_seconds": 60,
        "average_win": "10",
        "average_loss": None,
        "session_realized_pnl": "5",
        "session_unrealized_pnl": "59",
        "symbol_realized_pnl": "10",
        "max_drawdown": "140",
        "current_drawdown": "56",
    }


def test_dashboard_api_filtering_pagination_and_summary() -> None:
    db_path = _db_path()
    repository = StorageRepository(f"sqlite:///{db_path}")
    try:
        _seed_repository(repository)
    finally:
        repository.close()

    client = _make_client(db_path)
    try:
        trades_response = client.get("/trades", params={"symbol": "btcusdt", "limit": 1, "offset": 1})
        fills_response = client.get(
            "/fills",
            params={"start_date": "2024-03-09", "end_date": "2024-03-09", "limit": 2, "offset": 1},
        )
        events_response = client.get("/events", params={"symbol": "ETHUSDT", "limit": 1, "offset": 1})
        summary_response = client.get("/summary/symbols", params=[("symbols", "BTCUSDT"), ("symbols", "SOLUSDT")])
        performance_response = client.get(
            "/performance",
            params={"symbol": "BTCUSDT", "start_date": "2024-03-09", "end_date": "2024-03-09"},
        )
    finally:
        app.dependency_overrides.clear()

    assert trades_response.status_code == 200
    assert trades_response.json() == {
        "items": [
            {
                "order_id": "PAPER-000002",
                "symbol": "BTCUSDT",
                "side": "SELL",
                "requested_quantity": "1",
                "approved_quantity": "1",
                "filled_quantity": "1",
                "status": "executed",
                "risk_decision": "approve",
                "reason_codes": ["APPROVED"],
                "fill_price": "110",
                "realized_pnl": "10",
                "quote_balance": "1009.79",
                "event_time": "2024-03-09T16:01:00Z",
            }
        ],
        "total": 3,
        "limit": 1,
        "offset": 1,
    }

    assert fills_response.status_code == 200
    assert fills_response.json()["total"] == 4
    assert len(fills_response.json()["items"]) == 2
    assert fills_response.json()["items"][0]["order_id"] == "PAPER-000002"

    assert events_response.status_code == 200
    assert events_response.json() == {
        "items": [
            {
                "event_type": "execution_result",
                "symbol": "ETHUSDT",
                "message": "status=executed",
                "payload": {"filled_quantity": "1", "status": "executed"},
                "event_time": "2024-03-09T16:03:00Z",
            }
        ],
        "total": 2,
        "limit": 1,
        "offset": 1,
    }

    assert summary_response.status_code == 200
    assert summary_response.json() == [
        {
            "symbol": "BTCUSDT",
            "total_trades": 3,
            "buy_trades": 2,
            "sell_trades": 1,
            "win_rate": "100",
            "realized_pnl": "10",
            "open_quantity": "1",
            "avg_entry_price": "120",
            "open_exposure": "120",
            "last_trade_time": "2024-03-10T10:00:00Z",
        },
        {
            "symbol": "SOLUSDT",
            "total_trades": 0,
            "buy_trades": 0,
            "sell_trades": 0,
            "win_rate": "0",
            "realized_pnl": "0",
            "open_quantity": "3",
            "avg_entry_price": "20",
            "open_exposure": "60",
            "last_trade_time": None,
        },
    ]

    assert performance_response.status_code == 200
    assert performance_response.json() == {
        "symbol": "BTCUSDT",
        "start_date": "2024-03-09",
        "end_date": "2024-03-09",
        "total_closed_trades": 1,
        "expectancy_per_closed_trade": "10",
        "profit_factor": None,
        "average_hold_seconds": 60,
        "average_win": "10",
        "average_loss": None,
        "session_realized_pnl": "5",
        "session_unrealized_pnl": "0",
        "symbol_realized_pnl": "10",
        "max_drawdown": "0",
        "current_drawdown": "0",
    }


def test_dashboard_api_uses_dependency_backed_data_access() -> None:
    class FakeDashboardDataAccess:
        def __init__(self) -> None:
            self.trade_calls: list[tuple[str | None, date | None, date | None, int, int]] = []

        def get_trades_page(
            self,
            *,
            symbol: str | None,
            start_date: date | None,
            end_date: date | None,
            limit: int,
            offset: int,
        ) -> tuple[list[TradeRecord], int]:
            self.trade_calls.append((symbol, start_date, end_date, limit, offset))
            return (
                [
                    TradeRecord(
                        order_id="FAKE-1",
                        symbol="BTCUSDT",
                        side="BUY",
                        requested_quantity=Decimal("1"),
                        approved_quantity=Decimal("1"),
                        filled_quantity=Decimal("1"),
                        status="executed",
                        risk_decision="approve",
                        reason_codes=("APPROVED",),
                        fill_price=Decimal("100"),
                        realized_pnl=Decimal("0"),
                        quote_balance=Decimal("900"),
                        event_time=datetime(2024, 3, 9, 16, 0, 0, tzinfo=UTC),
                    )
                ],
                1,
            )

    fake_data_access = FakeDashboardDataAccess()
    app.dependency_overrides[get_dashboard_data_access] = lambda: fake_data_access
    client = TestClient(app)
    try:
        response = client.get("/trades", params={"symbol": "BTCUSDT", "limit": 25, "offset": 5})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["order_id"] == "FAKE-1"
    assert fake_data_access.trade_calls == [("BTCUSDT", None, None, 25, 5)]
