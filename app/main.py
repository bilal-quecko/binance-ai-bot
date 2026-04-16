"""Application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.monitoring.health import HealthStatus
from app.monitoring.logging import configure_logging


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    yield


app = FastAPI(title="Binance AI Bot", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    """Basic health endpoint."""

    settings = get_settings()
    return HealthStatus(
        name=settings.app_name,
        status="ok",
        mode=settings.app_mode,
    ).to_dict()
