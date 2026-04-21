# BINANCE AI BOT — Full Development Roadmap
_Last updated: 2026-04-21_

This document is the **single source of truth** for taking the current Binance AI Bot from an advanced paper-trading prototype to a **fully functional, production-grade trading platform**.

It is written for:
- the human operator / product owner
- Codex / implementation agent
- future contributors

---

## 1. Current status snapshot

### What exists now
The project already includes:

- single-symbol Binance Spot **live market-data ingestion**
- searchable symbol selection from tradable `USDT` Spot pairs
- deterministic strategy pipeline
- deterministic risk engine
- paper execution engine
- paper bot runtime controls:
  - start
  - stop
  - pause
  - resume
  - reset
- SQLite persistence for paper-session data
- FastAPI backend
- React/Vite/Tailwind frontend
- symbol-first workstation UX
- AI advisory signal layer:
  - bias
  - confidence
  - entry preview
  - exit preview
  - suggested action
  - explanation
- AI outcome validation:
  - directional accuracy
  - confidence calibration
  - false positives
  - false reversals
- tests/build checks passing

### What it is right now
This project is currently best described as:

> **A live-data, single-symbol, AI-assisted paper-trading workstation for Binance Spot**

### What it is not yet
It is **not yet**:
- a production-ready live trading bot
- a multi-symbol scanning engine
- a statistically validated trading system
- a commercial-grade robust platform
- a capital-safe launch-ready autonomous trading product

---

## 2. Product goal

## Primary goal
Build a **fully functional, production-grade AI-assisted crypto trading platform** that can:

1. ingest live Binance market data reliably
2. evaluate one or more symbols continuously
3. generate explainable trading signals
4. manage risk deterministically
5. optionally auto-trade with strict safety controls
6. provide a trustworthy control surface and monitoring layer
7. persist all relevant state, outcomes, and analytics
8. prove its usefulness through measurable performance

## Preferred long-term positioning
Do **not** position the end product as:
- “magic AI predicts crypto”

Prefer positioning as:
> **An explainable AI-assisted trading decision and automation platform**

---

## 3. Core product modes to support

The final system should have **three distinct modes**.

### Mode A — Signal Assistant
For a selected symbol, the user can see:
- live market data
- trend / bias
- entry opportunity
- exit opportunity
- AI advisory read
- explanation
- no orders executed

### Mode B — Auto Paper Trading
For a selected symbol or watchlist:
- bot uses live data
- evaluates signals
- applies risk rules
- paper-executes trades
- stores all activity
- supports control panel actions

### Mode C — Live Trading
Only after paper validation:
- real account connectivity
- real position/account state
- capital-safe controls
- operator confirmations or safe automation
- full audit trail

---

## 4. Guiding development principles

Codex and all contributors must follow these rules.

### Safety rules
- keep live execution disabled until explicitly enabled in a dedicated production phase
- AI must never bypass deterministic risk controls
- every trading action must have a reason path
- paper mode remains the default mode
- no hidden side effects from UI actions
- all runtime actions must be state-visible in the API/UI

### Engineering rules
- implement in small reviewable steps
- always add tests where practical
- preserve modularity
- avoid mixing frontend feature work with backend architectural work in one uncontrolled step
- do not add “smartness” before stability
- prefer deterministic and explainable intermediate solutions over black-box shortcuts

### Product rules
- clarity over dashboard clutter
- symbol-first workflow over generic dashboard-first workflow
- latest runtime state must always be distinguishable from old persisted history
- full-page flicker is unacceptable
- no fake confidence presentation

---

## 5. Development phases

---

# Phase 0 — Stabilize current foundation
**Goal:** eliminate drift, runtime issues, and UX confusion from the current paper workstation.

## Must complete
- [ ] verify live runtime works correctly end-to-end against real Binance Spot streams
- [ ] fix all remaining symbol selector issues
- [ ] confirm selected symbol always scopes workstation state correctly
- [ ] confirm no stale cross-symbol data appears in signal views
- [ ] ensure candle history remains strictly ordered and duplicate/out-of-order klines are safely ignored
- [ ] confirm reset clears paper session cleanly
- [ ] confirm pause/resume semantics are intuitive and documented
- [ ] ensure auto-refresh updates sections in place only
- [ ] add backend and frontend logging around runtime transitions

## Acceptance criteria
- selecting a symbol is reliable
- starting the bot uses that symbol only
- signal tab is understandable within 5 seconds
- no stale BTC data appears while another symbol is selected
- no candle-ordering runtime errors remain
- workstation is trusted as a single-symbol paper-trading interface

---

# Phase 1 — AI history and explainability maturity
**Goal:** make the AI advisory layer measurable, inspectable, and historically useful.

