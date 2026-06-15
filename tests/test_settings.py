from app.config import Settings


def test_settings_parses_lists() -> None:
    settings = Settings(SYMBOLS="BTCUSDT, ETHUSDT", TIMEFRAMES="1m,5m")

    assert settings.symbol_list == ["BTCUSDT", "ETHUSDT"]
    assert settings.timeframe_list == ["1m", "5m"]


def test_settings_uses_repo_local_data_sqlite_by_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.database_url == "sqlite:///./data/binance_ai_bot.db"
