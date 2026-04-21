import assert from 'node:assert/strict';

import { buildAiHistoryViewModel } from '../src/lib/ai-history.js';

const empty = buildAiHistoryViewModel('BTCUSDT', []);
assert.deepEqual(empty.items, []);
assert.deepEqual(empty.labels, []);
assert.deepEqual(empty.recentActionChanges, []);

const mixedHistory = [
  {
    symbol: 'BTCUSDT',
    timestamp: '2024-03-09T16:00:00Z',
    bias: 'bullish',
    confidence: 70,
    entry_signal: true,
    exit_signal: false,
    suggested_action: 'enter',
    explanation: 'Bullish setup.',
  },
  {
    symbol: 'ETHUSDT',
    timestamp: '2024-03-09T16:01:00Z',
    bias: 'bearish',
    confidence: 65,
    entry_signal: false,
    exit_signal: true,
    suggested_action: 'exit',
    explanation: 'Bearish setup.',
  },
  {
    symbol: 'BTCUSDT',
    timestamp: '2024-03-09T16:02:00Z',
    bias: 'sideways',
    confidence: 55,
    entry_signal: false,
    exit_signal: false,
    suggested_action: 'wait',
    explanation: 'Wait for confirmation.',
  },
];

const btcOnly = buildAiHistoryViewModel('btcusdt', mixedHistory);
assert.equal(btcOnly.items.length, 2);
assert.deepEqual(
  btcOnly.items.map((item) => item.symbol),
  ['BTCUSDT', 'BTCUSDT'],
);
assert.deepEqual(btcOnly.confidenceValues, [70, 55]);
assert.deepEqual(
  btcOnly.recentActionChanges.map((item) => item.suggested_action),
  ['wait', 'enter'],
);
