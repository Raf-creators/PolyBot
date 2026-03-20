import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import { API_BASE } from '../utils/constants';
import { SectionCard } from '../components/SectionCard';
import { DataTable } from '../components/DataTable';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { formatPnl, formatPrice, formatBps, formatTimestamp, formatTimeAgo, pnlColor, truncate, formatPercent } from '../utils/formatters';
import { FlaskConical } from 'lucide-react';

const api = axios.create({ baseURL: API_BASE });

export default function QuantLab() {
  const [report, setReport] = useState(null);
  const [evaluations, setEvaluations] = useState([]);
  const [unitPositions, setUnitPositions] = useState([]);
  const [lePositions, setLePositions] = useState([]);
  const [unitClosed, setUnitClosed] = useState([]);
  const [leClosed, setLeClosed] = useState([]);

  const refresh = useCallback(async () => {
    try {
      const [rpt, evals, uPos, lPos, uCls, lCls] = await Promise.all([
        api.get('/shadow/report'),
        api.get('/shadow/evaluations?limit=100'),
        api.get('/shadow/positions?mode=unit'),
        api.get('/shadow/positions?mode=le'),
        api.get('/shadow/closed?limit=50&mode=unit'),
        api.get('/shadow/closed?limit=50&mode=le'),
      ]);
      setReport(rpt.data);
      setEvaluations(evals.data);
      setUnitPositions(uPos.data);
      setLePositions(lPos.data);
      setUnitClosed(uCls.data);
      setLeClosed(lCls.data);
    } catch { /* silent */ }
  }, []);

  useEffect(() => {
    refresh();
    const iv = setInterval(refresh, 8000);
    return () => clearInterval(iv);
  }, [refresh]);

  const comp = report?.comparison || {};
  const live = comp.live || {};
  const signals = comp.shadow_signals || {};
  const unit = report?.unit_size || {};
  const le = report?.live_equivalent || {};
  const sizing = report?.sizing || {};
  const cfg = report?.config || {};
  const totalEvals = report?.total_evaluations || 0;
  const meaningfulEvals = report?.meaningful_evaluations || 0;

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

      {/* Banner */}
      <div data-testid="shadow-banner" className="flex items-center gap-3 px-4 py-2.5 border border-dashed border-indigo-500/40 bg-indigo-950/20 rounded-lg flex-wrap">
        <div className="w-2 h-2 rounded-full bg-indigo-400 animate-pulse shrink-0" />
        <span className="text-xs font-semibold text-indigo-300 tracking-wide uppercase">Shadow Only — No Live Execution</span>
        <span className="text-xs text-zinc-500">Both modes are hypothetical research. Neither places live orders.</span>
        <div className="ml-auto text-xs text-zinc-600 font-mono">{report?.status === 'active' ? 'ACTIVE' : '—'}</div>
      </div>

      {/* Signal quality + agreement (shared across modes) */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <MC t="metric-live-signals" l="Live Signals" v={live.trade_count ?? 0} s="actual fills" />
        <MC t="metric-shadow-signals" l="Shadow Signals" v={signals.trade_count ?? 0} s="would-trade" a />
        <MC t="metric-agreement" l="Agreement Rate"
          v={comp.meaningful_agreement_rate != null ? formatPercent(comp.meaningful_agreement_rate * 100, 1) : '—'}
          s={`${meaningfulEvals} meaningful`} />
        <MC t="metric-fp" l="False Positives" v={comp.false_positives ?? 0} s="shadow traded, loss" />
        <MC t="metric-fn" l="False Negatives" v={comp.false_negatives ?? 0} s="shadow skip, live won" />
      </div>

      {/* Dual-mode PnL comparison */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Unit-Size column */}
        <ModeCard
          testId="mode-unit"
          title="Unit-Size"
          badge="Research Normalization"
          badgeColor="amber"
          description={sizing.unit?.note || `$${sizing.unit?.per_signal || '?'}/signal, no accumulation`}
          stats={unit}
        />
        {/* Live-Equivalent column */}
        <ModeCard
          testId="mode-le"
          title="Live-Equivalent"
          badge="Hypothetical Real-World Replay"
          badgeColor="cyan"
          description={sizing.live_equivalent?.note || 'Same sizing/accumulation path as live'}
          stats={le}
        />
      </div>

      {/* Shadow Config */}
      <SectionCard title="Shadow Config" testId="section-shadow-config"
        action={<span className="text-[10px] text-indigo-400/60 font-mono uppercase tracking-wider">Experiment Parameters</span>}>
        <div className="grid grid-cols-2 md:grid-cols-6 gap-x-6 gap-y-2 text-xs">
          <CR l="EV-Gap Threshold" v={cfg.min_ev_ratio != null ? `${(cfg.min_ev_ratio * 100).toFixed(1)}%` : '—'} />
          <CR l="Pseudo-Stoikov" v="Enabled" active />
          <CR l="Gamma" v={cfg.gamma ?? '—'} />
          <CR l="Inventory Decay" v={cfg.inventory_decay ?? '—'} />
          <CR l="Unit Size" v={`$${sizing.unit?.per_signal || '?'}/sig`} />
          <CR l="LE Max Size" v={sizing.live_equivalent?.max_size ?? '—'} />
        </div>
      </SectionCard>

      {/* Positions / Closed / Evaluations — tabbed for each mode */}
      <Tabs defaultValue="le-open">
        <TabsList className="bg-zinc-900 border border-zinc-800 mb-3">
          <TabsTrigger value="le-open" data-testid="tab-le-open">LE Open ({lePositions.length})</TabsTrigger>
          <TabsTrigger value="le-closed" data-testid="tab-le-closed">LE Closed ({leClosed.length})</TabsTrigger>
          <TabsTrigger value="unit-open" data-testid="tab-unit-open">Unit Open ({unitPositions.length})</TabsTrigger>
          <TabsTrigger value="unit-closed" data-testid="tab-unit-closed">Unit Closed ({unitClosed.length})</TabsTrigger>
          <TabsTrigger value="evals" data-testid="tab-evals">Evaluations ({evaluations.length})</TabsTrigger>
        </TabsList>

        <TabsContent value="le-open">
          <SectionCard title="Live-Equivalent Open Positions" testId="section-le-open"
            action={<Badge color="cyan" text="Accumulating · Hypothetical" />}>
            <DataTable columns={leOpenCols} data={lePositions}
              emptyMessage="No LE hypothetical positions" testId="le-open-table" />
          </SectionCard>
        </TabsContent>

        <TabsContent value="le-closed">
          <SectionCard title="Live-Equivalent Closed Trades" testId="section-le-closed"
            action={<Badge color="cyan" text="Hypothetical Real-World PnL" />}>
            <DataTable columns={closedCols} data={leClosed}
              emptyMessage="No LE resolved trades yet" testId="le-closed-table" />
          </SectionCard>
        </TabsContent>

        <TabsContent value="unit-open">
          <SectionCard title="Unit-Size Open Positions" testId="section-unit-open"
            action={<Badge color="amber" text="$3/signal · No Accumulation" />}>
            <DataTable columns={unitOpenCols} data={unitPositions}
              emptyMessage="No unit hypothetical positions" testId="unit-open-table" />
          </SectionCard>
        </TabsContent>

        <TabsContent value="unit-closed">
          <SectionCard title="Unit-Size Closed Trades" testId="section-unit-closed"
            action={<Badge color="amber" text="Research Normalization" />}>
            <DataTable columns={closedCols} data={unitClosed}
              emptyMessage="No unit resolved trades yet" testId="unit-closed-table" />
          </SectionCard>
        </TabsContent>

        <TabsContent value="evals">
          <SectionCard title="Recent Evaluations" testId="section-evals"
            action={<span className="text-[10px] text-indigo-400/60 font-mono uppercase tracking-wider">Live vs Shadow</span>}>
            <DataTable columns={evalCols} data={evaluations}
              emptyMessage="Waiting for scan cycle" testId="evals-table" />
          </SectionCard>
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ---- Mode comparison card ----

function ModeCard({ testId, title, badge, badgeColor, description, stats }) {
  const bc = badgeColor === 'cyan' ? 'border-cyan-500/30 bg-cyan-950/15' : 'border-amber-500/30 bg-amber-950/15';
  const tc = badgeColor === 'cyan' ? 'text-cyan-300' : 'text-amber-300';
  const bc2 = badgeColor === 'cyan' ? 'border-cyan-500/20 text-cyan-400' : 'border-amber-500/20 text-amber-400';
  return (
    <div data-testid={testId} className={`border rounded-lg p-4 space-y-3 ${bc}`}>
      <div className="flex items-center justify-between">
        <span className={`text-sm font-semibold ${tc}`}>{title}</span>
        <span className={`text-[10px] font-mono border rounded px-1.5 py-0.5 ${bc2}`}>{badge}</span>
      </div>
      <div className="text-[11px] text-zinc-500">{description}</div>
      <div className="grid grid-cols-3 gap-2 text-xs">
        <MiniStat label="PnL" value={formatPnl(stats.pnl_total || 0)} pnl />
        <MiniStat label="PnL/Trade" value={stats.pnl_per_trade != null ? formatPnl(stats.pnl_per_trade) : '—'} pnl />
        <MiniStat label="Win Rate (Binary)" value={stats.binary_win_rate != null ? formatPercent(stats.binary_win_rate * 100, 1) : '—'} />
        <MiniStat label="Open" value={stats.open_positions ?? 0} />
        <MiniStat label="Closed" value={stats.closed_trades ?? 0} />
        <MiniStat label="Exposure" value={stats.open_exposure != null ? `$${stats.open_exposure.toFixed(2)}` : '—'} />
        <MiniStat label="Total Size" value={stats.open_total_size != null ? `${stats.open_total_size}` : '—'} />
        <MiniStat label="Rolling 1h" value={formatPnl(stats.rolling_pnl?.['1h'] || 0)} pnl />
        <MiniStat label="Rolling 6h" value={formatPnl(stats.rolling_pnl?.['6h'] || 0)} pnl />
      </div>
    </div>
  );
}

function MiniStat({ label, value, pnl }) {
  let c = 'text-zinc-200';
  if (pnl && typeof value === 'string') {
    if (value.startsWith('+') && value !== '+$0.00') c = 'text-emerald-400';
    else if (value.startsWith('-')) c = 'text-red-400';
    else c = 'text-zinc-400';
  }
  return (
    <div>
      <div className="text-[10px] text-zinc-500">{label}</div>
      <div className={`font-mono text-sm font-medium ${c}`}>{value ?? '—'}</div>
    </div>
  );
}

function MC({ t, l, v, s, a }) {
  return (
    <div data-testid={t} className={`border rounded-lg px-4 py-3 ${a ? 'bg-indigo-950/20 border-indigo-500/20' : 'bg-zinc-900/60 border-zinc-800'}`}>
      <div className="text-[11px] text-zinc-500 mb-1">{l}</div>
      <div className={`text-base font-semibold font-mono ${a ? 'text-indigo-300' : 'text-zinc-100'}`}>{v ?? '—'}</div>
      {s && <div className="text-[10px] text-zinc-600 mt-0.5">{s}</div>}
    </div>
  );
}

function CR({ l, v, active }) {
  return (
    <div className="flex justify-between py-1 text-xs">
      <span className="text-zinc-500">{l}</span>
      <span className={`font-mono ${active ? 'text-indigo-300' : 'text-zinc-300'}`}>{v}</span>
    </div>
  );
}

function Badge({ color, text }) {
  const c = color === 'cyan' ? 'text-cyan-400/70 border-cyan-500/20' : 'text-amber-500/70 border-amber-500/20';
  return <span className={`text-[10px] font-mono border rounded px-1.5 py-0.5 ${c}`}>{text}</span>;
}

// ---- Table columns ----

const leOpenCols = [
  { key: 'question', label: 'Market', render: v => <span className="text-zinc-300 max-w-[160px] truncate block">{truncate(v, 40)}</span> },
  { key: 'asset', label: 'Asset', render: v => <span className="text-zinc-200 font-medium">{v}</span> },
  { key: 'side', label: 'Side', render: v => <span className={v === 'buy_yes' ? 'text-emerald-400' : v === 'buy_no' ? 'text-red-400' : 'text-zinc-500'}>{v}</span> },
  { key: 'size', label: 'Size', align: 'right', sortable: true, render: v => <span className="font-mono text-cyan-300 font-medium">{v}</span> },
  { key: 'fills', label: 'Fills', align: 'right', render: v => <span className="font-mono text-zinc-400">{v}</span> },
  { key: 'notional', label: 'Notional', align: 'right', render: v => <span className="font-mono text-zinc-300">${typeof v === 'number' ? v.toFixed(2) : '—'}</span> },
  { key: 'avg_entry', label: 'Avg Entry', align: 'right', render: v => <span className="font-mono">{formatPrice(v)}</span> },
  { key: 'current_price', label: 'Mark', align: 'right', render: v => <span className="font-mono text-zinc-200">{v != null ? formatPrice(v) : '—'}</span> },
  { key: 'unrealized_pnl', label: 'Unrl PnL', align: 'right', sortable: true, render: v => <span className={`font-mono font-medium ${pnlColor(v)}`}>{formatPnl(v)}</span> },
  { key: 'ev_ratio', label: 'EV Ratio', align: 'right', render: v => <span className="font-mono text-indigo-300">{v != null ? `${(v * 100).toFixed(1)}%` : '—'}</span> },
  { key: 'opened_at', label: 'Opened', render: v => <span className="text-zinc-500">{formatTimeAgo(v)}</span> },
];

const unitOpenCols = [
  { key: 'question', label: 'Market', render: v => <span className="text-zinc-300 max-w-[160px] truncate block">{truncate(v, 40)}</span> },
  { key: 'asset', label: 'Asset', render: v => <span className="text-zinc-200 font-medium">{v}</span> },
  { key: 'side', label: 'Side', render: v => <span className={v === 'buy_yes' ? 'text-emerald-400' : v === 'buy_no' ? 'text-red-400' : 'text-zinc-500'}>{v}</span> },
  { key: 'size', label: 'Size', align: 'right', render: v => <span className="font-mono text-amber-300">{v}</span> },
  { key: 'notional', label: 'Notional', align: 'right', render: v => <span className="font-mono text-zinc-300">${typeof v === 'number' ? v.toFixed(2) : '—'}</span> },
  { key: 'entry_price', label: 'Entry', align: 'right', render: v => <span className="font-mono">{formatPrice(v)}</span> },
  { key: 'current_price', label: 'Mark', align: 'right', render: v => <span className="font-mono text-zinc-200">{v != null ? formatPrice(v) : '—'}</span> },
  { key: 'unrealized_pnl', label: 'Unrl PnL', align: 'right', sortable: true, render: v => <span className={`font-mono font-medium ${pnlColor(v)}`}>{formatPnl(v)}</span> },
  { key: 'ev_ratio', label: 'EV Ratio', align: 'right', render: v => <span className="font-mono text-indigo-300">{v != null ? `${(v * 100).toFixed(1)}%` : '—'}</span> },
  { key: 'stoikov_edge_bps', label: 'Stoikov', align: 'right', render: v => <span className="font-mono text-indigo-300">{v != null ? formatBps(v) : '—'}</span> },
  { key: 'opened_at', label: 'Opened', render: v => <span className="text-zinc-500">{formatTimeAgo(v)}</span> },
];

const closedCols = [
  { key: 'question', label: 'Market', render: v => <span className="text-zinc-300 max-w-[160px] truncate block">{truncate(v, 40)}</span> },
  { key: 'asset', label: 'Asset', render: v => <span className="text-zinc-200 font-medium">{v}</span> },
  { key: 'side', label: 'Side', render: v => <span className={v === 'buy_yes' ? 'text-emerald-400' : v === 'buy_no' ? 'text-red-400' : 'text-zinc-500'}>{v}</span> },
  { key: 'size', label: 'Size', align: 'right', render: v => <span className="font-mono font-medium">{v}</span> },
  { key: 'fills', label: 'Fills', align: 'right', render: v => <span className="font-mono text-zinc-400">{v ?? 1}</span> },
  { key: 'avg_entry', label: 'Avg Entry', align: 'right', render: v => <span className="font-mono">{formatPrice(v)}</span> },
  { key: 'exit_price', label: 'Exit', align: 'right', render: v => <span className="font-mono">{formatPrice(v)}</span> },
  { key: 'pnl', label: 'PnL', align: 'right', sortable: true, render: v => <span className={`font-mono font-semibold ${pnlColor(v)}`}>{formatPnl(v)}</span> },
  { key: 'won', label: 'Result', render: v => <span className={v ? 'text-emerald-400' : 'text-red-400'}>{v ? 'WIN' : 'LOSS'}</span> },
  { key: 'resolution_type', label: 'Resolution', render: v => {
    const c = { resolved_yes: 'text-emerald-400', resolved_no: 'text-red-400', expired_mtm: 'text-amber-500', no_data: 'text-zinc-600' };
    return <span className={`font-mono text-xs ${c[v] || 'text-zinc-500'}`}>{v || '—'}</span>;
  }},
  { key: 'closed_at', label: 'Closed', render: v => <span className="text-zinc-500">{formatTimestamp(v)}</span> },
];

const evalCols = [
  { key: 'timestamp', label: 'Time', render: v => <span className="text-zinc-500">{formatTimestamp(v)}</span> },
  { key: 'question', label: 'Market', render: v => <span className="text-zinc-400 max-w-[140px] truncate block">{truncate(v, 35)}</span> },
  { key: 'asset', label: 'Asset', render: v => <span className="text-zinc-200 font-medium">{v}</span> },
  { key: 'live_decision', label: 'Live', render: v => {
    const t = v && v.startsWith('trade');
    return <span className={t ? 'text-emerald-400 font-medium' : 'text-zinc-600'}>{v}</span>;
  }},
  { key: 'shadow_would_trade', label: 'Shadow', render: v => <span className={v ? 'text-indigo-300 font-medium' : 'text-zinc-600'}>{v ? 'TRADE' : 'skip'}</span> },
  { key: 'le_action', label: 'LE Action', render: v => v ? <span className="font-mono text-xs text-cyan-400">{v}</span> : <span className="text-zinc-700">—</span> },
  { key: 'ev_ratio', label: 'EV Gap', align: 'right', sortable: true, render: (v, r) => (
    <span className={`font-mono ${r.ev_pass ? 'text-indigo-300' : 'text-zinc-600'}`}>{v != null ? `${(v * 100).toFixed(1)}%` : '—'}</span>
  )},
  { key: 'stoikov_edge_bps', label: 'Stoikov', align: 'right', sortable: true, render: (v, r) => (
    <span className={`font-mono ${r.stoikov_pass ? 'text-indigo-300' : 'text-zinc-600'}`}>{v != null ? formatBps(v) : '—'}</span>
  )},
  { key: 'edge_bps', label: 'Raw Edge', align: 'right', render: v => (
    <span className={`font-mono ${v > 0 ? 'text-amber-400' : 'text-zinc-600'}`}>{formatBps(v)}</span>
  )},
];
