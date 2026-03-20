import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { API_BASE } from '../utils/constants';
import { SectionCard } from '../components/SectionCard';
import { DataTable } from '../components/DataTable';
import { formatPnl, formatPrice, formatBps, formatTimestamp, formatTimeAgo, pnlColor, truncate, formatPercent } from '../utils/formatters';
import { FlaskConical } from 'lucide-react';

const api = axios.create({ baseURL: API_BASE });

export default function QuantLab() {
  const [report, setReport] = useState(null);
  const [evaluations, setEvaluations] = useState([]);
  const [positions, setPositions] = useState([]);
  const [closed, setClosed] = useState([]);

  const refresh = useCallback(async () => {
    try {
      const [rpt, evals, pos, cls] = await Promise.all([
        api.get('/shadow/report'),
        api.get('/shadow/evaluations?limit=100'),
        api.get('/shadow/positions'),
        api.get('/shadow/closed?limit=50'),
      ]);
      setReport(rpt.data);
      setEvaluations(evals.data);
      setPositions(pos.data);
      setClosed(cls.data);
    } catch { /* silent */ }
  }, []);

  useEffect(() => {
    refresh();
    const iv = setInterval(refresh, 8000);
    return () => clearInterval(iv);
  }, [refresh]);

  const comp = report?.comparison || {};
  const live = comp.live || {};
  const shadow = comp.shadow || {};
  const rolling = report?.rolling_pnl || {};
  const cfg = report?.config || {};
  const sizing = report?.sizing || {};
  const totalEvals = report?.total_evaluations || 0;
  const meaningfulEvals = report?.meaningful_evaluations || 0;

  const shadowClosedCount = shadow.closed_trades || 0;
  const binaryResolved = shadow.binary_resolved_count || 0;
  const shadowPnlPerTrade = shadowClosedCount > 0
    ? formatPnl(shadow.pnl_total / shadowClosedCount)
    : '—';

  return (
    <div data-testid="quant-lab-page" className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <FlaskConical size={20} className="text-indigo-400" />
          <h1 className="text-lg font-semibold text-zinc-100">Quant Lab</h1>
        </div>
        <span className="text-xs text-zinc-600 font-mono">
          {totalEvals} evals ({meaningfulEvals} meaningful) | Last: {report?.last_eval_time ? formatTimeAgo(report.last_eval_time) : '—'}
        </span>
      </div>

      {/* Shadow Banner */}
      <div data-testid="shadow-banner" className="flex items-center gap-3 px-4 py-2.5 border border-dashed border-indigo-500/40 bg-indigo-950/20 rounded-lg">
        <div className="w-2 h-2 rounded-full bg-indigo-400 animate-pulse shrink-0" />
        <span className="text-xs font-semibold text-indigo-300 tracking-wide uppercase">Shadow Only</span>
        <span className="text-xs text-zinc-500">No live execution — all positions and PnL are hypothetical</span>
        {sizing.type && (
          <span className="text-[10px] text-amber-500/70 font-mono border border-amber-500/20 rounded px-1.5 py-0.5">
            Unit-size: ${sizing.per_signal_size}/signal · No accumulation
          </span>
        )}
        <div className="ml-auto text-xs text-zinc-600 font-mono">
          {report?.status === 'active' ? 'ACTIVE' : report?.status || '—'}
        </div>
      </div>

      {/* A) Live vs Shadow Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
        <MetricCard testId="metric-live-trades" label="Live Signals" value={live.trade_count ?? 0} sub="actual trade signals" />
        <MetricCard testId="metric-shadow-trades" label="Shadow Signals" value={shadow.trade_count ?? 0} sub="would-trade signals" accent />
        <MetricCard testId="metric-shadow-win-rate" label="Shadow Win Rate (Binary)" value={shadow.binary_win_rate != null ? formatPercent(shadow.binary_win_rate * 100, 1) : '—'} sub={`${binaryResolved} binary-resolved`} accent />
        <MetricCard testId="metric-meaningful-agreement" label="Agreement Rate"
          value={comp.meaningful_agreement_rate != null ? formatPercent(comp.meaningful_agreement_rate * 100, 1) : '—'}
          sub={`${meaningfulEvals} meaningful evals`} />
        <MetricCard testId="metric-shadow-overall-win" label="Shadow Win Rate (All)" value={shadow.win_rate != null ? formatPercent(shadow.win_rate * 100, 1) : '—'} sub={`${shadowClosedCount} total closed`} accent />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <MetricCard testId="metric-shadow-pnl" label="Shadow PnL (unit-size)" value={formatPnl(shadow.pnl_total || 0)} format="pnl" accent />
        <MetricCard testId="metric-shadow-pnl-trade" label="PnL/Trade (unit)" value={shadowPnlPerTrade} format="pnl" accent />
        <MetricCard testId="metric-rolling-1h" label="Rolling 1h" value={formatPnl(rolling['1h'] || 0)} format="pnl" accent />
        <MetricCard testId="metric-rolling-3h" label="Rolling 3h" value={formatPnl(rolling['3h'] || 0)} format="pnl" accent />
        <MetricCard testId="metric-rolling-6h" label="Rolling 6h" value={formatPnl(rolling['6h'] || 0)} format="pnl" accent />
        <MetricCard testId="metric-edge" label="Shadow Avg Edge" value={shadow.avg_edge_bps != null ? `${shadow.avg_edge_bps} bps` : '—'} accent />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <MetricCard testId="metric-open-positions" label="Open Hypothetical" value={shadow.open_positions ?? positions.length} accent />
        <MetricCard testId="metric-false-pos" label="False Positives" value={comp.false_positives ?? 0} sub="shadow traded, resolved to loss" />
        <MetricCard testId="metric-false-neg" label="False Negatives" value={comp.false_negatives ?? 0} sub="shadow skipped, live would've won" />
        <MetricCard testId="metric-live-edge" label="Live Avg Edge" value={live.avg_edge_bps != null ? `${live.avg_edge_bps} bps` : '—'} />
      </div>

      {/* B) Shadow Config + Sizing */}
      <SectionCard title="Shadow Config" testId="section-shadow-config"
        action={<span className="text-[10px] text-indigo-400/60 font-mono uppercase tracking-wider">Experiment Parameters</span>}>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-x-8 gap-y-2 text-xs">
          <ConfigRow label="EV-Gap Threshold" value={cfg.min_ev_ratio != null ? `${(cfg.min_ev_ratio * 100).toFixed(1)}%` : '—'} />
          <ConfigRow label="Pseudo-Stoikov" value="Enabled" active />
          <ConfigRow label="Gamma (Risk Aversion)" value={cfg.gamma ?? '—'} />
          <ConfigRow label="Inventory Decay" value={cfg.inventory_decay ?? '—'} />
          <ConfigRow label="Sizing" value={`$${sizing.per_signal_size || '?'}/signal (unit, no accum.)`} />
        </div>
      </SectionCard>

      {/* C) Open Hypothetical Positions */}
      <SectionCard
        title={`Open Hypothetical Positions (${positions.length})`}
        testId="section-shadow-open"
        action={<UnitBadge />}
      >
        <DataTable
          columns={openPosColumns}
          data={positions}
          emptyMessage="No open hypothetical positions"
          testId="shadow-open-table"
        />
      </SectionCard>

      {/* D) Closed Hypothetical Positions */}
      <SectionCard
        title={`Closed Hypothetical Trades (${closed.length})`}
        testId="section-shadow-closed"
        action={<UnitBadge />}
      >
        <DataTable
          columns={closedPosColumns}
          data={closed}
          emptyMessage="No resolved shadow trades yet — waiting for binary outcomes"
          testId="shadow-closed-table"
        />
      </SectionCard>

      {/* E) Recent Evaluations */}
      <SectionCard
        title={`Recent Evaluations (${evaluations.length})`}
        testId="section-shadow-evals"
        action={<span className="text-[10px] text-indigo-400/60 font-mono uppercase tracking-wider">Live vs Shadow</span>}
      >
        <DataTable
          columns={evalColumns}
          data={evaluations}
          emptyMessage="No evaluations yet — waiting for crypto sniper scan cycle"
          testId="shadow-evals-table"
        />
      </SectionCard>
    </div>
  );
}

