import assert from 'node:assert/strict';

import {
  buildPatternCoverageSummary,
  describeReadiness,
  humanizeMode,
  humanizeReadinessAction,
  shouldShowCostMetrics,
} from '../src/lib/workstation-ux.js';

assert.equal(humanizeReadinessAction('start_runtime'), 'Start live runtime');
assert.equal(humanizeReadinessAction('wait_for_history'), 'Wait for more history');
assert.equal(humanizeMode('auto_paper'), 'Auto paper');

const inactiveReadiness = {
  runtime_active: false,
  enough_candle_history: false,
  broker_ready: false,
  risk_blocked: false,
  reason_if_not_trading: 'Start the live runtime first.',
  expected_edge_pct: null,
  estimated_round_trip_cost_pct: null,
};

assert.match(describeReadiness(inactiveReadiness), /Start the runtime/i);
assert.equal(shouldShowCostMetrics(inactiveReadiness), false);

const activeReadiness = {
  runtime_active: true,
  enough_candle_history: true,
  broker_ready: true,
  risk_blocked: false,
  reason_if_not_trading: null,
  expected_edge_pct: '0.8',
  estimated_round_trip_cost_pct: '0.2',
};

assert.equal(shouldShowCostMetrics(activeReadiness), true);

const coverage = buildPatternCoverageSummary({
  horizon: '7d',
  coverage_start: '2024-03-01T00:00:00Z',
  coverage_end: '2024-03-03T12:00:00Z',
  coverage_ratio_pct: '0',
  partial_coverage: true,
  data_state: 'waiting_for_history',
});

assert.equal(coverage.value, '2d 12h of 7d');
assert.match(coverage.helper, /Preliminary read/);
assert.ok(!coverage.helper.includes('0%'));
