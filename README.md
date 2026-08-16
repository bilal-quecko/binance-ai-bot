# Binance AI Bot

AI-Assisted Binance Signal Intelligence Platform.

This project is a paper-mode signal intelligence workstation for Binance symbols. It combines technical analysis, market and symbol sentiment context, regime analysis, similar setup outcomes, signal validation, trade eligibility, adaptive recommendations, and a V1 signal summary dashboard. It does not place live orders.

## Current Product State

- V1 Market Ready Signal Provider is complete.
- The main UI opens on a premium V1 signal summary dashboard for the selected symbol.
- Advanced modules are preserved inside `Advanced Details - Pro`.
- Manual paper buy and close flows are stable.
- Signal validation, regime analysis, similar setup outcomes, trade eligibility, and adaptive recommendations exist.
- A paper-only Futures Long/Short Opportunity Scanner is available for advisory ranking only.
- A paper-only Spot Opportunity Scanner is available for advisory buy/watch/avoid ranking only.
- Active Spot paper profile is more responsive while retaining deterministic risk, fee/slippage, daily-loss, and max-position gates.
- Spot paper attempts now persist signal, risk, execution, blocked reason, position, and PnL context for blocker analytics.
- Separate paper-only Futures LONG/SHORT execution models and manual LONG/SHORT/CLOSE endpoints are available for simulation only.
- The futures scanner can scan up to 100 symbols and includes a display-only paper leverage risk simulator.
- The Spot scanner can scan up to 100 Spot USDT symbols with progressive async jobs, validation-ready persistence, and Spot paper simulation handoff.
- Selected-symbol analysis loads separately from paper trading runtime controls; Start, Pause, Resume, and Stop control only paper runtime.
- Sidebar selections use Spot analysis/simulation by default, while Futures scanner Simulate opens a separate USD-M Futures paper simulation flow.
- Market Sensitivity supports Conservative, Balanced, and Active paper modes. Active mode is paper-only and only surfaces smaller slow-market setups when deterministic structure, liquidity, invalidation, and cost checks remain acceptable.
- Prediction-redesign Phase 1 is implemented: actionable signals are continuously evaluated for timing quality across 5m, 15m, 1h, 4h, and 24h horizons.
- Timing baselines persist pre-signal move consumption, post-signal capture, lead time, MFE/MAE, target/stop timing, paper-entry latency when available, estimated post-cost return, regime, volatility, liquidity context, and early/useful/late/chased/false classifications.
- LONG futures scanner candidates should render green, SHORT candidates red, and WAIT/AVOID candidates neutral.

## Safety Baseline

- No live trading.
- No real futures execution.
- No autonomous AI trade execution.
- AI is advisory-only.
- Paper trading is the active execution model.
- Signals are not profitability guarantees.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
Copy-Item .env.example .env
```

Install frontend dependencies:

```powershell
cd frontend
npm install
cd ..
```

## Local SQLite Setup

The default local database is repo-local:

```text
sqlite:///./data/binance_ai_bot.db
```

`data/` is created automatically on backend startup if it does not exist. This database stores paper sessions, signal history, validation snapshots, historical candles, runtime recovery state, and paper broker recovery state. The database file is ignored by git.

If you override `DATABASE_URL`, use a writable local SQLite path:

```env
DATABASE_URL=sqlite:///./data/binance_ai_bot.db
```

## Run

Backend:

```powershell
uvicorn app.main:app --reload
```

Frontend:

```powershell
cd frontend
npm run dev
```

Tests:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check app tests
```

Build frontend:

```powershell
cd frontend
npm run build
```

## V1 Capabilities

- Symbol-first V1 signal summary with final BUY/WAIT/AVOID/EXIT style guidance.
- Technical analysis: trend, momentum, volatility, structure, support/resistance, breakout/reversal context, and multi-timeframe confirmation.
- Market sentiment: BTC/ETH context, broader market tone, breadth, volatility environment, and source/freshness-aware fallback behavior.
- Symbol sentiment: source-backed or heuristic/proxy sentiment with explicit confidence and fallback labels.
- Pattern analysis: selectable horizons with trend persistence, return, drawdown, volatility, breakout/range/reversal behavior.
- Signal synthesis: separate technical, sentiment, pattern, AI, eligibility, and validation inputs before final signal presentation.
- Signal validation: persisted snapshots and forward outcome checks where enough candles exist.
- Regime analysis: deterministic current market regime and behavior guidance.
- Similar setup engine: compares current setups against stored historical outcomes when sample size is sufficient.
- Trade eligibility gate: advisory evidence-based gate for paper automation consideration.
- Adaptive recommendations: report-only threshold and rule suggestions from measured outcomes.
- Paper futures scanner: advisory LONG/SHORT/WAIT/AVOID opportunity ranking without execution, with async progressive scan jobs, 20/50/100-symbol scan sizes, display-only leverage-risk simulation, and event-based liquidation intelligence fields.
- Paper futures execution sandbox: separate isolated-margin paper models, conservative leverage, estimated liquidation references, fees, manual LONG/SHORT/CLOSE, and separate Futures persistence. It never submits Binance Futures orders.
- Paper Spot scanner: advisory BUY candidate/WATCH/AVOID/EXIT watch ranking from Spot candles, technical structure, regime, validation, and eligibility evidence, with async progressive scan jobs and persisted validation snapshots.
- Blocker analytics: summarizes recent `trade_blocked`, `risk_decision`, and `execution_result` events so operators can see why no trade happened.
- Slow-market opportunity detection: range breakout, liquidity sweep reversal, compression breakout, mean reversion from range edge, low-volatility continuation, and low-volatility no-edge blocking are labeled for paper-only review.
- Liquidation event intelligence: interprets recent Binance force-order events into cascade, exhaustion, sweep-confirmation, noise, and no-activity context. This uses observed liquidation events only; it does not fabricate predictive liquidation levels.
- Signal timing baseline: measures whether current actionable Spot/Futures signals activate before or after the available move and keeps the lookback swing used as the setup-origin proxy explicitly labeled as derived evidence.