## Must complete
- [ ] persist AI advisory snapshots to storage
- [ ] expose AI history API for selected symbol
- [ ] show AI history in the Signal tab
- [ ] track:
  - [ ] bias changes
  - [ ] confidence changes
  - [ ] suggested action changes
  - [ ] entry/exit flag changes
- [ ] add “why the bot acted” narrative evidence trail
- [ ] label all AI outputs clearly as:
  - advisory
  - heuristic / model-driven depending on implementation stage
- [ ] support empty states when insufficient data exists

## Acceptance criteria
- user can inspect latest AI state and recent AI history
- user can see how AI view evolved before and after trades
- AI advice is no longer just a single static card
- explainability is symbol-scoped and human-readable

---

# Phase 2 — Performance analytics and evaluation layer
**Goal:** determine whether the bot is useful, not just operational.

## Must complete
- [ ] compute and expose:
  - [ ] total closed trades
  - [ ] win rate
  - [ ] average win
  - [ ] average loss
  - [ ] expectancy per trade
  - [ ] profit factor
  - [ ] max drawdown
  - [ ] current drawdown
  - [ ] average hold time
  - [ ] longest no-trade period
  - [ ] per-symbol realized PnL
  - [ ] equity curve
  - [ ] drawdown curve
- [ ] separate realized from unrealized PnL
- [ ] show metric definitions in UI
- [ ] add symbol-specific analytics views
- [ ] add timeframe/range filtering for evaluation

## Acceptance criteria
- operator can tell whether strategy quality is improving or degrading
- operator can compare symbols and sessions
- metrics are not misleading or unlabeled
- dashboard is useful for evaluation, not just observation

---

# Phase 3 — AI usefulness validation
**Goal:** prove whether AI helps.

## Must complete
- [x] implement AI-vs-outcome evaluation pipeline
- [ ] compare:
  - [x] AI bias vs subsequent price direction
  - [ ] AI entry suggestion vs later opportunity quality
  - [ ] AI exit suggestion vs realized outcomes
- [x] score AI snapshot usefulness
- [x] add confidence calibration analysis
- [ ] compare deterministic-only vs AI-assisted signal quality
- [ ] identify false positives and false negatives
- [x] add evaluation views/reports

## Acceptance criteria
- the project can answer: “Does AI improve the system?”
- confidence becomes evidence-driven rather than assumed
- AI layer can be tuned based on observed value

---

# Phase 4 — Watch mode and manual trading assistant quality
**Goal:** make the platform highly useful even without auto-trading.

## Must complete
- [ ] add passive Watch mode:
  - no auto-trading
  - live signal tracking only
- [ ] improve signal tab with:
  - [ ] current price
  - [ ] candle summary
  - [ ] entry zone / invalidation
  - [ ] exit zone / stop / target
  - [ ] confidence context
  - [ ] explanation
- [ ] allow easy switching between:
  - [ ] watch
  - [ ] paper auto-trade
- [ ] show current setup state clearly:
  - [ ] no setup
  - [ ] setup forming
  - [ ] entry active
  - [ ] in trade
  - [ ] exit active

## Acceptance criteria
- the system is valuable as a live signal assistant
- the user can watch without auto-trading
- decisions are understandable and actionable

---

# Phase 5 — Multi-symbol scanning and ranking
**Goal:** move from single-symbol workstation to opportunity engine.

## Must complete
- [ ] define “active symbol” clearly
  - [ ] by quote volume
  - [ ] by volatility
  - [ ] by momentum
  - [ ] by watchlist
- [ ] add multi-symbol market-data subscriptions
- [ ] maintain isolated state per symbol
- [ ] run feature extraction per symbol
- [ ] run deterministic strategy per symbol
- [ ] run AI scoring per symbol
- [ ] build ranking engine:
  - [ ] best bullish setups
  - [ ] best bearish setups (if supported)
  - [ ] best low-risk setups
  - [ ] strongest confidence setups
- [ ] add watchlist / shortlist UI

## Acceptance criteria
- the platform can scan multiple symbols safely
- operator can see ranked opportunities instead of manually checking one symbol only
- platform starts becoming differentiated beyond a basic bot

---

# Phase 6 — Strategy framework expansion
**Goal:** support multiple strategies and clearer strategy selection.

## Must complete
- [ ] abstract strategy registry
- [ ] support multiple strategy types, e.g.:
  - [ ] trend-following
  - [ ] breakout
  - [ ] mean reversion
  - [ ] momentum continuation
- [ ] add strategy metadata:
  - [ ] timeframe compatibility
  - [ ] regime compatibility
  - [ ] symbol suitability
- [ ] show active strategy in UI
- [ ] allow strategy selection/configuration in safe modes
- [ ] compare strategy performance

