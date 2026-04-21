# Project Progress Log

Chronological implementation checkpoints for Binance AI Bot.

## No. 1 — AI Advisory History Persistence

- Status: Completed
- Scope:
  - persisted symbol-scoped AI advisory snapshots in SQLite
  - added duplicate suppression on materially unchanged advisory outputs
  - exposed latest/history AI advisory API endpoints
  - added Signal-tab AI history UI for the selected symbol
- Backend:
  - added `ai_signal_snapshots` storage with repository methods for insert/latest/history/count
  - persisted AI snapshots on closed-candle processing after the advisory signal is recomputed
  - suppressed inserts when bias, confidence, entry/exit flags, suggested action, explanation, and compact feature summary are unchanged
- Frontend:
  - added symbol-scoped AI Signal history section with confidence trend, bias/action history, and recent advisory snapshots
  - kept empty states and in-place refresh behavior for the workstation UX
- Validation:
  - backend tests: `55 passed`
  - frontend helper tests: passed
  - frontend production build: passed

## No. 2 — AI Outcome Validation

- Status: Completed
- Scope:
  - persisted closed-candle price history for AI outcome comparison
  - evaluated AI bias against later price movement at 5m, 15m, and 1h when data exists
  - exposed symbol-scoped AI outcome validation metrics through the bot API
  - added an AI Evaluation card in the Signal tab
- Backend:
  - added `market_candle_snapshots` storage for closed-candle price outcomes
  - added deterministic evaluation for directional accuracy, confidence calibration, false positives, and false reversals
  - added a symbol-scoped `/bot/ai-signal/evaluation` endpoint
- Frontend:
  - added a Signal-tab AI Evaluation card with horizon summaries and recent evaluated samples
  - kept symbol scoping and in-place refresh behavior
- Validation:
  - targeted backend tests: passed
  - full backend test suite: passed
  - frontend helper tests: passed
  - frontend production build: passed
