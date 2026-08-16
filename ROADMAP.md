# Binance AI Bot Roadmap

Last updated: 2026-07-19

## Product Direction

The target product is an AI-Assisted Binance Signal Intelligence Platform.

The platform evolves in this order:

1. Technical Analysis Layer
2. Market Sentiment Layer
3. Symbol Sentiment Layer
4. Fundamental Analysis Layer
5. Multi-Horizon Pattern Analysis Layer
6. Signal Synthesis Layer
7. Paper Automation Layer
8. Futures Long/Short Layer, later phase only

## Completed Phases

### Technical Analysis Engine

Status: Completed

- Trend, momentum, volatility, structure, support/resistance, breakout/reversal context, and multi-timeframe analysis are available for selected symbols.

### Market and Symbol Sentiment Layers

Status: Completed

- Broader market sentiment exists.
- Symbol sentiment exists with explicit source/fallback behavior.
- Sentiment remains advisory and source-labeled.

### Multi-Horizon Pattern Analysis

Status: Completed

- User-selectable horizons are available.
- Pattern behavior includes return, drawdown, volatility, persistence, breakout/range/reversal tendencies, and insufficient-history states.

### Signal Synthesis Engine

Status: Completed

- Technical, sentiment, pattern, AI advisory, fusion, risk, eligibility, and validation context feed explainable final signal presentation.
- Signals are not a single opaque score.

### Signal Validation

Status: Completed

- Signal snapshots are persisted and evaluated against forward outcomes when enough candle history exists.
- Reports stay honest when samples are insufficient.

### Regime Analysis

Status: Completed

- Current selected-symbol regime analysis exists with confidence, evidence, behavior guidance, avoid conditions, and warnings.

### Similar Setup Outcome Engine

Status: Completed

- Current or latest setups can be compared against historical signal-validation snapshots.
- Reliability remains sample-size gated.

### Trade Eligibility Gate

Status: Completed

- Advisory-only eligibility combines signal, regime, validation, similar setup evidence, blockers, confidence, horizon, risk grade, and fee/slippage checks.
- It does not place trades or bypass paper controls.

### Adaptive Recommendations

Status: Completed

- Evidence-based threshold and rule recommendations exist.
- Recommendations are report-only and are not auto-applied.

### V1 Signal Provider Release

Status: Completed

- The main UI presents a premium V1 signal summary dashboard.
- Advanced modules are preserved under `Advanced Details - Pro`.
- Manual paper buy/close remains stable.
- Safety messaging is visible: paper mode, advisory only, no guaranteed profit.

## Current Phase

### Prediction Redesign - Phase 1 Timing Baseline

Status: Completed

- Existing actionable signal snapshots are evaluated at fixed 5m, 15m, 1h, 4h, and 24h horizons without changing entry or execution behavior.
- The baseline measures activation price, a clearly labeled derived lookback swing origin, recent swing bounds, pre-signal move, post-signal move, MFE/MAE, move-consumed percentage, capture ratio, entry efficiency, lead time, target/stop timing, expiry, estimated post-cost return, volatility, regime, and available liquidity context.
- Matching executed paper orders contribute signal-to-entry latency when available; unrelated or absent paper execution remains null rather than fabricated.
- Samples are classified deterministically as early, useful, late, chased, false, neutral, or insufficient-data.
- Results persist in SQLite, recover across restarts, are evaluated by the existing background outcome service, and are exposed through `GET /bot/signal-timing-baseline`.
- This phase establishes the measurable control baseline required before the continuous scanner and predictive setup lifecycle are implemented.

### V2 Paper Trading Upgrades

Status: Implemented incrementally in paper mode

- Active Spot paper profile is more responsive, but keeps deterministic risk checks, fee/slippage handling, daily-loss protection, and max-position controls.
- Blocker analytics groups no-trade causes such as weak signal, low volatility, spread too wide, edge below costs, position limit, and daily loss limit.
- Separate Futures paper models, risk checks, signal engine, service, persistence, endpoints, and UI controls support manual paper LONG, SHORT, and CLOSE.
- Futures execution remains paper-only with conservative leverage and estimated liquidation references.
- AI remains advisory-only and cannot bypass deterministic strategy/risk checks.