// ---- Sub-components ----

function UnitBadge() {
  return (
    <span className="text-[10px] text-amber-500/70 font-mono border border-amber-500/20 rounded px-1.5 py-0.5">
      Unit-size research PnL
    </span>
  );
}

function MetricCard({ label, value, sub, format, testId, accent }) {
  let colorClass = accent ? 'text-indigo-300' : 'text-zinc-100';
  if (format === 'pnl' && typeof value === 'string') {
    if (value.startsWith('+') && value !== '+$0.00') colorClass = 'text-emerald-400';
    else if (value.startsWith('-')) colorClass = 'text-red-400';
    else colorClass = 'text-zinc-400';
  }
  return (
    <div data-testid={testId} className={`border rounded-lg px-4 py-3 ${accent ? 'bg-indigo-950/20 border-indigo-500/20' : 'bg-zinc-900/60 border-zinc-800'}`}>
      <div className="text-[11px] text-zinc-500 mb-1">{label}</div>
      <div className={`text-base font-semibold font-mono leading-tight ${colorClass}`}>
        {value ?? '—'}
      </div>
      {sub && <div className="text-[10px] text-zinc-600 mt-0.5">{sub}</div>}
    </div>
  );
}

function ConfigRow({ label, value, active }) {
  return (
    <div className="flex justify-between py-1">
      <span className="text-zinc-500">{label}</span>
      <span className={`font-mono ${active ? 'text-indigo-300' : 'text-zinc-300'}`}>{value}</span>
    </div>
  );
}

