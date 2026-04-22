function humanize(value) {
  if (!value) {
    return '-';
  }
  return value.split('_').join(' ');
}

function horizonDays(horizon) {
  switch ((horizon ?? '').toLowerCase()) {
    case '1d':
      return 1;
    case '3d':
      return 3;
    case '7d':
      return 7;
    case '14d':
      return 14;
    case '30d':
      return 30;
    default:
      return null;
  }
}

export function formatDurationLabel(start, end) {
  if (!start || !end) {
    return 'No coverage yet';
  }

  const startTime = Date.parse(start);
  const endTime = Date.parse(end);
  if (Number.isNaN(startTime) || Number.isNaN(endTime) || endTime <= startTime) {
    return 'Coverage still building';
  }

  let totalMinutes = Math.max(1, Math.round((endTime - startTime) / 60000));
  const days = Math.floor(totalMinutes / 1440);
  totalMinutes -= days * 1440;
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes - hours * 60;

  const parts = [];
  if (days > 0) {
    parts.push(`${days}d`);
  }
  if (hours > 0) {
    parts.push(`${hours}h`);
  }
  if (days === 0 && minutes > 0) {
    parts.push(`${minutes}m`);
  }
  return parts.join(' ');
}

export function buildPatternCoverageSummary(analysis) {
  const requestedDays = horizonDays(analysis?.horizon);
  const requestedDuration = requestedDays ? `${requestedDays}d requested` : 'Requested range';
  const coveredDuration = formatDurationLabel(analysis?.coverage_start ?? null, analysis?.coverage_end ?? null);
  const hasWindow = Boolean(analysis?.coverage_start && analysis?.coverage_end);
  const isPreliminary = Boolean(analysis?.partial_coverage || analysis?.data_state !== 'ready');
  const coverageRatio = analysis?.coverage_ratio_pct ?? null;

  const helperParts = [];
  if (hasWindow) {
    helperParts.push(`${coveredDuration} covered`);
  }
  helperParts.push(requestedDuration);
  if (coverageRatio !== null && Number(coverageRatio) > 0) {
    helperParts.push(`${coverageRatio}% of target history`);
  }
  if (isPreliminary) {
    helperParts.push('Preliminary read');
  }

  return {
    value: hasWindow ? `${coveredDuration} of ${requestedDays ? `${requestedDays}d` : 'requested range'}` : requestedDuration,
    helper: helperParts.join(' · '),
    isPreliminary,
  };
}

export function humanizeReadinessAction(nextAction) {
  switch (nextAction) {
    case 'start_runtime':
      return 'Start live runtime';
    case 'resume_runtime':
    case 'resume_auto_trade':
      return 'Resume auto trade';
    case 'wait_for_history':
      return 'Wait for more history';
    case 'enter':
      return 'Allow next entry';
    case 'exit':
      return 'Allow exit';
    case 'hold':
    case 'hold_position':
      return 'Hold position';
    default:
      return humanize(nextAction);
  }
}

export function humanizeMode(mode) {
  switch (mode) {
    case 'auto_paper':
      return 'Auto paper';
    case 'paused':
      return 'Paused';
    case 'stopped':
      return 'Stopped';
    case 'error':
      return 'Attention needed';
    default:
      return humanize(mode);
  }
}

export function describeReadiness(readiness) {
  if (!readiness) {
    return 'Deterministic execution readiness is not available yet.';
  }
  if (!readiness.runtime_active) {
    return 'Live runtime is inactive for this symbol. Start the runtime to receive live candles, features, and execution context.';
  }
  if (!readiness.enough_candle_history) {
    return 'Live data is connected, but more closed candles are needed before deterministic entry and exit checks can be trusted.';
  }
  if (!readiness.broker_ready) {
    return 'Paper broker state is not ready yet, so the workstation stays in observation mode.';
  }
  if (readiness.risk_blocked) {
    return readiness.reason_if_not_trading || 'Risk is currently blocking the next deterministic action.';
  }
  return readiness.reason_if_not_trading || 'Deterministic execution conditions are ready.';
}

export function shouldShowCostMetrics(readiness) {
  if (!readiness) {
    return false;
  }
  return Boolean(
    readiness.runtime_active
      && readiness.enough_candle_history
      && (readiness.expected_edge_pct !== null || readiness.estimated_round_trip_cost_pct !== null),
  );
}
