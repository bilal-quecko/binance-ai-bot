from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.monitoring.futures_scanner_heartbeat import calculate_futures_scanner_heartbeat


def test_long_heartbeat_distance_to_stop_and_take_profit() -> None:
    now = datetime(2024, 1, 1, 12, 1, tzinfo=UTC)
    heartbeat = calculate_futures_scanner_heartbeat(
        direction="long",
        scan_price=Decimal("100"),
        live_price=Decimal("101"),
        signal_time=now - timedelta(seconds=60),
        live_price_updated_at=now,
        stop_loss=Decimal("98"),
        take_profit=Decimal("104"),
        now=now,
    )

    assert heartbeat.live_change_since_scan == Decimal("1.0000")
    assert heartbeat.distance_to_stop == Decimal("2.9703")
    assert heartbeat.distance_to_take_profit == Decimal("2.9703")
    assert heartbeat.signal_age_seconds == 60
    assert heartbeat.status == "active"


def test_long_invalidates_when_live_price_falls_below_stop() -> None:
    now = datetime(2024, 1, 1, 12, 1, tzinfo=UTC)
    heartbeat = calculate_futures_scanner_heartbeat(
        direction="long",
        scan_price=Decimal("100"),
        live_price=Decimal("97.9"),
        signal_time=now - timedelta(seconds=30),
        live_price_updated_at=now,
        stop_loss=Decimal("98"),
        take_profit=Decimal("104"),
        now=now,
    )

    assert heartbeat.status == "invalidated"


def test_short_invalidates_when_live_price_rises_above_stop() -> None:
    now = datetime(2024, 1, 1, 12, 1, tzinfo=UTC)
    heartbeat = calculate_futures_scanner_heartbeat(
        direction="short",
        scan_price=Decimal("100"),
        live_price=Decimal("102.2"),
        signal_time=now - timedelta(seconds=30),
        live_price_updated_at=now,
        stop_loss=Decimal("102"),
        take_profit=Decimal("96"),
        now=now,
    )

    assert heartbeat.status == "invalidated"


def test_stale_heartbeat_behavior() -> None:
    now = datetime(2024, 1, 1, 12, 1, tzinfo=UTC)
    heartbeat = calculate_futures_scanner_heartbeat(
        direction="long",
        scan_price=Decimal("100"),
        live_price=Decimal("101"),
        signal_time=now - timedelta(seconds=90),
        live_price_updated_at=now - timedelta(seconds=31),
        stop_loss=Decimal("98"),
        take_profit=Decimal("104"),
        now=now,
    )

    assert heartbeat.status == "stale"
    assert heartbeat.signal_age_seconds == 90
    assert heartbeat.live_change_since_scan is None
