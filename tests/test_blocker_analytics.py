from datetime import UTC, datetime

from app.monitoring.blocker_analytics import categorize_blocker, summarize_blockers
from app.storage.models import RunnerEventRecord


def test_categorize_blocker_maps_known_reason_codes() -> None:
    assert categorize_blocker(("EDGE_BELOW_COSTS",)) == "edge_below_costs"
    assert categorize_blocker(("OPEN_POSITION_LIMIT",)) == "position_limit"
    assert categorize_blocker(("VOL_TOO_LOW",)) == "low_volatility"


def test_summarize_blockers_groups_recent_events() -> None:
    events = [
        RunnerEventRecord(
            event_type="trade_blocked",
            symbol="BTCUSDT",
            message="blocked=EDGE_BELOW_COSTS",
            payload_json='{"reason_codes": ["EDGE_BELOW_COSTS"]}',
            event_time=datetime(2024, 1, 1, tzinfo=UTC),
        ),
        RunnerEventRecord(
            event_type="risk_decision",
            symbol="BTCUSDT",
            message="decision=reject",
            payload_json='{"decision": "reject", "reason_codes": ["OPEN_POSITION_LIMIT"]}',
            event_time=datetime(2024, 1, 2, tzinfo=UTC),
        ),
    ]

    report = summarize_blockers(events, symbol="BTCUSDT", limit=10)

    assert report.total_events == 2
    assert report.groups[0].count == 1
    assert {group.category for group in report.groups} == {"edge_below_costs", "position_limit"}
    assert report.next_suggested_action
