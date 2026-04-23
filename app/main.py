"""Application entrypoint."""

from __future__ import annotations

from argparse import ArgumentParser
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.api.bot_api import router as bot_router
from app.api.dashboard_api import router as dashboard_router
from app.bot import PaperBotRuntime
from app.config import get_settings
from app.exchange.binance_rest import BinanceRestClient
from app.exchange.binance_ws import BinanceWebSocketClient
from app.exchange.symbol_service import SpotSymbolService
from app.monitoring.logging import configure_logging
from app.sentiment import SymbolSentimentService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)

    rest_client = BinanceRestClient(settings)
    websocket_client = BinanceWebSocketClient(base_url=settings.binance_ws_url)
    symbol_service = SpotSymbolService(rest_client)
    symbol_sentiment_service = SymbolSentimentService()
    bot_runtime = PaperBotRuntime(
        settings=settings,
        websocket_client=websocket_client,
    )

    app.state.symbol_service = symbol_service
    app.state.symbol_sentiment_service = symbol_sentiment_service
    app.state.bot_runtime = bot_runtime

    try:
        yield
    finally:
        await bot_runtime.close()
        await rest_client.close()


app = FastAPI(title="Binance AI Bot", version="0.1.0", lifespan=lifespan)
app.include_router(dashboard_router)
app.include_router(bot_router)


def main() -> None:
    """CLI entry point for serving the FastAPI backend."""

    settings = get_settings()
    parser = ArgumentParser(description="Run the Binance AI Bot API server.")
    parser.add_argument("--host", default=settings.api_host, help="Host interface to bind.")
    parser.add_argument("--port", type=int, default=settings.api_port, help="Port to bind.")
    args = parser.parse_args()
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
