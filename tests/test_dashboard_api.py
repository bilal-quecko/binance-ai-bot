from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dashboard_api import get_dashboard_data_access
from app.api.dependencies import DashboardDataAccess
from app.config import get_settings
from app.main import app
from app.market_data.candles import Candle
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
    candle_inputs = (
        ("BTCUSDT", base_time, Decimal("100"), Decimal("100")),
        ("BTCUSDT", base_time + timedelta(minutes=1), Decimal("112"), Decimal("112")),
        ("BTCUSDT", next_day, Decimal("120"), Decimal("120")),
        ("BTCUSDT", next_day + timedelta(minutes=1), Decimal("125"), Decimal("125")),
        ("ETHUSDT", base_time + timedelta(minutes=2), Decimal("105"), Decimal("105")),
        ("ETHUSDT", base_time + timedelta(minutes=3), Decimal("100"), Decimal("100")),
    )
    for symbol, open_time, close_price, close_value in candle_inputs:
        repository.insert_market_candle_snapshot(
            Candle(
                symbol=symbol,
                timeframe="1m",
                open=close_value,
                high=close_value,
                low=close_value,
                close=close_price,
                volume=Decimal("1"),
                quote_volume=close_price,
                open_time=open_time,
                close_time=open_time + timedelta(minutes=1),
                event_time=open_time + timedelta(minutes=1),
                trade_count=1,
                is_closed=True,
            )
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
        trade_quality_response = client.get("/performance/trade-quality", params={"symbol": "BTCUSDT"})
        review_response = client.get("/performance/review", params={"symbol": "BTCUSDT"})
        calibration_response = client.get("/performance/profile-calibration", params={"symbol": "BTCUSDT"})
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

    assert trade_quality_response.status_code == 200
    assert review_response.status_code == 200
    assert calibration_response.status_code == 200
    assert trade_quality_response.json() == {
        "symbol": "BTCUSDT",
        "start_date": None,
        "end_date": None,
        "total_details": 1,
        "limit": 5,
        "offset": 0,
        "summary": {
            "total_closed_trades": 1,
            "average_mfe_pct": "10.00",
            "average_mae_pct": "0.00",
            "average_captured_move_pct": "100.00",
            "average_giveback_pct": "0.00",
            "average_entry_quality_score": "100.00",
            "average_exit_quality_score": "100.00",
            "longest_no_trade_seconds": 64740,
            "hold_time_distribution": {
                "average_seconds": 60,
                "median_seconds": 60,
                "p75_seconds": 60,
                "max_seconds": 60,
            },
        },
        "details": [
            {
                "order_id": "PAPER-000002",
                "symbol": "BTCUSDT",
                "entry_time": "2024-03-09T16:00:00Z",
                "exit_time": "2024-03-09T16:01:00Z",
                "quantity": "1",
                "entry_price": "100",
                "exit_price": "110",
                "realized_pnl": "10",
                "hold_seconds": 60,
                "mfe_pct": "10.00",
                "mae_pct": "0.00",
                "captured_move_pct": "100.00",
                "giveback_pct": "0.00",
                "entry_quality_score": "100.00",
                "exit_quality_score": "100.00",
            }
        ],
    }
    review_payload = review_response.json()
    assert review_payload["symbol"] == "BTCUSDT"
    assert review_payload["session"]["total_closed_trades"] == 1
    assert review_payload["session"]["average_pnl"] == "10.0000"
    assert review_payload["session"]["fees_paid"] == "0.3"
    assert review_payload["profiles"][1] == {
        "profile": "balanced",
        "trade_count": 1,
        "realized_pnl": "10",
        "win_rate": "100.00",
        "average_expectancy": "10.0000",
    }
    assert review_payload["execution_sources"][0] == {
        "execution_source": "auto",
        "trade_count": 1,
        "realized_pnl": "10",
        "win_rate": "100.00",
        "average_expectancy": "10.0000",
    }
    assert review_payload["suggestions"][0]["summary"].startswith("BTCUSDT has limited blocker pressure")
    calibration_payload = calibration_response.json()
    assert calibration_payload["symbol"] == "BTCUSDT"
    assert len(calibration_payload["recommendations"]) == 3
    assert calibration_payload["recommendations"][1]["profile"] == "balanced"
    assert calibration_payload["recommendations"][1]["sample_size_warning"] is not None


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
        trade_quality_response = client.get(
            "/performance/trade-quality",
            params={"symbol": "BTCUSDT", "start_date": "2024-03-09", "end_date": "2024-03-09", "limit": 1, "offset": 0},
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

    assert trade_quality_response.status_code == 200
    assert trade_quality_response.json()["summary"]["total_closed_trades"] == 1
    assert trade_quality_response.json()["total_details"] == 1
    assert trade_quality_response.json()["details"][0]["order_id"] == "PAPER-000002"


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


def test_dashboard_api_profile_calibration_apply_and_comparison() -> None:
    db_path = _db_path()
    repository = StorageRepository(f"sqlite:///{db_path}")
    base_time = datetime(2024, 3, 9, 16, 0, tzinfo=UTC)
    try:
        for index, code in enumerate(("VOL_TOO_LOW", "REGIME_NOT_TREND", "VOL_TOO_LOW", "MISSING_ATR_CONTEXT")):
            repository.insert_event(
                event_type="trade_blocked",
                symbol="BTCUSDT",
                message=f"blocked={code}",
                payload={"reason_codes": (code,), "trading_profile": "conservative", "session_id": "blocked-session"},
                event_time=base_time + timedelta(minutes=index),
            )
        for order_id, session_id, tuning_version_id, realized_pnl, event_time in (
            ("BASE-BUY", "baseline-session", None, Decimal("0"), base_time),
            ("BASE-SELL", "baseline-session", None, Decimal("8"), base_time + timedelta(minutes=5)),
            ("TUNED-BUY", "tuned-session", "tune-applied", Decimal("0"), base_time + timedelta(hours=1)),
            ("TUNED-SELL", "tuned-session", "tune-applied", Decimal("12"), base_time + timedelta(hours=1, minutes=5)),
        ):
            fill = FillResult(
                order_id=order_id,
                status="executed",
                symbol="BTCUSDT",
                side="BUY" if "BUY" in order_id else "SELL",
                requested_quantity=Decimal("1"),
                filled_quantity=Decimal("1"),
                fill_price=Decimal("100"),
                fee_paid=Decimal("0.1"),
                realized_pnl=realized_pnl,
                quote_balance=Decimal("1000"),
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
                trading_profile="balanced",
                session_id=session_id,
                tuning_version_id=tuning_version_id,
            )
            repository.insert_fill(
                fill,
                event_time,
                trading_profile="balanced",
                session_id=session_id,
                tuning_version_id=tuning_version_id,
            )

        repository.insert_event(
            event_type="trade_blocked",
            symbol="BTCUSDT",
            message="blocked=VOL_TOO_LOW",
            payload={"reason_codes": ("VOL_TOO_LOW",), "trading_profile": "balanced", "session_id": "baseline-session"},
            event_time=base_time + timedelta(minutes=1),
        )
        repository.insert_event(
            event_type="trade_blocked",
            symbol="BTCUSDT",
            message="blocked=EDGE_BELOW_COSTS",
            payload={"reason_codes": ("EDGE_BELOW_COSTS",), "trading_profile": "balanced", "session_id": "tuned-session"},
            event_time=base_time + timedelta(hours=1, minutes=1),
        )
        repository.start_paper_session_run(
            session_id="baseline-session",
            symbol="BTCUSDT",
            trading_profile="balanced",
            tuning_version_id=None,
            baseline_tuning_version_id=None,
            started_at=base_time,
        )
        repository.finish_paper_session_run(
            session_id="baseline-session",
            ended_at=base_time + timedelta(minutes=10),
        )
        repository.create_profile_tuning_set(
            symbol="BTCUSDT",
            profile="balanced",
            config_json='{"min_atr_ratio": "0.0003", "min_expected_edge_buffer_pct": "0.0006"}',
            baseline_config_json='{"min_atr_ratio": "0.0004", "min_expected_edge_buffer_pct": "0.0008"}',
            baseline_version_id=None,
            reason="Observed blocker pressure shows this profile is waiting too often for confirmation or usable volatility.",
        )
        applied = repository.create_profile_tuning_set(
            symbol="BTCUSDT",
            profile="balanced",
            config_json='{"min_atr_ratio": "0.0003", "min_expected_edge_buffer_pct": "0.0006"}',
            baseline_config_json='{"min_atr_ratio": "0.0004", "min_expected_edge_buffer_pct": "0.0008"}',
            baseline_version_id=None,
            reason="Applied balanced tuning.",
        )
        repository.mark_profile_tuning_applied(applied.version_id, applied_at=base_time + timedelta(minutes=30))
        repository.start_paper_session_run(
            session_id="tuned-session",
            symbol="BTCUSDT",
            trading_profile="balanced",
            tuning_version_id=applied.version_id,
            baseline_tuning_version_id=None,
            started_at=base_time + timedelta(hours=1),
        )
        repository.finish_paper_session_run(
            session_id="tuned-session",
            ended_at=base_time + timedelta(hours=1, minutes=10),
        )
    finally:
        repository.close()

    client = _make_client(db_path)
    try:
        apply_response = client.post(
            "/performance/profile-calibration/apply",
            json={"symbol": "BTCUSDT", "profile": "conservative", "selected_thresholds": ["min_atr_ratio"]},
        )
        comparison_response = client.get(
            "/performance/profile-calibration/comparison",
            params={"symbol": "BTCUSDT", "profile": "balanced"},
        )
    finally:
        app.dependency_overrides.clear()

    assert apply_response.status_code == 200
    assert apply_response.json()["applied_to_next_session"] is True
    assert apply_response.json()["pending_tuning"]["affected_thresholds"][0]["threshold"] == "min_atr_ratio"

    assert comparison_response.status_code == 200
    comparison_payload = comparison_response.json()
    assert comparison_payload["comparison_status"] == "ready"
    assert comparison_payload["before"]["trade_count"] == 1
    assert comparison_payload["after"]["trade_count"] == 1
    assert comparison_payload["after"]["expectancy"] == "12.0000"


def test_dashboard_api_profile_calibration_apply_is_rejected_in_live_mode() -> None:
    db_path = _db_path()
    repository = StorageRepository(f"sqlite:///{db_path}")
    try:
        _seed_repository(repository)
    finally:
        repository.close()

    client = _make_client(db_path)
    original_settings = get_settings()
    app.dependency_overrides[get_settings] = lambda: original_settings.model_copy(update={"app_mode": "live"})
    try:
        response = client.post(
            "/performance/profile-calibration/apply",
            json={"symbol": "BTCUSDT", "profile": "balanced"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
