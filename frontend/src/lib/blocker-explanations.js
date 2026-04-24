function codeList(readiness) {
  if (!readiness) {
    return [];
  }
  return [
    ...(readiness.risk_reason_codes ?? []),
    ...(readiness.signal_reason_codes ?? []),
  ];
}

function matchCode(readiness, ...codes) {
  const values = codeList(readiness);
  return codes.find((code) => values.includes(code)) ?? null;
}

export function explainPrimaryBlocker(readiness) {
  if (!readiness) {
    return null;
  }

  if (!readiness.runtime_active) {
    return {
      title: 'Runtime not started',
      happened: 'The selected symbol is not connected to the live paper runtime yet.',
      why: 'Without live candles and order-book updates, the bot cannot build signals or evaluate risk safely.',
      action: 'Start the live runtime for this symbol first.',
      category: 'system_state',
    };
  }

  if (!readiness.enough_candle_history) {
    return {
      title: 'Waiting for more candles',
      happened: 'The bot does not have enough closed candles yet.',
      why: 'Indicators like EMA and ATR need a minimum history before the setup is trustworthy.',
      action: 'Wait for more closed candles to accumulate.',
      category: 'data_requirement',
    };
  }

  const matched = matchCode(
    readiness,
    'STOP_DISTANCE_TOO_TIGHT',
    'PROTECTIVE_STOP_TOO_TIGHT',
    'EDGE_BELOW_COSTS',
    'EXPECTED_EDGE_TOO_SMALL',
    'MICROSTRUCTURE_UNHEALTHY',
    'VOL_TOO_LOW',
    'VOL_TOO_HIGH',
    'REGIME_NOT_TREND',
    'NO_POSITION_TO_EXIT',
    'NO_POSITION',
  );

  switch (matched) {
    case 'STOP_DISTANCE_TOO_TIGHT':
    case 'PROTECTIVE_STOP_TOO_TIGHT':
      return {
        title: 'Protective stop too tight',
        happened: 'The proposed stop-loss distance is smaller than the minimum safe distance for current volatility.',
        why: 'Normal market noise could hit the stop quickly before the setup has room to work.',
        action: 'Increase stop distance or wait for a cleaner setup with a wider volatility cushion.',
        category: 'risk_protection',
      };
    case 'EDGE_BELOW_COSTS':
    case 'EXPECTED_EDGE_TOO_SMALL':
      return {
        title: 'Edge too small after costs',
        happened: 'The setup does not offer enough expected upside after fees and slippage.',
        why: 'Even a correct direction call could underperform once execution costs are included.',
        action: 'Wait for a stronger setup or a cleaner breakout with more edge.',
        category: 'risk_protection',
      };
    case 'MICROSTRUCTURE_UNHEALTHY':
      return {
        title: 'Spread or liquidity is weak',
        happened: 'The live spread or order-book quality is not healthy enough right now.',
        why: 'Thin liquidity can make fills worse and distort short-horizon setups.',
        action: 'Wait for tighter spread and steadier order-book conditions.',
        category: 'risk_protection',
      };
    case 'VOL_TOO_LOW':
      return {
        title: 'Movement is too quiet',
        happened: 'Current volatility is too weak to activate the setup.',
        why: 'Low movement often means there is not enough edge to overcome costs.',
        action: 'Wait for stronger movement or a clearer trend impulse.',
        category: 'setup_quality',
      };
    case 'VOL_TOO_HIGH':
      return {
        title: 'Volatility is unstable',
        happened: 'Price movement is too erratic for the current setup.',
        why: 'Unstable volatility can invalidate short-horizon signals and stop placement.',
        action: 'Wait for volatility to normalize before trading.',
        category: 'risk_protection',
      };
    case 'REGIME_NOT_TREND':
      return {
        title: 'Trend not confirmed',
        happened: 'The market does not show a strong enough trend yet.',
        why: 'The deterministic strategy needs clearer direction before it can enter with discipline.',
        action: 'Wait for stronger trend confirmation or choose a cleaner symbol.',
        category: 'setup_quality',
      };
    case 'NO_POSITION':
    case 'NO_POSITION_TO_EXIT':
      return {
        title: 'No open position',
        happened: 'There is no open paper position to close.',
        why: 'Exit logic only activates when the broker already holds a live paper position.',
        action: 'Open a paper position first or wait for the next entry setup.',
        category: 'state_info',
      };
    default:
      if ((readiness.blocking_reasons ?? []).length === 0) {
        return null;
      }
      return {
        title: 'Trade is waiting',
        happened: readiness.blocking_reasons[0],
        why: readiness.reason_if_not_trading ?? 'The current setup is not actionable yet.',
        action: 'Keep monitoring the selected symbol for a cleaner setup.',
        category: 'state_info',
      };
  }
}
