export function scannerCandidateCount(scan) {
  if (!scan) {
    return 0;
  }
  return (
    (scan.long_candidates?.length ?? 0)
    + (scan.short_candidates?.length ?? 0)
    + (scan.neutral_candidates?.length ?? 0)
  );
}

export function hasScannerCandidates(scan) {
  return scannerCandidateCount(scan) > 0;
}

export function isLastSuccessfulScannerCache(scan) {
  return scan?.data_source === 'last_successful_cache' && hasScannerCandidates(scan);
}

export function buildScannerUnavailableMessage(error, hasCachedResults) {
  if (hasCachedResults) {
    return error ?? 'Scanner refresh failed. Showing the last successful scanner result.';
  }
  if (!error) {
    return 'No scanner results yet. Run scanner when Binance API is available.';
  }
  return error
    .replace(/ Previous futures scanner results remain visible\./g, '')
    .replace(/ Previous results remain visible while this refresh is skipped\./g, '');
}