## Main UI

The primary screen is designed as a premium dark trading dashboard for a selected symbol. It keeps top navigation, compact market sidebars, a central AI Trading Assistant decision card, chart context, key insight cards, and paper-mode safety labels visible without requiring the operator to read every advanced module.

Selecting a symbol starts analysis and historical-candle backfill for that symbol without starting paper runtime. Paper Trading Controls affect only paper session state and paper execution readiness; they do not force the selected analysis symbol to follow the runtime symbol. Sidebar/watchlist selections default to Spot context; Futures scanner simulation selections use USD-M Futures candles and scanner-provided paper simulation parameters.

## Advanced Details - Pro

`Advanced Details - Pro` keeps the deeper modules available without cluttering the main V1 workflow. It contains detailed technical analysis, market sentiment, symbol sentiment, pattern analysis, AI advisory, fusion signal, liquidation-event intelligence, signal validation, regime, similar setups, trade eligibility, adaptive recommendations, performance analytics, paper trade review, profile calibration, diagnostics, and related evidence panels.

Advanced details are for validation and due diligence. They must not bypass paper-only execution controls.

## Key Backend Endpoints

- `GET /health` - backend health.
- `GET /bot/status` - paper runtime status and persistence health.
- `POST /bot/start`, `POST /bot/stop`, `POST /bot/pause`, `POST /bot/resume` - paper runtime controls.
- `GET /bot/workstation?symbol=...` - selected-symbol workstation state.
- `GET /bot/technical-analysis?symbol=...` - technical analysis layer.
- `GET /bot/market-sentiment?symbol=...` - broader market context.
- `GET /bot/symbol-sentiment?symbol=...` - symbol sentiment layer.
- `GET /bot/pattern-analysis?symbol=...&horizon=...` - multi-horizon pattern layer.
- `GET /bot/regime-analysis?symbol=...&horizon=...` - current regime layer.
- `GET /bot/trade-eligibility?symbol=...&horizon=...` - advisory eligibility gate.
- `POST /bot/spot-opportunities/scan` - start a paper-only Spot opportunity scan.
- `GET /bot/spot-opportunities/scan/{scan_id}` - read Spot scanner progress and partial/final results.
- `POST /bot/spot-opportunities/scan/{scan_id}/cancel` - cancel a running Spot scan.
- `GET /performance/blockers?symbol=...` - recent no-trade blocker analytics.
- `GET /bot/futures/status`, `POST /bot/futures/start`, `POST /bot/futures/stop` - paper Futures runtime controls.
- `GET /bot/futures/signal?symbol=...` - deterministic paper Futures LONG/SHORT/WAIT/AVOID/CLOSE signal.
- `POST /bot/futures/manual-long`, `POST /bot/futures/manual-short`, `POST /bot/futures/manual-close` - manual paper Futures actions only.
- `GET /performance/futures-paper?symbol=...` - paper Futures fills, positions, and PnL summary.
- `GET /bot/futures-opportunities` - paper-only futures long/short opportunity scanner.
- `GET /performance/signal-validation` - measured signal validation report.
- `GET /bot/signal-timing-baseline?symbol=...&source=...&horizon=...` - Phase 1 timing-quality baseline with aggregate and recent per-signal evidence.

## Investor-Facing Summary

Binance shows market data. This platform converts market data into explainable, validated, paper-tested trading decisions.

- Explainable signal engine with separate technical, sentiment, pattern, validation, and eligibility context.
- Spot and Futures paper simulation with long/short decision support.
- Blocker analytics that explains why no trade happened.
- Validation loop that checks whether past signals worked.
- Similar setup analysis and adaptive recommendations.
- Paper-first safety before any live-risk phase.
- Beginner-friendly summary with advanced pro details for due diligence.
- `GET /performance/similar-setups` - historical similar setup outcome report.
- `GET /performance/adaptive-recommendations` - report-only adaptive recommendations.

## Paper Trading Limitations

Paper trading is a simulation. It does not fully model exchange latency, partial fills, liquidity shocks, downtime, liquidation, funding, or real order-book execution. Binance force-order data is event-based and retrospective. Paper results are useful for validation, but they are not proof of live profitability.

The futures scanner is also paper-only and advisory-only. Its leverage simulator estimates paper TP, SL, live return, fees/slippage, and risk labels for display only. It does not open persistent futures positions and does not place Binance futures orders.

The Spot scanner is paper-only and advisory-only. It ranks Spot buy candidates, watch names, exit-watch names, and avoid names. It does not short Spot symbols and does not place Binance Spot orders.

## SQLite Troubleshooting

Expected default path:

```text
sqlite:///./data/binance_ai_bot.db
```

If you see a warning that WAL is unavailable, the app should continue using the repo-local database with SQLite default journaling when the path is writable. Persistence should still survive backend restarts.

If you see a temp-storage warning, the configured database path is not writable or SQLite cannot persist to it in the current environment. Check:

- `DATABASE_URL` in `.env`.
- Whether `data/` exists or can be created.
- Whether the repo directory is writable.
- Antivirus, sync tools, or filesystem restrictions that may block SQLite journal files.

Do not point `DATABASE_URL` at a user-specific hardcoded path. Prefer the repo-local default unless there is a deliberate deployment reason to change it.