## Acceptance criteria
- platform is no longer locked to one simple signal style
- strategies can be evaluated and replaced cleanly
- strategy logic remains explainable

---

# Phase 7 — Risk engine maturity
**Goal:** make risk logic robust enough for serious deployment.

## Must complete
- [ ] improve position sizing model
- [ ] add symbol-specific sizing controls
- [ ] add session/day/week drawdown stops
- [ ] add per-symbol exposure limits
- [ ] add portfolio exposure limits
- [ ] add cooldown after losing streak
- [ ] add “max trades per period”
- [ ] add slippage tolerance checks
- [ ] add spread/liquidity trade blocking
- [ ] add emergency global kill switch
- [ ] support configurable risk profiles:
  - [ ] conservative
  - [ ] balanced
  - [ ] aggressive

## Acceptance criteria
- risk engine is configurable, visible, and enforced
- capital protection logic is strong enough for non-demo deployment
- no trade can bypass risk checks

---

# Phase 8 — Backtesting, replay, and walk-forward evaluation
**Goal:** validate strategies before live exposure.

## Must complete
- [ ] add historical data ingestion tools
- [ ] implement replay engine using stored/live-compatible data structures
- [ ] implement backtest execution path
- [ ] support:
  - [ ] fees
  - [ ] slippage
  - [ ] latency approximation
- [ ] add result comparison tools
- [ ] add walk-forward evaluation framework
- [ ] add out-of-sample validation
- [ ] compare backtest vs paper/live paper outcomes

## Acceptance criteria
- strategies can be tested before live rollout
- results are not based only on ad hoc paper sessions
- evaluation becomes repeatable

---

# Phase 9 — Replace heuristic AI scorer with trainable model pipeline
**Goal:** move from advisory rules to measurable probabilistic modeling.

## Must complete
- [ ] define prediction target(s), e.g.:
  - [ ] next N-candle direction probability
  - [ ] breakout probability
  - [ ] expected move category
  - [ ] entry quality score
  - [ ] exit urgency score
- [ ] build labeled dataset pipeline
- [ ] implement offline training workflow
- [ ] start with practical tabular models first:
  - [ ] XGBoost / LightGBM / CatBoost
- [ ] add evaluation metrics:
  - [ ] precision
  - [ ] recall
  - [ ] calibration
  - [ ] Brier score / probability quality
- [ ] support model versioning
- [ ] compare trained model vs heuristic scorer
- [ ] keep human-readable explanations

## Acceptance criteria
- AI signal is evidence-backed
- model quality is measured
- production uses versioned, testable signal models

---

# Phase 10 — Persistence and state recovery hardening
**Goal:** survive restarts and recover truth reliably.

## Must complete
- [ ] persist paper broker state
- [ ] restore open paper positions after restart
- [ ] add runtime session recovery
- [ ] clearly distinguish:
  - [ ] current runtime state
  - [ ] historical persisted state
- [ ] persist bot control state if appropriate
- [ ] add event sourcing or stronger ledger consistency where useful
- [ ] prepare migration path from SQLite to PostgreSQL

## Acceptance criteria
- restart does not silently desync system state
- broker/runtime state is durable
- system is suitable for long-lived operation

---

# Phase 11 — Monitoring, alerting, and operational readiness
**Goal:** make the platform operable without babysitting.

## Must complete
- [ ] structured runtime logs
- [ ] alerting on:
  - [ ] data stream disconnect
  - [ ] stale feed
  - [ ] runtime crash
  - [ ] repeated risk rejections
  - [ ] unexpected no-trade period
  - [ ] drawdown breach
  - [ ] bot stopped unexpectedly
- [ ] health endpoints for runtime internals
- [ ] event severity levels
- [ ] operator notification hooks:
  - [ ] email
  - [ ] Telegram
  - [ ] Discord or webhook
- [ ] frontend operator alerts view

## Acceptance criteria
- operator can trust long-running sessions
- failures are visible and actionable
- silent breakdowns are reduced

---

# Phase 12 — Live trading readiness (testnet first, then constrained production)
**Goal:** safely bridge from paper to real execution.

## Must complete
- [ ] Binance Testnet / safe real-execution adapter path
- [ ] account and balance sync
- [ ] real open-order state handling
- [ ] order reconciliation
- [ ] failed order retry/recovery logic
- [ ] explicit trade confirmation rules
- [ ] live mode flags and hard safety gates
- [ ] separate environments:
  - [ ] paper
  - [ ] testnet
  - [ ] production
- [ ] UI mode banners and risk warnings

## Acceptance criteria
- testnet behavior is stable
- production cannot be activated accidentally
- live execution path is robust and visible

---

# Phase 13 — Commercial-grade productization
**Goal:** make it launchable as a serious product.

