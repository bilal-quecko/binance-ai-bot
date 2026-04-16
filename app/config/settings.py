"""Application settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="binance-ai-bot", alias="APP_NAME")
    app_env: Literal["dev", "paper", "live"] = Field(default="dev", alias="APP_ENV")
    app_mode: Literal["dev", "paper", "live"] = Field(default="paper", alias="APP_MODE")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    api_host: str = Field(default="127.0.0.1", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")

    symbols: str = Field(default="BTCUSDT,ETHUSDT", alias="SYMBOLS")
    timeframes: str = Field(default="1m,5m,15m", alias="TIMEFRAMES")
    risk_per_trade: float = Field(default=0.005, alias="RISK_PER_TRADE")
    max_daily_loss: float = Field(default=0.02, alias="MAX_DAILY_LOSS")
    max_open_positions: int = Field(default=3, alias="MAX_OPEN_POSITIONS")
    ai_enabled: bool = Field(default=False, alias="AI_ENABLED")

    binance_api_key: str = Field(default="", alias="BINANCE_API_KEY")
    binance_api_secret: str = Field(default="", alias="BINANCE_API_SECRET")
    binance_base_url: str = Field(default="https://api.binance.com", alias="BINANCE_BASE_URL")
    binance_ws_url: str = Field(
        default="wss://stream.binance.com:9443/ws",
        alias="BINANCE_WS_URL",
    )

    database_url: str = Field(default="sqlite:///./binance_ai_bot.db", alias="DATABASE_URL")

    @property
    def symbol_list(self) -> list[str]:
        return [item.strip().upper() for item in self.symbols.split(",") if item.strip()]

    @property
    def timeframe_list(self) -> list[str]:
        return [item.strip() for item in self.timeframes.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()
