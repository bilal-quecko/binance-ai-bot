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
    binance_futures_base_url: str = Field(default="https://fapi.binance.com", alias="BINANCE_FUTURES_BASE_URL")
    binance_derivatives_data_enabled: bool = Field(default=False, alias="BINANCE_DERIVATIVES_DATA_ENABLED")
    binance_ws_url: str = Field(
        default="wss://stream.binance.com:9443/ws",
        alias="BINANCE_WS_URL",
    )

    database_url: str = Field(default="sqlite:///./data/binance_ai_bot.db", alias="DATABASE_URL")
    heatmap_provider: str = Field(default="mock", alias="HEATMAP_PROVIDER")
    heatmap_vendor_base_url: str = Field(default="", alias="HEATMAP_VENDOR_BASE_URL")
    heatmap_vendor_api_key: str = Field(default="", alias="HEATMAP_VENDOR_API_KEY")
    heatmap_vendor_name: str = Field(default="", alias="HEATMAP_VENDOR_NAME")
    heatmap_vendor_clusters_path: str = Field(default="", alias="HEATMAP_VENDOR_CLUSTERS_PATH")
    heatmap_vendor_symbol_param: str = Field(default="symbol", alias="HEATMAP_VENDOR_SYMBOL_PARAM")
    heatmap_request_timeout_seconds: int = Field(default=10, alias="HEATMAP_REQUEST_TIMEOUT_SECONDS")

    continuous_intelligence_enabled: bool = Field(default=True, alias="CONTINUOUS_INTELLIGENCE_ENABLED")
    continuous_intelligence_markets: str = Field(default="spot,futures", alias="CONTINUOUS_INTELLIGENCE_MARKETS")
    continuous_intelligence_quote_asset: str = Field(default="USDT", alias="CONTINUOUS_INTELLIGENCE_QUOTE_ASSET")
    continuous_intelligence_universe_limit: int = Field(default=50, alias="CONTINUOUS_INTELLIGENCE_UNIVERSE_LIMIT")
    continuous_intelligence_cycle_seconds: int = Field(default=300, alias="CONTINUOUS_INTELLIGENCE_CYCLE_SECONDS")
    continuous_intelligence_universe_refresh_seconds: int = Field(
        default=1800,
        alias="CONTINUOUS_INTELLIGENCE_UNIVERSE_REFRESH_SECONDS",
    )
    continuous_intelligence_deep_candidate_limit: int = Field(
        default=12,
        alias="CONTINUOUS_INTELLIGENCE_DEEP_CANDIDATE_LIMIT",
    )
    continuous_intelligence_fast_score_threshold: int = Field(
        default=45,
        alias="CONTINUOUS_INTELLIGENCE_FAST_SCORE_THRESHOLD",
    )
    continuous_intelligence_concurrency: int = Field(default=4, alias="CONTINUOUS_INTELLIGENCE_CONCURRENCY")
    continuous_intelligence_request_interval_ms: int = Field(
        default=50,
        alias="CONTINUOUS_INTELLIGENCE_REQUEST_INTERVAL_MS",
    )
    continuous_intelligence_initial_delay_seconds: int = Field(
        default=2,
        alias="CONTINUOUS_INTELLIGENCE_INITIAL_DELAY_SECONDS",
    )

    @property
    def symbol_list(self) -> list[str]:
        return [item.strip().upper() for item in self.symbols.split(",") if item.strip()]

    @property
    def timeframe_list(self) -> list[str]:
        return [item.strip() for item in self.timeframes.split(",") if item.strip()]

    @property
    def continuous_intelligence_market_list(self) -> list[str]:
        """Return the enabled continuous-intelligence market names."""

        return [
            item.strip().lower()
            for item in self.continuous_intelligence_markets.split(",")
            if item.strip().lower() in {"spot", "futures"}
        ]


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()
