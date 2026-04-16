# Binance AI Bot

Python scaffold for a Binance Spot trading bot with optional AI-assisted market analysis.

## Current status
This repository is a starter architecture only.
It includes:
- project structure
- typed settings
- basic logging
- minimal FastAPI health app
- placeholders for all major modules
- basic tests

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e .[dev]
cp .env.example .env
uvicorn app.main:app --reload
pytest
```

## Modes
- `dev`
- `paper`
- `live`

Default mode should remain `paper` until the trading core is implemented and tested.

## Safety baseline
- Spot only
- no leverage
- no Futures
- AI must never place trades directly
- every order path must pass deterministic risk validation

## Tree

```text
binance-ai-bot/
├── app/
│   ├── main.py
│   ├── config/
│   ├── exchange/
│   ├── market_data/
│   ├── features/
│   ├── strategies/
│   ├── ai/
│   ├── decision/
│   ├── risk/
│   ├── execution/
│   ├── portfolio/
│   ├── storage/
│   ├── backtest/
│   ├── paper/
│   ├── monitoring/
│   └── api/
├── tests/
├── scripts/
├── docs/
├── docker/
├── .env.example
├── .gitignore
├── AGENTS.md
├── pyproject.toml
└── requirements.txt
```
