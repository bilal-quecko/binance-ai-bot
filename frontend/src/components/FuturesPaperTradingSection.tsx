import { useEffect, useState } from 'react';
import {
  getFuturesPaperPerformance,
  getFuturesPaperSignal,
  getFuturesPaperStatus,
  manualFuturesClose,
  manualFuturesLong,
  manualFuturesShort,
  startFuturesPaper,
  stopFuturesPaper,
} from '../lib/api';
import type {
  FuturesPaperFillResponse,
  FuturesPaperPerformanceResponse,
  FuturesPaperExecutionSignalResponse,
  FuturesPaperStatusResponse,
} from '../lib/types';
import { formatCurrency, formatReasonCodes } from '../lib/format';
import { MetricCard } from './MetricCard';
import { StatePanel } from './StatePanel';

interface FuturesPaperTradingSectionProps {
  symbol: string;
}

export function FuturesPaperTradingSection({ symbol }: FuturesPaperTradingSectionProps) {
  const [status, setStatus] = useState<FuturesPaperStatusResponse | null>(null);
  const [signal, setSignal] = useState<FuturesPaperExecutionSignalResponse | null>(null);
  const [performance, setPerformance] = useState<FuturesPaperPerformanceResponse | null>(null);
  const [marketPrice, setMarketPrice] = useState('');
  const [quantity, setQuantity] = useState('0.001');
  const [leverage, setLeverage] = useState(2);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const position = status?.positions.find((item) => item.symbol === symbol.toUpperCase()) ?? null;

  const refresh = async () => {
    if (!symbol) {
      return;
    }
    setError(null);
    const [nextStatus, nextSignal, nextPerformance] = await Promise.all([
      getFuturesPaperStatus(),
      getFuturesPaperSignal(symbol),
      getFuturesPaperPerformance(symbol),
    ]);
    setStatus(nextStatus);
    setSignal(nextSignal);
    setPerformance(nextPerformance);
  };

  useEffect(() => {
    void refresh().catch((err: unknown) => {
      setError(err instanceof Error ? err.message : 'Unable to load paper Futures state.');
    });
  }, [symbol]);

  const runAction = async (action: () => Promise<FuturesPaperFillResponse | FuturesPaperStatusResponse>) => {
    setLoading(true);
    setError(null);
    setMessage(null);
    try {
      const result = await action();
      if ('positions' in result) {
        setMessage(`Futures paper runtime ${result.active ? 'started' : 'stopped'}.`);
      } else {
        setMessage(`Paper Futures ${result.side} ${result.status}.`);
      }
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Paper Futures action failed.');
    } finally {
      setLoading(false);
    }
  };

  if (!symbol) {
    return <StatePanel title="No symbol selected" message="Select a symbol to use paper Futures controls." tone="empty" />;
  }

  return (
    <section className="space-y-4">
      <div className="rounded-lg border border-sky-400/20 bg-sky-400/10 p-4">
        <p className="text-sm font-semibold text-sky-100">Paper Futures only. No real Binance Futures orders are placed.</p>
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(320px,0.8fr)]">
        <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Futures Paper</p>
              <h3 className="mt-1 text-lg font-semibold text-white">{symbol.toUpperCase()}</h3>
            </div>
            <div className="flex flex-wrap gap-2">
              <button type="button" disabled={loading} onClick={() => void runAction(startFuturesPaper)} className="rounded-md border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-xs font-semibold text-emerald-100 disabled:opacity-50">Start</button>
              <button type="button" disabled={loading} onClick={() => void runAction(stopFuturesPaper)} className="rounded-md border border-rose-400/30 bg-rose-400/10 px-3 py-2 text-xs font-semibold text-rose-100 disabled:opacity-50">Stop</button>
            </div>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Signal" value={signal?.signal ?? 'WAIT'} helper={formatReasonCodes(signal?.reason_codes ?? [])} />
            <MetricCard label="Confidence" value={signal ? `${signal.confidence}%` : '-'} helper="Deterministic engine" />
            <MetricCard label="Risk Grade" value={signal?.risk_grade ?? '-'} helper={signal?.blocker_reason ?? 'Paper risk only'} />
            <MetricCard label="Runtime" value={status?.active ? 'Active' : 'Stopped'} helper="Paper Futures service" />
            <MetricCard label="Position Side" value={position?.side ?? 'None'} helper="Current paper position" />
            <MetricCard label="Entry Price" value={position ? formatCurrency(position.entry_price) : '-'} helper="Paper fill" />
            <MetricCard label="Mark Price" value={position ? formatCurrency(position.mark_price) : '-'} helper="Manual mark input" />
            <MetricCard label="Leverage" value={position ? `${position.leverage}x` : `${leverage}x`} helper="Conservative max 3x" />
            <MetricCard label="Margin Used" value={position ? formatCurrency(position.margin_used) : '-'} helper="Isolated paper margin" />
            <MetricCard label="Unrealized PnL" value={position ? formatCurrency(position.unrealized_pnl) : '-'} helper="Marked to paper price" />
            <MetricCard label="Realized PnL" value={formatCurrency(status?.realized_pnl ?? performance?.realized_pnl ?? '0')} helper="Paper only" />
            <MetricCard label="Liq. Estimate" value={position ? formatCurrency(position.liquidation_price_estimate) : '-'} helper="Estimated reference only" />
          </div>
        </div>
        <div className="rounded-lg border border-slate-800 bg-slate-950/50 p-4">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">Manual Paper Controls</p>
          <div className="mt-4 space-y-3">
            <label className="block text-xs font-semibold text-slate-400">
              Market Price
              <input value={marketPrice} onChange={(event) => setMarketPrice(event.target.value)} className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white" placeholder="e.g. 65000" />
            </label>
            <label className="block text-xs font-semibold text-slate-400">
              Quantity
              <input value={quantity} onChange={(event) => setQuantity(event.target.value)} className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white" />
            </label>
            <label className="block text-xs font-semibold text-slate-400">
              Leverage
              <select value={leverage} onChange={(event) => setLeverage(Number(event.target.value))} className="mt-1 w-full rounded-md border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white">
                <option value={1}>1x</option>
                <option value={2}>2x</option>
                <option value={3}>3x</option>
              </select>
            </label>
            <div className="grid grid-cols-3 gap-2">
              <button type="button" disabled={loading || !marketPrice} onClick={() => void runAction(() => manualFuturesLong(symbol, marketPrice, quantity, leverage))} className="rounded-md border border-emerald-400/30 bg-emerald-400/10 px-3 py-2 text-xs font-semibold text-emerald-100 disabled:opacity-50">LONG</button>
              <button type="button" disabled={loading || !marketPrice} onClick={() => void runAction(() => manualFuturesShort(symbol, marketPrice, quantity, leverage))} className="rounded-md border border-rose-400/30 bg-rose-400/10 px-3 py-2 text-xs font-semibold text-rose-100 disabled:opacity-50">SHORT</button>
              <button type="button" disabled={loading || !marketPrice} onClick={() => void runAction(() => manualFuturesClose(symbol, marketPrice))} className="rounded-md border border-slate-600 bg-slate-800 px-3 py-2 text-xs font-semibold text-slate-100 disabled:opacity-50">CLOSE</button>
            </div>
            {message ? <p className="text-sm text-emerald-300">{message}</p> : null}
            {error ? <p className="text-sm text-rose-300">{error}</p> : null}
          </div>
          <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/70 p-3 text-xs text-slate-400">
            Recent paper fills: {performance?.total_fills ?? 0}
          </div>
        </div>
      </div>
    </section>
  );
}
