from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.analysis.horizon_analysis import HorizonPatternAnalysisService
from app.analysis.pattern_summary import PatternPricePoint


def _points(prices: list[Decimal], *, start: datetime, step_hours: int) -> list[PatternPricePoint]:
    return [
        PatternPricePoint(
            symbol="BTCUSDT",
            timestamp=start + timedelta(hours=index * step_hours),
            close_price=price,
        )
        for index, price in enumerate(prices)
    ]


def test_pattern_analysis_detects_bullish_horizon_behavior() -> None:
    points = _points(
        [
            Decimal("100"),
            Decimal("102"),
            Decimal("103"),
            Decimal("105"),
            Decimal("107"),
            Decimal("108"),
            Decimal("110"),
        ],
        start=datetime(2024, 3, 1, tzinfo=UTC),
        step_hours=4,
    )
    analysis = HorizonPatternAnalysisService().analyze(
        symbol="BTCUSDT",
        horizon="1d",
        points=points,
        runtime_active=True,
    )

    assert analysis.overall_direction == "bullish"
    assert analysis.net_return_pct is not None
    assert analysis.net_return_pct > Decimal("0")
    assert analysis.data_state in {"ready", "waiting_for_history"}


def test_pattern_analysis_detects_bearish_horizon_behavior() -> None:
    points = _points(
        [
            Decimal("110"),
            Decimal("108"),
            Decimal("107"),
            Decimal("105"),
            Decimal("104"),
            Decimal("102"),
            Decimal("100"),
        ],
        start=datetime(2024, 3, 1, tzinfo=UTC),
        step_hours=4,
    )
    analysis = HorizonPatternAnalysisService().analyze(
        symbol="BTCUSDT",
        horizon="1d",
        points=points,
        runtime_active=True,
    )

    assert analysis.overall_direction == "bearish"
    assert analysis.net_return_pct is not None
    assert analysis.net_return_pct < Decimal("0")


def test_pattern_analysis_detects_choppy_behavior() -> None:
    points = _points(
        [
            Decimal("100"),
            Decimal("101"),
            Decimal("99"),
            Decimal("101"),
            Decimal("99.5"),
            Decimal("100.5"),
            Decimal("100"),
        ],
        start=datetime(2024, 3, 1, tzinfo=UTC),
        step_hours=4,
    )
    analysis = HorizonPatternAnalysisService().analyze(
        symbol="BTCUSDT",
        horizon="1d",
        points=points,
        runtime_active=True,
    )

    assert analysis.trend_character in {"choppy", "balanced"}
    assert analysis.breakout_tendency in {"range_bound", "mixed"}


def test_pattern_analysis_returns_incomplete_state_when_history_is_insufficient() -> None:
    points = _points(
        [Decimal("100"), Decimal("101")],
        start=datetime(2024, 3, 9, tzinfo=UTC),
        step_hours=1,
    )
    analysis = HorizonPatternAnalysisService().analyze(
        symbol="BTCUSDT",
        horizon="7d",
        points=points,
        runtime_active=False,
    )

    assert analysis.data_state == "waiting_for_history"
    assert analysis.partial_coverage is True
    assert analysis.net_return_pct is not None
    assert analysis.explanation is not None


def test_pattern_analysis_calculates_return_and_drawdown_shape() -> None:
    points = _points(
        [
            Decimal("100"),
            Decimal("110"),
            Decimal("105"),
            Decimal("115"),
            Decimal("109"),
            Decimal("120"),
        ],
        start=datetime(2024, 3, 1, tzinfo=UTC),
        step_hours=5,
    )
    analysis = HorizonPatternAnalysisService().analyze(
        symbol="BTCUSDT",
        horizon="1d",
        points=points,
        runtime_active=True,
    )

    assert analysis.net_return_pct is not None
    assert analysis.max_drawdown_pct is not None
    assert analysis.net_return_pct > Decimal("0")
    assert analysis.max_drawdown_pct > Decimal("0")
