from app.config import Settings


def test_settings_parses_lists() -> None:
    settings = Settings(SYMBOLS="BTCUSDT, ETHUSDT", TIMEFRAMES="1m,5m")

    assert settings.symbol_list == ["BTCUSDT", "ETHUSDT"]
    assert settings.timeframe_list == ["1m", "5m"]
