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

## No. 9 - Technical Analysis Engine Maturity

- Status: Completed
- Scope:
  - added a dedicated technical-analysis layer for the selected symbol
  - exposed symbol-scoped trend, momentum, structure, volatility, breakout, reversal, and multi-timeframe summaries
  - added a separate Signal-tab technical-analysis section distinct from AI advisory
- Backend:
  - added `app/analysis/technical.py`, `app/analysis/support_resistance.py`, `app/analysis/patterns.py`, `app/analysis/multi_timeframe.py`, and `app/analysis/volatility.py`
  - added `/bot/technical-analysis` with typed empty/incomplete vs ready responses
  - reused live runner candle history and existing feature snapshots without allowing technical output to bypass deterministic risk or execution
- Frontend:
  - added a dedicated `Technical Analysis` section in the Signal tab
  - kept technical state visually separate from AI advisory and current runtime state
  - kept symbol-scoped empty and refreshing states explicit
- Validation:
  - added backend service and API tests for bullish, bearish, sideways, support/resistance, and incomplete-data paths
  - full backend test suite: passed
  - frontend production build: passed

## No. 10 - Multi-Horizon Pattern Analysis

- Status: Completed
- Scope:
  - added a symbol-scoped multi-horizon pattern-analysis layer over user-selectable day ranges
  - exposed range behavior, return, volatility, drawdown, persistence, and breakout/range/reversal tendencies
  - added a dedicated Signal-tab `Pattern Analysis` section with horizon selection
- Backend:
  - added `app/analysis/horizon_analysis.py`, `app/analysis/range_behavior.py`, and `app/analysis/pattern_summary.py`
  - added `/bot/pattern-analysis?symbol=...&horizon=...` with typed `ready`, `waiting_for_runtime`, `waiting_for_history`, and `degraded_storage` states
  - merged persisted close-price history with current live closed candles without allowing pattern analysis to bypass deterministic execution controls
- Frontend:
  - added a separate `Pattern Analysis` Signal-tab section with `1D`, `3D`, `7D`, `14D`, and `30D` selectors
  - kept pattern analysis visually distinct from technical analysis, current bot state, and AI advisory
  - kept horizon-specific refresh behavior in-place without full-page flicker
- Validation:
  - added backend service and API tests for bullish, bearish, choppy, insufficient-history, and drawdown/return calculation paths
  - full backend test suite: passed
  - frontend production build: passed

## No. 11 - Market Sentiment Layer

- Status: Completed
- Scope:
  - added a broader-market sentiment layer for the selected symbol
  - exposed BTC/ETH context, relative strength, market breadth, and volatility environment through a symbol-scoped API
  - added a separate Signal-tab `Market Sentiment` section distinct from technical analysis, pattern analysis, and AI advisory
- Backend:
  - added `app/analysis/market_sentiment.py`, `app/analysis/market_breadth.py`, and `app/data/market_context_service.py`
  - added `/bot/market-sentiment?symbol=...` with typed `ready`, `waiting_for_runtime`, `waiting_for_history`, and `degraded_storage` states
  - reused persisted close-price history plus live closed candles when available, without allowing market sentiment to bypass deterministic execution or risk controls
- Frontend:
  - added a dedicated `Market Sentiment` Signal-tab section with broader-market state, score, BTC/ETH bias, relative strength, breadth, volatility environment, and explanation
  - kept market sentiment visually separate from current bot state, technical analysis, pattern analysis, and AI advisory
  - kept symbol-scoped refresh behavior in-place without full-page flicker
- Validation:
  - added backend service and API tests for bullish, bearish, mixed, insufficient-data, and API-shape paths
  - full backend test suite: passed
  - frontend production build: passed

## No. 12 - AI Robustness Upgrade for Short Timeframes

- Status: Completed
- Scope:
  - upgraded the advisory AI layer with explicit regime classification, short-timeframe noise filters, horizon-specific scoring, and confidence shaping
  - added abstain, low-confidence, and confirmation-needed behavior so the AI can decline weak 5m-style setups
  - extended persisted AI snapshots, API responses, and the Signal-tab AI section with richer advisory context
- Backend:
  - added `app/ai/regime.py`, `app/ai/noise_filters.py`, `app/ai/calibration.py`, and `app/ai/horizon_scoring.py`
  - expanded AI feature extraction to combine technical state, market sentiment context, microstructure sanity, momentum persistence, flip-rate noise, breakout/reversal context, and recent 5m false-signal profile when available
  - added distinct `5m`, `15m`, and `1h` horizon reads with separate confidence, action, and abstain/confirmation behavior
  - extended AI evaluation to track actionable sample size, abstain count/rate, and horizon-specific confidence usage
- Frontend:
  - replaced the old compact AI card with a richer `AI Advisory` section showing regime, noise level, preferred horizon, recommendation, abstain/confirmation flags, horizon reads, and confidence headwinds
  - kept the AI section visually separate from technical analysis, market sentiment, and pattern analysis
- Validation:
  - added backend tests for noisy/choppy abstention, clean trending confidence, breakout-building confirmation, reversal-risk behavior, and horizon differentiation
  - full backend test suite: passed
  - frontend production build: passed

## No. 13 - Symbol Sentiment Layer

- Status: Completed
- Scope:
  - added a symbol-scoped external sentiment layer for the selected symbol
  - exposed a typed `/bot/symbol-sentiment` endpoint with honest `insufficient_data` fallback when no source-backed evidence exists
  - added a separate Signal-tab `Symbol Sentiment` section distinct from technical analysis, pattern analysis, market sentiment, and AI advisory
- Backend:
  - added `app/analysis/symbol_sentiment.py` and `app/analysis/sentiment_scoring.py`
  - added `app/data/news_service.py` and `app/data/sentiment_sources.py` for source-backed evidence abstractions
  - kept the default local setup source-free, so sentiment returns `insufficient_data` instead of fabricating external tone
- Frontend:
  - added a dedicated `Symbol Sentiment` Signal-tab section with state, score, confidence, freshness, source count, explanation, and evidence summary
  - kept symbol sentiment visually separate from current bot state, technical analysis, pattern analysis, market sentiment, and AI advisory
- Validation:
  - added backend service and API tests for bullish, bearish, mixed, insufficient-data, and API-shape paths
  - full backend test suite: passed
  - frontend production build: passed

## No. 14 - Workstation UX Clarity and Log Pagination

- Status: Completed
- Scope:
  - clarified partial and incomplete workstation states in the Signal tab
  - replaced technical execution wording with clearer operator-facing language
  - reduced advisory history noise by showing the latest three entries first with pagination for older history
- Backend:
  - reused existing typed AI-history pagination without changing trading logic or paper-only execution behavior
- Frontend:
  - clarified pattern coverage using covered duration versus requested duration and explicit preliminary labels
  - removed repetitive market-sentiment incomplete messaging in favor of one compact status plus one explanation
  - stopped showing misleading zeroes in the Feature Snapshot when live market data is not available yet
  - humanized execution-readiness actions and hid cost/edge metrics until live readiness inputs exist
  - paginated AI advisory history to three items per page and made the latest three entries visually prominent
- Validation:
  - full backend test suite: passed
  - frontend helper tests: passed
  - frontend production build: passed
