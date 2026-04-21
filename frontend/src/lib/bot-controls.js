/**
 * Return whether the Start button should be enabled for the live paper bot.
 *
 * @param {string} selectedSymbol
 * @param {'stopped' | 'running' | 'paused' | 'error'} state
 * @param {boolean} actionLoading
 * @returns {boolean}
 */
export function canStartBot(selectedSymbol, state, actionLoading) {
  return selectedSymbol.trim().length > 0 && state === 'stopped' && actionLoading === false;
}
