# AGENTS.md

Repository instructions for Codex and other coding agents.

## Product Positioning

This project is an:

> AI-Assisted Binance Signal Intelligence Platform

It is no longer only a paper-trading workstation. The product is a symbol-first trading intelligence and paper automation platform for Binance symbols.

## Current Implemented State

- V1 Market Ready Signal Provider is completed.
- Main UI has a premium V1 signal summary dashboard.
- Advanced modules are preserved inside `Advanced Details - Pro`.
- Manual paper buy and close flow is stable.
- Signal validation exists.
- Regime analysis exists.
- Similar setup outcome engine exists.
- Trade eligibility gate exists.
- Adaptive recommendations exist.
- Futures Paper Long/Short Opportunity Scanner is implemented as advisory paper intelligence.

## Development Priorities

Prioritize work in this order:

1. Build analysis quality.
2. Build signal quality.
3. Validate usefulness.
4. Improve paper automation.
5. Add real futures or live execution only in a later validated phase.

Do not over-focus on dashboard-only work when core analysis, signal quality, validation, or persistence are missing.

## Required Analysis Layers

For each selected symbol, the system should provide or evolve toward:

- Technical analysis: trend, support/resistance, momentum, volatility, structure, breakout/reversal conditions, and multi-timeframe confirmation.
- Market sentiment: broader crypto bias, risk-on/risk-off state, sector or market-wide tone, and BTC-led context where relevant.
- Symbol sentiment: selected-symbol news/social/news-like sentiment scored bullish, bearish, or neutral with confidence and source labels.
- Fundamental analysis: crypto-relevant project quality, liquidity tier, market structure, supply/unlock context where available, and clearly labeled source freshness.
- Pattern analysis: user-selectable day horizon with trend persistence, volatility regime, reversal signs, and breakout/range behavior.
- Signal synthesis: long bias, short bias, neutral, signal strength, entry quality, exit quality, suggested action, and explanation.

Signals must never come from a single opaque score alone. Keep technical signal, sentiment signal, fundamental context, pattern/horizon signal, and final combined signal separate and visible.

## Safety Rules

- No live trading unless explicitly requested and separately designed.
- No real futures execution unless explicitly requested in a later validated phase.
- No autonomous AI trade execution.
- AI remains advisory-only.
- Paper trading remains the active execution model.
- Do not add guaranteed profitability claims.
- Every order-like path must stay behind deterministic risk checks and paper-mode controls.

## Paper-Only Execution Rule

Paper spot execution may simulate manual buy and close flows and deterministic strategy behavior. It must not submit Binance live orders.

Runtime recovery, signal history, validation snapshots, and paper broker state should persist through the configured SQLite database when storage is available.

## V1 UI Rules

- Keep the selected symbol as the center of the workflow.
- The first screen should communicate the V1 signal summary clearly: current signal, confidence, risk grade, regime, eligibility, invalidation, recommended action, and safety state.
- Keep Paper Mode, Advisory Only, No Guaranteed Profit, and historical validation labels visible where relevant.
- Do not clutter the main V1 screen with every advanced diagnostic.

## Advanced Details - Pro Rule

Detailed modules belong inside `Advanced Details - Pro` unless the user explicitly asks for a different layout. Preserve advanced modules for due diligence, including technical analysis, market sentiment, symbol sentiment, pattern analysis, AI advisory, fusion signal, validation, regime, similar setups, trade eligibility, adaptive recommendations, performance, paper review, profile calibration, and diagnostics.

## Futures Paper Scanner Rules

- Futures scanner output is advisory and paper-only.
- Do not place real futures orders.
- Do not simulate live leverage or margin execution as real trading.
- LONG candidates should be visually green.
- SHORT candidates should be visually red.
- WAIT and AVOID candidates should use neutral/default colors.
- Leverage guidance must remain conservative, explicitly paper-only, and liquidation-risk-aware.
- Real futures execution belongs to a later phase after strong validation.

## Data Source Rules

If sentiment, fundamentals, market context, or broader external data are implemented:

- Isolate each source behind a service layer.
- Label source freshness.
- Distinguish live data from derived or inferred data.
- Provide graceful fallback when external data is unavailable.
- Do not fabricate sentiment, fundamentals, validation, or profitability.

## Documentation Rules

When product behavior changes, update `README.md`, `ROADMAP.md`, and `PROGRESS.md` in the same change when relevant. Documentation must match implemented state, safety limitations, and current database setup.

## Persistence Rules

- Default local SQLite path should be repo-local: `sqlite:///./data/binance_ai_bot.db`.
- `data/` should be created automatically when needed.
- Keep WAL enabled where supported.
- If WAL is unavailable, use persistent SQLite default journaling when the configured path is writable.
- Use temp storage only when persistent local storage is not writable or not usable.
- Do not hardcode user-specific paths.

## Evaluation Rules

Every new analysis layer should be measurable. Prefer features that can later answer whether technical analysis, sentiment, fundamentals, pattern analysis, combined signals, or eligibility filters improved paper-trade quality.
