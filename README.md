# Binance AI Bot

AI-assisted Binance Spot signal-intelligence platform with a paper-mode trading workstation.

## Current status

This repository is currently a V1 paper-mode signal provider and analysis dashboard.

Implemented areas include:

- Binance Spot market-data integration
- FastAPI backend
- React/Vite dashboard
- paper-mode runtime controls
- manual paper buy/close controls
- technical analysis
- market sentiment
- symbol sentiment
- multi-horizon pattern analysis
- regime analysis
- final signal/fusion layer
- trading assistant
- signal validation and edge reports
- similar setup analysis
- trade eligibility review
- adaptive recommendations
- performance, review, and calibration panels

## Safety status

The current product is advisory and paper-mode only.

- No live Binance order execution
- No Futures execution
- No leverage
- AI does not place trades directly
- Paper execution must pass deterministic strategy and risk checks
- Signals are not guaranteed to be profitable

## Requirements

- Python 3.11+
- Node.js 18+
- npm

## Backend setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -e .[dev]
cp .env.example .env
uvicorn app.main:app --reload
```

Backend default URL:

```text
http://127.0.0.1:8000
```

## Frontend setup

```bash
cd frontend
npm install
npm run dev
```

Frontend default URL:

```text
http://127.0.0.1:5173
```

The Vite dev server proxies `/api` requests to the FastAPI backend.

## Validation commands

```bash
pytest
ruff check app tests
```

```bash
cd frontend
npm run build
```

## Environment

Copy `.env.example` to `.env` and adjust local values as needed.

Do not commit real API keys or secrets.

## Modes

Supported configuration values include:

- `dev`
- `paper`
- `live`

The project should remain in `paper` mode until a separate live-trading architecture, risk review, security review, and production deployment checklist are completed.

## Important limitations

- Fundamental analysis is not fully completed yet.
- Futures mode is intentionally not implemented yet.
- Adaptive recommendations are report-only and are not auto-applied unless explicitly queued through the paper workflow.
- Signal quality depends on accumulated historical snapshots and forward outcome data.

## Repository structure

```text
binance-ai-bot/
├── app/                 # FastAPI backend and trading intelligence modules
├── frontend/            # React/Vite dashboard
├── tests/               # Backend tests
├── AGENTS.md            # Product direction and development rules
├── PROGRESS.md          # Implementation checkpoints
├── ROADMAP.md           # Future development roadmap
├── pyproject.toml       # Python package/dependency config
├── requirements.txt     # Python dependency list
├── .env.example         # Safe local environment template
└── .gitignore
```
