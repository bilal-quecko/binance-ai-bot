"""AI advisory signal service."""

from __future__ import annotations

from decimal import Decimal

from app.analysis.market_sentiment import MarketSentimentSnapshot
from app.analysis.technical import TechnicalAnalysisSnapshot
from app.ai.features import extract_ai_features
from app.ai.models import AISignalSnapshot
from app.ai.scoring import score_ai_signal
from app.features.models import FeatureSnapshot
from app.market_data.candles import Candle
from app.market_data.orderbook import TopOfBook


class AISignalService:
    """Build a deterministic AI-style advisory signal from market state."""

    def build_signal(
        self,
        *,
        symbol: str,
        candles: list[Candle],
        feature_snapshot: FeatureSnapshot,
        top_of_book: TopOfBook | None = None,
        technical_analysis: TechnicalAnalysisSnapshot | None = None,
        market_sentiment: MarketSentimentSnapshot | None = None,
        recent_false_positive_rate_5m: Decimal | None = None,
        recent_false_reversal_rate_5m: Decimal | None = None,
    ) -> AISignalSnapshot:
        """Create an advisory AI signal snapshot for one symbol."""

        feature_vector = extract_ai_features(
            symbol=symbol,
            candles=candles,
            feature_snapshot=feature_snapshot,
            top_of_book=top_of_book,
            technical_analysis=technical_analysis,
            market_sentiment=market_sentiment,
            recent_false_positive_rate_5m=recent_false_positive_rate_5m,
            recent_false_reversal_rate_5m=recent_false_reversal_rate_5m,
        )
        return score_ai_signal(feature_vector)
