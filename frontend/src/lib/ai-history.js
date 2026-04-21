export function biasToScore(bias) {
  if (bias === 'bullish') {
    return 1;
  }
  if (bias === 'bearish') {
    return -1;
  }
  return 0;
}

export function buildAiHistoryViewModel(selectedSymbol, items) {
  const normalizedSymbol = (selectedSymbol ?? '').trim().toUpperCase();
  const filtered = items
    .filter((item) => !normalizedSymbol || item.symbol.toUpperCase() === normalizedSymbol)
    .sort((left, right) => Date.parse(left.timestamp) - Date.parse(right.timestamp));

  const labels = filtered.map((item) => item.timestamp);
  const confidenceValues = filtered.map((item) => Number(item.confidence));
  const biasValues = filtered.map((item) => biasToScore(item.bias));
  const recentItems = [...filtered].reverse();
  const recentActionChanges = filtered.filter((item, index) => {
    if (index === 0) {
      return true;
    }
    return filtered[index - 1].suggested_action !== item.suggested_action;
  }).reverse();

  return {
    items: filtered,
    recentItems,
    recentActionChanges,
    labels,
    confidenceValues,
    biasValues,
  };
}
