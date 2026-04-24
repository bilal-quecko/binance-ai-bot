import assert from 'node:assert/strict';

import { explainPrimaryBlocker } from '../src/lib/blocker-explanations.js';

const stopTight = explainPrimaryBlocker({
  runtime_active: true,
  enough_candle_history: true,
  risk_reason_codes: ['STOP_DISTANCE_TOO_TIGHT'],
  signal_reason_codes: [],
  blocking_reasons: ['The protective stop is too tight relative to current price movement.'],
  reason_if_not_trading: 'The protective stop is too tight relative to current price movement.',
});

assert.equal(stopTight.title, 'Protective stop too tight');
assert.match(stopTight.why, /Normal market noise could hit the stop quickly/i);
assert.equal(stopTight.category, 'risk_protection');

const waitingForHistory = explainPrimaryBlocker({
  runtime_active: true,
  enough_candle_history: false,
  risk_reason_codes: [],
  signal_reason_codes: [],
  blocking_reasons: ['Need more closed candles before deterministic entries and exits can activate.'],
  reason_if_not_trading: 'Waiting for enough closed candle history.',
});

assert.equal(waitingForHistory.title, 'Waiting for more candles');
assert.equal(waitingForHistory.category, 'data_requirement');
