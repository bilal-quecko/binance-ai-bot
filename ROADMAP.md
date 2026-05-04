# Binance AI Bot Roadmap

Last updated: 2026-04-30

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

### Futures Paper Long/Short Opportunity Scanner

Status: Current product direction and implemented paper scanner

- Paper-only scanner ranks Binance quote-asset symbols as LONG, SHORT, WAIT, or AVOID.
- LONG candidates should render green.
- SHORT candidates should render red.
- WAIT and AVOID candidates should render neutral/default.
- Scanner output is advisory only.
- No real futures execution, no live leverage, and no Binance futures orders are allowed in this phase.

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
- Leverage and margin-aware risk engine.
- Stronger controls than spot paper trading.
- Explicit user request and separate design review.

## Not In Scope Now

- Live spot trading.
- Real futures execution.
- Autonomous AI order placement.
- Profitability guarantees.
