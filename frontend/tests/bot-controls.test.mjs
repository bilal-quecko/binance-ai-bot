import assert from 'node:assert/strict';

import { canStartBot } from '../src/lib/bot-controls.js';

assert.equal(canStartBot('', 'stopped', false), false);
assert.equal(canStartBot('BTCUSDT', 'stopped', false), true);
assert.equal(canStartBot('BTCUSDT', 'running', false), false);
assert.equal(canStartBot('BTCUSDT', 'stopped', true), false);
