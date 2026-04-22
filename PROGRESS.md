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

## No. 6 — Trade Quality Attribution

- Status: Completed
- Scope:
  - added deterministic trade-quality attribution for closed paper trades
  - exposed symbol/date-scoped trade-quality analytics plus recent closed-trade details
  - added an Auto Trade workstation section for entry/exit quality and trade-management quality
- Backend:
  - added `app/monitoring/trade_quality.py` for MFE, MAE, captured move, giveback, entry quality, exit quality, no-trade gap, and hold-time distribution calculations
  - added `/performance/trade-quality` with `symbol`, `start_date`, `end_date`, `limit`, and `offset`
  - reused persisted `trades` and `market_candle_snapshots` so attribution stays explainable and paper-only
- Frontend:
  - added a `Trade Quality` section in the Auto Trade tab
  - showed recent closed-trade attribution details without returning to a cluttered monitoring dashboard
- Validation:
  - added backend formula and API coverage
  - full backend test suite: passed
  - frontend production build: passed

## No. 7 — Runtime Persistence and Trade Readiness

- Status: Completed
- Scope:
  - made backend runtime/session ownership explicit with stable session metadata and reconnect-friendly status reads
  - added symbol-scoped deterministic trade-readiness payloads so the workstation can explain why the bot is waiting, blocked, entering, exiting, or holding
  - added fee/slippage-aware minimum-edge blocking before paper entries
- Backend:
  - extended runtime status with backend-owned `mode` and `session_id`
  - added workstation `trade_readiness` with runtime activity, signal readiness, risk state, broker readiness, next action, and human-readable blocking reasons
  - added fee-aware entry gating using expected edge versus estimated round-trip fees and slippage
- Frontend:
  - reconnected to backend runtime state after refresh/reopen by adopting the active backend symbol when needed
  - added deterministic execution-readiness panels in Signal and Auto Trade views
  - clarified that AI remains advisory while execution follows deterministic strategy plus risk gating
- Validation:
  - added backend tests for reconnect-style status rereads, paused/readiness states, and fee-aware blocking
  - full backend test suite: passed
  - frontend production build: passed

## No. 8 - Runtime Session Persistence and Broker Recovery

- Status: Completed
- Scope:
  - persisted backend-owned runtime session state across backend restart
  - persisted paper broker balances and open positions for safe recovery
  - restored prior runtime ownership and recovered paper positions visibly without auto-resuming trading
- Backend:
  - added `runtime_session_state`, `paper_broker_state`, and `paper_broker_positions` SQLite tables
  - restored prior runtime state on startup and normalized previously running sessions into a safe paused recovery state
  - restored recovered paper broker balances, realized PnL, and open positions into the runtime runner
  - exposed recovery metadata through bot status and workstation reads
- Frontend:
  - surfaced recovery status, restored broker-state visibility, and recovery guidance in the live control panel
  - kept the workstation symbol-scoped and read-only
- Validation:
  - added storage, runtime, and API tests for restart-style recovery, corrupt persisted state, and reset clearing
  - full backend test suite: passed
  - frontend production build: passed