## Must complete
- [ ] authentication / user accounts if multi-user product
- [ ] API security hardening
- [ ] configuration management
- [ ] environment secrets management
- [ ] role-based access if needed
- [ ] audit trail exports
- [ ] deployment automation
- [ ] backup and restore
- [ ] usage analytics
- [ ] documentation for operators
- [ ] onboarding flows

## Acceptance criteria
- product is usable by non-developers
- operations are manageable
- security and deployment are not ad hoc

---

## 6. Launch-readiness gates

The project must **not** be called a “full-fledged trading bot” until all the following are meaningfully satisfied.

### Gate A — Runtime safety
- [ ] stable live market-data ingestion
- [ ] state recovery
- [ ] alerting
- [ ] no known critical runtime desync bugs

### Gate B — Strategy validity
- [ ] enough paper/live-paper sample size
- [ ] acceptable drawdown
- [ ] metrics visible and reviewed
- [ ] strategy quality validated beyond one symbol

### Gate C — AI validity
- [ ] AI history exists
- [ ] AI usefulness measured
- [ ] confidence interpretation documented
- [ ] advisory or model behavior is calibrated

### Gate D — Operator usability
- [ ] UI is clear
- [ ] symbol workflow is intuitive
- [ ] no full-page flicker
- [ ] controls are reliable
- [ ] explanations are understandable

### Gate E — Execution readiness
- [ ] testnet or controlled live execution path exists
- [ ] reconciliation works
- [ ] kill switch exists
- [ ] mode separation is impossible to confuse

---

## 7. Current USP assessment

### Current USP candidate
The current strongest differentiator is:

> **A symbol-first live Binance workstation that combines explainable deterministic strategy, advisory AI trade interpretation, and paper-trading automation in one interface.**

### Is it a strong USP already?
Partially.

### Why only partially?
Because the current uniqueness is mostly in:
- workflow
- explainability
- control surface

Not yet in:
- proven edge
- superior execution outcomes
- validated AI contribution

### Stronger future USP
A more powerful version would be:

> **A multi-symbol explainable AI trading decision engine that ranks the best real-time setups and only auto-trades when deterministic strategy and AI confidence align under strict risk controls.**

That is a stronger and more defensible USP.

---

## 8. Recommended product positioning by stage

### Right now
Use wording like:
- live paper-trading workstation
- AI-assisted signal and automation platform
- paper trading control console

### Do NOT use yet
- guaranteed profitable bot
- full autonomous trading bot
- launch-ready live trading engine

### Later, after validation
Use wording like:
- explainable AI trading assistant
- probabilistic multi-symbol setup scanner
- controlled auto-trading platform

---

## 9. Codex execution rules

Codex should use this roadmap as the step-by-step tracker.

### For each task:
1. explain plan first
2. implement one checkpoint only
3. run tests/build
4. summarize:
   - what changed
   - risks
   - limitations
   - next best step

### Never do in one uncontrolled step
- mix large backend runtime rewrites with big frontend redesigns
- enable live trading by accident
- replace risk logic without preserving tests
- add AI authority over execution without explicit instruction

### Preferred progression
Always complete the phases in this order unless there is a bug emergency:
1. stabilize
2. measure
3. validate
4. expand
5. automate
6. harden
7. launch

---

## 10. Immediate next recommended phases

### Highest priority now
1. Phase 1 — AI history and explainability maturity
2. Phase 2 — Performance analytics and evaluation
3. Phase 3 — AI usefulness validation
4. Phase 4 — Watch mode and manual assistant quality

### Then
5. Phase 5 — Multi-symbol scanning and ranking
6. Phase 7 — Risk engine maturity
7. Phase 8 — Backtesting / replay
8. Phase 9 — trainable AI model pipeline

---

## 11. Definition of success

This project becomes a **fully functional trading platform** when:

- the runtime is stable
- the UI is clear
- the risk engine is trusted
- AI usefulness is measurable
- symbol scanning/ranking is meaningful
- performance is evaluated rigorously
- state is recoverable
- paper success is repeatable
- live execution is safe and controlled

This project becomes a **game-changing product** only when it can:
- rank opportunities across symbols
- explain why they matter
- show statistically defensible usefulness
- automate only under validated, risk-bounded conditions

---

## 12. Next checkpoint to execute now

### Recommended next implementation step
Implement:

> **Phase 2 — Performance analytics and evaluation layer**

That is the best next step because the workstation now has AI history and initial AI outcome validation, so broader strategy and symbol analytics are the next missing evaluation layer.

---

## 13. Final note

This project is already beyond a dummy MVP.

But it is still in the stage of:

> **advanced prototype / serious paper-trading platform**

The remaining work is about:
- validation
- robustness
- product clarity
- measurable edge
- deployment maturity

That is what will turn it into a real full-fledged system.
