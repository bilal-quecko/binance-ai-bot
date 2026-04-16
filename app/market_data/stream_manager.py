"""Stream manager placeholder."""

from app.market_data.models import MarketSnapshot


class StreamManager:
    """Normalize raw stream payloads into MarketSnapshot objects."""

    def normalize_trade(self, payload: dict) -> MarketSnapshot:
        raise NotImplementedError
