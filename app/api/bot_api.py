"""FastAPI endpoints for paper-bot symbol discovery and runtime control."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.bot import BotStatus, PaperBotRuntime
from app.exchange.symbol_service import SpotSymbolRecord, SpotSymbolService

router = APIRouter()


class SymbolResponse(BaseModel):
    """Serialized Spot symbol metadata."""

    symbol: str
    base_asset: str
    quote_asset: str
    status: str


class BotStartRequest(BaseModel):
    """Payload for starting the paper bot."""

    symbol: str = Field(min_length=1)


class BotStatusResponse(BaseModel):
    """Serialized paper-bot runtime status."""

    state: str
    symbol: str | None = None
    timeframe: str
    paper_only: bool
    started_at: datetime | None = None
    last_event_time: datetime | None = None
    last_error: str | None = None


def get_symbol_service(request: Request) -> SpotSymbolService:
    """Return the shared symbol service instance from FastAPI app state."""

    return request.app.state.symbol_service


def get_bot_runtime(request: Request) -> PaperBotRuntime:
    """Return the shared live paper-bot runtime instance from app state."""

    return request.app.state.bot_runtime


def _to_symbol_response(record: SpotSymbolRecord) -> SymbolResponse:
    """Convert a symbol record to an API response."""

    return SymbolResponse(
        symbol=record.symbol,
        base_asset=record.base_asset,
        quote_asset=record.quote_asset,
        status=record.status,
    )


def _to_status_response(status: BotStatus) -> BotStatusResponse:
    """Convert runtime status to an API response."""

    return BotStatusResponse(
        state=status.state,
        symbol=status.symbol,
        timeframe=status.timeframe,
        paper_only=status.paper_only,
        started_at=status.started_at,
        last_event_time=status.last_event_time,
        last_error=status.last_error,
    )


@router.get("/symbols", response_model=list[SymbolResponse])
async def get_symbols(
    symbol_service: Annotated[SpotSymbolService, Depends(get_symbol_service)],
    query: str = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> list[SymbolResponse]:
    """Return searchable tradable Spot symbols for paper mode."""

    records = await symbol_service.search_symbols(query=query, limit=limit)
    return [_to_symbol_response(record) for record in records]


@router.get("/bot/status", response_model=BotStatusResponse)
def get_bot_status(
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
) -> BotStatusResponse:
    """Return the current paper-bot runtime status."""

    return _to_status_response(runtime.status())


@router.post("/bot/start", response_model=BotStatusResponse)
async def start_bot(
    payload: BotStartRequest,
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
) -> BotStatusResponse:
    """Start live Binance Spot market-data driven paper trading."""

    try:
        status = await runtime.start(payload.symbol)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_status_response(status)


@router.post("/bot/stop", response_model=BotStatusResponse)
async def stop_bot(
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
) -> BotStatusResponse:
    """Stop the live paper bot."""

    return _to_status_response(await runtime.stop())


@router.post("/bot/pause", response_model=BotStatusResponse)
async def pause_bot(
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
) -> BotStatusResponse:
    """Pause the live paper bot while keeping market-data ingestion alive."""

    try:
        status = await runtime.pause()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_status_response(status)


@router.post("/bot/resume", response_model=BotStatusResponse)
async def resume_bot(
    runtime: Annotated[PaperBotRuntime, Depends(get_bot_runtime)],
) -> BotStatusResponse:
    """Resume the live paper bot after a pause."""

    try:
        status = await runtime.resume()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_status_response(status)
