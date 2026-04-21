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

## No. 3 â€” Workstation Empty-State Hardening

- Status: Completed
- Scope:
  - hardened symbol-scoped workstation and AI endpoints against missing runtime state and partial local storage state
  - added SQLite compatibility guards for optional AI history/evaluation tables
  - ensured empty AI history/evaluation paths return typed neutral payloads instead of 500 errors
- Backend:
  - added neutral workstation fallback behavior when runtime state cannot be built
  - added safe empty responses for `/bot/ai-signal`, `/bot/ai-signal/history`, and `/bot/ai-signal/evaluation`
  - made local SQLite initialization add missing optional AI/evaluation columns for older paper-mode files
  - made optional AI snapshot/candle reads and writes degrade gracefully when schema drift is encountered
- Validation:
  - added regression tests for no-runtime, no-history, no-evaluation, reset-followed-by-read, runtime failure, and old-SQLite-schema cases
  - backend tests: passed

## No. 4 â€” Workstation Data-State Visibility

- Status: Completed
- Scope:
  - exposed a symbol-scoped workstation `data_state` and user-readable status message
  - extended AI history and AI evaluation responses with the same readiness/degradation visibility
  - surfaced the new status indicators in the Signal and Auto Trade tabs without changing the paper-only execution model
- Backend:
  - added `ready`, `waiting_for_runtime`, `waiting_for_history`, and `degraded_storage` response states
  - derived workstation readiness from runtime attachment, live feature availability, and optional storage degradation
  - derived AI history/evaluation readiness from persisted data availability, runtime status, and optional storage health
- Frontend:
  - added compact data-state indicators in the Signal and Auto Trade tabs
  - used symbol-scoped backend status messages to explain empty AI history/evaluation sections
- Validation:
  - added backend tests for ready, waiting-for-runtime, waiting-for-history, and degraded-storage paths
  - full backend test suite: passed
  - frontend production build: passed

## No. 5 â€” Performance Analytics Completion

- Status: Completed
- Scope:
  - completed closed-trade performance analytics for expectancy, profit factor, hold time, average win/loss, drawdown, and realized vs unrealized PnL separation
  - added a symbol/date-scoped performance endpoint for the workstation
  - added a workstation performance section in the Auto Trade tab
- Backend:
  - added deterministic performance analytics formulas in `app/monitoring/metrics.py`
  - added `/performance` with optional `symbol`, `start_date`, and `end_date` filters
  - extended repository/data-access helpers for latest equity snapshots within a date range
- Frontend:
  - added a `Performance Analytics` section with expectancy, profit factor, average hold time, average win/loss, drawdown, and sample size
  - kept refresh behavior in-place and symbol-scoped
- Validation:
  - added backend metric and API coverage
  - full backend test suite: passed
  - frontend production build: passed
