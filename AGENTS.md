# AGENTS.md

## Project
This repository is a Python Binance Spot trading bot with optional AI-assisted market analysis.
The AI layer must never place trades directly or bypass deterministic risk controls.

## Rules
- Python 3.11+
- Use FastAPI for internal API endpoints
- Use httpx or aiohttp for REST
- Use websockets for streams
- Use pydantic-settings for config
- Use pytest for tests
- Use PostgreSQL-ready abstractions, but allow SQLite for local dev
- Keep modules small and typed
- Prefer clear, reviewable changes over large rewrites

## Safety constraints
- Spot trading only
- No leverage or Futures
- No live trading by default
- Default mode must be paper trading
- Every order path must go through risk validation
- Never store secrets in source files
- Use .env.example, not real keys

## Architecture order
1. config
2. exchange
3. market_data
4. features
5. strategies
6. risk
7. paper broker
8. execution
9. storage
10. monitoring
11. optional AI analysis

## Coding style
- Add docstrings to public classes and functions
- Add type hints everywhere
- Keep functions single-purpose
- Write or update tests for new behavior
- Do not introduce external dependencies unless necessary

## When modifying code
- Explain plan first
- Then implement
- Then run tests
- Then summarize what changed, risks, and next steps
