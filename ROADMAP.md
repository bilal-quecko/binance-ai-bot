# BINANCE AI BOT — Full Development Roadmap
_Last updated: 2026-04-22_

# Strategic Scope Expansion

The project is expanding from a live paper-trading workstation into a broader trading intelligence platform.

The long-term architecture must include:

1. Technical Analysis Engine
2. Market Sentiment Engine
3. Symbol Sentiment Engine
4. Fundamental Analysis Engine
5. Multi-Horizon Pattern Analysis
6. Combined Signal Engine
7. Paper Automation
8. Futures Long/Short Execution (later)

---

# New Phase — Technical Analysis Engine Maturity

## Goal
Build a proper technical-analysis layer for the selected symbol.

## Must complete
- multi-timeframe trend analysis
- support/resistance detection
- breakout/reversal detection
- volatility regime classification
- momentum analysis
- trend-strength scoring
- clearer technical explanations in UI

## Acceptance criteria
The selected symbol can be analyzed technically in a way a trader can understand without relying only on a generic AI card.

---

# New Phase — Market and Symbol Sentiment Layer

## Goal
Add broader market sentiment and symbol-specific sentiment.

## Must complete
- market-wide crypto sentiment/bias
- symbol-specific sentiment feed
- sentiment scoring pipeline
- source freshness tracking
- confidence / fallback handling
- UI separation between market sentiment and symbol sentiment

## Acceptance criteria
The platform can explain whether the environment is broadly supportive, broadly weak, or mixed.

---

# New Phase — Fundamental Context Layer

## Goal
Add crypto-relevant fundamental context for the selected symbol.

## Must complete
- define what “fundamental analysis” means for this platform
- add symbol/project context fields
- add liquidity/market-structure tiering
- add supply/unlock/context data where available
- render a compact fundamentals summary

## Acceptance criteria
The user can see more than price action alone when evaluating a symbol.

---

# New Phase — Multi-Horizon Pattern Analysis

## Goal
Allow custom day-based pattern analysis for the selected symbol.

## Must complete
- support user-selectable day horizons
- compute trend/volatility/up-down behavior over selected range
- summarize pattern changes over the selected duration
- integrate into signal formation

## Acceptance criteria
The platform can explain how the symbol behaved over the selected number of days.

---

# New Phase — Signal Synthesis Engine

## Goal
Combine technical, sentiment, fundamentals, and pattern analysis into one explainable signal.

## Must complete
- separate sub-scores for:
  - technical
  - market sentiment
  - symbol sentiment
  - fundamentals
  - pattern/horizon behavior
- combine into final signal:
  - long bias
  - short bias
  - neutral
  - confidence
  - suggested action
  - explanation

## Acceptance criteria
The final signal is explainable, layered, and not a black box.

---

# New Phase — Futures Mode Preparation

## Goal
Prepare for later long/short futures trading safely.

## Must complete
- futures paper mode first
- long/short support
- leverage-aware risk engine
- funding/open-interest aware context
- liquidation-risk controls
- separate mode handling from spot

## Acceptance criteria
Futures mode is introduced safely and only after signal quality and risk maturity improve.

That is what will turn it into a real full-fledged system.
