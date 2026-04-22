# Product Direction Update

This repository is no longer only a paper-trading workstation.

The target product is now:

> An AI-assisted trading intelligence and automation platform for Binance symbols.

The platform must evolve to support these layers in order:

1. Technical Analysis Layer
2. Market Sentiment Layer
3. Symbol Sentiment Layer
4. Fundamental Analysis Layer
5. Multi-Horizon Pattern Analysis Layer
6. Signal Synthesis Layer
7. Paper Automation Layer
8. Futures Long/Short Layer (later phase only)

---

# Updated Product Priorities

Codex must prioritize the project in this order:

1. Build analysis quality
2. Build signal quality
3. Validate usefulness
4. Improve automation
5. Add futures support later

Do NOT over-focus on dashboard-only work if core analysis layers are missing.

---

# Required Analysis Layers

For each selected symbol, the system should ultimately provide:

## Technical Analysis
- trend
- support/resistance
- momentum
- volatility
- structure
- breakout/reversal conditions
- multi-timeframe confirmation

## Market Sentiment
- broader crypto market bias
- risk-on / risk-off state
- sector or market-wide tone
- BTC-led context where relevant

## Symbol Sentiment
- news/social/news-like sentiment for the selected symbol
- scored as bullish / bearish / neutral with confidence
- clearly labeled if heuristic or model-derived

## Fundamental Analysis
- symbol/project quality and structural context
- liquidity tier / market cap tier
- supply / unlock / market-structure data where available
- project/news/context summary
- clearly define what “fundamental” means in crypto context

## Pattern Analysis
- user-selectable day horizon
- pattern summary over selected range
- up/down behavior, trend persistence, volatility regime, reversal/breakout signs

## Signal Synthesis
- combine all above layers into:
  - long bias / short bias / neutral
  - signal strength
  - entry quality
  - exit quality
  - suggested action
  - explanation

---

# Signal Rules

Signals must never come from a single opaque score alone.

A valid signal system should clearly separate:
- technical signal
- sentiment signal
- fundamental context
- pattern/horizon signal
- final combined signal

The UI must show what contributed to the final signal.

---

# Futures Expansion Rules

Futures support is a later-phase system only.

Do NOT implement full futures live trading unless explicitly instructed.

When futures mode is introduced, it must include:
- long and short support
- leverage and margin awareness
- funding rate context
- stronger risk controls than spot
- liquidation-risk-aware position logic
- separate paper futures mode before any live mode

---

# Data Source Rules

If sentiment, fundamentals, or broader market context are implemented:
- isolate each data source behind a service layer
- clearly label source freshness
- clearly distinguish live data from derived/inferred data
- provide graceful fallback when external data is unavailable
- do not silently fabricate sentiment or fundamentals

---

# UI Rules for Future Development

For a selected symbol, the workstation should eventually show:

1. Current Status
2. Technical Analysis
3. Market Sentiment
4. Symbol Sentiment
5. Fundamental Analysis
6. Pattern Analysis (custom range)
7. Combined Signal
8. Auto Trade / Futures Mode (later)

Avoid clutter.
Keep the symbol-first workflow.

---

# Evaluation Rules

Every new analysis layer must eventually be measurable.

Examples:
- Did technical analysis improve trade quality?
- Did sentiment improve filtering?
- Did fundamentals reduce bad trades?
- Did combined signals outperform deterministic-only signals?

Do not add layers that cannot later be evaluated.