// ---- Table columns ----

const openPosColumns = [
  { key: 'question', label: 'Market', render: (v) => <span className="text-zinc-300 max-w-[180px] truncate block">{truncate(v, 45)}</span> },
  { key: 'asset', label: 'Asset', render: (v) => <span className="text-zinc-200 font-medium">{v}</span> },
  { key: 'side', label: 'Side', render: (v) => <span className={v === 'buy_yes' ? 'text-emerald-400' : v === 'buy_no' ? 'text-red-400' : 'text-zinc-500'}>{v}</span> },
  { key: 'size', label: 'Size', align: 'right', render: (v) => <span className="font-mono text-zinc-300">{v}</span> },
  { key: 'notional', label: 'Notional', align: 'right', render: (v) => <span className="font-mono text-zinc-400">${typeof v === 'number' ? v.toFixed(2) : '—'}</span> },
  { key: 'entry_price', label: 'Entry', align: 'right', render: (v) => <span className="font-mono">{formatPrice(v)}</span> },
  { key: 'current_price', label: 'Mark', align: 'right', render: (v) => <span className="font-mono text-zinc-200">{v != null ? formatPrice(v) : '—'}</span> },
  { key: 'unrealized_pnl', label: 'Unrl PnL', align: 'right', sortable: true, render: (v) => <span className={`font-mono font-medium ${pnlColor(v)}`}>{formatPnl(v)}</span> },
  { key: 'ev_ratio', label: 'EV Ratio', align: 'right', sortable: true, render: (v) => <span className="font-mono text-indigo-300">{v != null ? `${(v * 100).toFixed(1)}%` : '—'}</span> },
  { key: 'stoikov_edge_bps', label: 'Stoikov Edge', align: 'right', sortable: true, render: (v) => <span className="font-mono text-indigo-300">{v != null ? formatBps(v) : '—'}</span> },
  { key: 'opened_at', label: 'Opened', render: (v) => <span className="text-zinc-500">{formatTimeAgo(v)}</span> },
];

