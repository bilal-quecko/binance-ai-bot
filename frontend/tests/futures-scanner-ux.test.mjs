import assert from 'node:assert/strict';

import {
  buildScannerUnavailableMessage,
  hasScannerCandidates,
  isLastSuccessfulScannerCache,
  scannerCandidateCount,
} from '../src/lib/futures-scanner-ux.js';

const emptyScan = {
  long_candidates: [],
  short_candidates: [],
  neutral_candidates: [],
  data_source: 'empty_degraded',
};

assert.equal(scannerCandidateCount(null), 0);
assert.equal(hasScannerCandidates(emptyScan), false);
assert.equal(
  buildScannerUnavailableMessage(
    'Binance API temporarily unavailable. Previous futures scanner results remain visible.',
    false,
  ),
  'Binance API temporarily unavailable.',
);

const cachedScan = {
  long_candidates: [{ symbol: 'BTCUSDT' }],
  short_candidates: [],
  neutral_candidates: [],
  data_source: 'last_successful_cache',
};

assert.equal(scannerCandidateCount(cachedScan), 1);
assert.equal(hasScannerCandidates(cachedScan), true);
assert.equal(isLastSuccessfulScannerCache(cachedScan), true);
assert.match(
  buildScannerUnavailableMessage('Binance API temporarily unavailable.', true),
  /Binance API temporarily unavailable/i,
);