### Futures Paper Long/Short Opportunity Scanner

Status: Current product direction and implemented paper scanner

- Paper-only scanner ranks Binance quote-asset symbols as LONG, SHORT, WAIT, or AVOID.
- Scanner supports 20, 50, and 100-symbol market coverage for paper opportunity discovery.
- Scanner refresh uses async progressive jobs so the UI can show queued/running/partial/completed progress and partial candidates while slower symbols continue.
- Scanner uses USD-M Futures candles/prices and cache-first reads for scanner candle history.
- Scanner Simulate opens a separate Futures Paper Simulation flow with scanner-provided direction, entry, stop, target, confidence, risk grade, and editable paper stop/target fields.
- Market Sensitivity supports Conservative, Balanced, and Active paper modes; Active surfaces smaller slow-market setups only when structure and risk gates remain clean.
- Slow-market setup labels include range breakout, liquidity sweep reversal, compression breakout, mean reversion from range edge, low-volatility continuation, and low-volatility no-edge.
- Scanner cards include display-only leverage-risk simulation for paper TP/SL/live return estimates.
- LONG candidates should render green.
- SHORT candidates should render red.
- WAIT and AVOID candidates should render neutral/default.
- Scanner output is advisory only.
- No real futures execution, no live leverage or margin execution, and no Binance futures orders are allowed in this phase.

### Spot Paper Opportunity Scanner

Status: Implemented paper scanner

- Paper-only Spot scanner ranks Binance Spot USDT symbols as BUY candidate, WATCH, EXIT watch, or AVOID.
- Scanner uses Spot candles, technical trend/momentum/volatility/liquidity, support/resistance structure, regime analysis, signal-validation evidence, and trade-eligibility evidence.
- Scanner uses async progressive jobs so the UI can show queued/running/partial/completed progress and partial candidates.
- Completed Spot scanner runs persist scanner candidates, validation snapshots, and post-signal outcome snapshots for later usefulness measurement.
- Spot scanner simulation handoff opens the existing Spot Paper Simulation flow.
- Scanner output is advisory only.
- No Spot shorting, live Spot order placement, autonomous execution, or profitability guarantee is allowed in this phase.

## Next Suggested Phases

### 7-Day Paper Validation Report

Build a compact report that summarizes whether V1 signals, trade eligibility, futures scanner rankings, and adaptive recommendations improved paper outcomes over a rolling 7-day window.

### Public Performance Report

Create a shareable, honest performance report with sample sizes, win/loss distribution, expectancy, drawdown, false positives, blocked trades, and insufficient-data labels.

### Portfolio and Capital Allocator

Design a paper-only allocator that decides symbol exposure, position sizing, max concurrent positions, and capital rotation from validated signal quality and risk controls.

### Manual Apply-and-Compare for Adaptive Settings

Allow an operator to manually queue adaptive recommendations for a future paper session and compare baseline versus adjusted settings.

### Fundamental Context Layer Expansion

Add crypto-relevant fundamental context behind service layers: project quality, liquidity tier, market cap tier, supply/unlock context where available, and source freshness.

### Real Futures Execution

Later phase only after strong validation.

Required before implementation:

- Proven paper results over meaningful samples.
- Futures paper mode with persistent hypothetical long/short outcomes.
- Funding-rate and liquidation-risk context.
- Event-based liquidation intelligence that separates observed cascades, exhaustion, and sweep confirmations from predictive heatmap claims.
- Leverage and margin-aware risk engine.
- Stronger controls than spot paper trading.
- Explicit user request and separate design review.

## Not In Scope Now

- Live spot trading.
- Real futures execution.
- Autonomous AI order placement.
- Profitability guarantees.