const closedPosColumns = [
  { key: 'question', label: 'Market', render: (v) => <span className="text-zinc-300 max-w-[180px] truncate block">{truncate(v, 45)}</span> },
  { key: 'asset', label: 'Asset', render: (v) => <span className="text-zinc-200 font-medium">{v}</span> },
  { key: 'side', label: 'Side', render: (v) => <span className={v === 'buy_yes' ? 'text-emerald-400' : v === 'buy_no' ? 'text-red-400' : 'text-zinc-500'}>{v}</span> },
  { key: 'size', label: 'Size', align: 'right', render: (v) => <span className="font-mono text-zinc-300">{v}</span> },
  { key: 'entry_price', label: 'Entry', align: 'right', render: (v) => <span className="font-mono">{formatPrice(v)}</span> },
  { key: 'exit_price', label: 'Exit', align: 'right', render: (v) => <span className="font-mono">{formatPrice(v)}</span> },
  { key: 'pnl', label: 'PnL', align: 'right', sortable: true, render: (v) => <span className={`font-mono font-semibold ${pnlColor(v)}`}>{formatPnl(v)}</span> },
  { key: 'won', label: 'Result', render: (v) => <span className={v ? 'text-emerald-400' : 'text-red-400'}>{v ? 'WIN' : 'LOSS'}</span> },
  { key: 'resolution_type', label: 'Resolution', render: (v) => {
    const colors = { resolved_yes: 'text-emerald-400', resolved_no: 'text-red-400', expired_mtm: 'text-amber-500', no_data: 'text-zinc-600' };
    return <span className={`font-mono text-xs ${colors[v] || 'text-zinc-500'}`}>{v || '—'}</span>;
  }},
  { key: 'closed_at', label: 'Closed', render: (v) => <span className="text-zinc-500">{formatTimestamp(v)}</span> },
];

const evalColumns = [
  { key: 'timestamp', label: 'Time', render: (v) => <span className="text-zinc-500">{formatTimestamp(v)}</span> },
  { key: 'question', label: 'Market', render: (v) => <span className="text-zinc-400 max-w-[160px] truncate block">{truncate(v, 40)}</span> },
  { key: 'asset', label: 'Asset', render: (v) => <span className="text-zinc-200 font-medium">{v}</span> },
  { key: 'live_decision', label: 'Live', render: (v) => {
    const traded = v && v.startsWith('trade');
    return <span className={traded ? 'text-emerald-400 font-medium' : 'text-zinc-600'}>{v}</span>;
  }},
  { key: 'shadow_would_trade', label: 'Shadow', render: (v) => <span className={v ? 'text-indigo-300 font-medium' : 'text-zinc-600'}>{v ? 'TRADE' : 'skip'}</span> },
  { key: 'ev_ratio', label: 'EV Gap', align: 'right', sortable: true, render: (v, row) => (
    <span className={`font-mono ${row.ev_pass ? 'text-indigo-300' : 'text-zinc-600'}`}>
      {v != null ? `${(v * 100).toFixed(1)}%` : '—'}
    </span>
  )},
  { key: 'reservation_price', label: 'Res. Price', align: 'right', render: (v) => <span className="font-mono text-zinc-400">{v != null ? formatPrice(v) : '—'}</span> },
  { key: 'stoikov_edge_bps', label: 'Stoikov', align: 'right', sortable: true, render: (v, row) => (
    <span className={`font-mono ${row.stoikov_pass ? 'text-indigo-300' : 'text-zinc-600'}`}>
      {v != null ? formatBps(v) : '—'}
    </span>
  )},
  { key: 'edge_bps', label: 'Raw Edge', align: 'right', sortable: true, render: (v) => (
    <span className={`font-mono ${v > 0 ? 'text-amber-400' : 'text-zinc-600'}`}>{formatBps(v)}</span>
  )},
];
