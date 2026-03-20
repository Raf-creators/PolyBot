import { useEffect, useMemo, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useDashboardStore } from '../state/dashboardStore';
import { useApi } from '../hooks/useApi';
import { StatCard } from '../components/StatCard';
import { SectionCard } from '../components/SectionCard';
import { DataTable } from '../components/DataTable';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { formatBps, formatPrice, formatPnl, formatNumber, formatPercent, formatTimestamp, formatTimeAgo, truncate } from '../utils/formatters';
import { FlaskConical } from 'lucide-react';
import axios from 'axios';
import { API_BASE } from '../utils/constants';

const shadowApi = axios.create({ baseURL: API_BASE });

const SIGNAL_STATUS_COLORS = {
  generated: 'text-blue-400',
  submitted: 'text-blue-400',
  filled: 'text-emerald-400',
  rejected: 'text-red-400',
  expired: 'text-zinc-500',
};

export default function Sniper() {
  const signals = useDashboardStore((s) => s.sniperSignals);
  const executions = useDashboardStore((s) => s.sniperExecutions);
  const health = useDashboardStore((s) => s.sniperHealth);
  const strategyPositions = useDashboardStore((s) => s.strategyPositions);
  const { fetchSniperSignals, fetchSniperExecutions, fetchSniperHealth, fetchStrategyPositions } = useApi();
  const [tab, setTab] = useState('positions');
  const [shadowReport, setShadowReport] = useState(null);

  useEffect(() => {
    fetchSniperSignals();
    fetchSniperExecutions();
    fetchSniperHealth();
    fetchStrategyPositions();
    const interval = setInterval(() => {
      fetchSniperSignals();
      fetchSniperExecutions();
      fetchSniperHealth();
      fetchStrategyPositions();
    }, 6000);
    return () => clearInterval(interval);
  }, [fetchSniperSignals, fetchSniperExecutions, fetchSniperHealth, fetchStrategyPositions]);

  // Shadow data fetch (separate from main polling)
  const fetchShadow = useCallback(async () => {
    try {
      const { data } = await shadowApi.get('/shadow/report');
      setShadowReport(data);
    } catch { /* silent */ }
  }, []);

  useEffect(() => {
    fetchShadow();
    const iv = setInterval(fetchShadow, 10000);
    return () => clearInterval(iv);
  }, [fetchShadow]);

  const config = health.config || {};
  const buffers = health.price_buffer_sizes || {};
  const rejReasons = health.rejection_reasons || {};
  const classFailReasons = health.classification_failure_reasons || {};

  const sniperSummary = strategyPositions?.summaries?.crypto || {};
  const sniperPositions = strategyPositions?.positions?.crypto || [];

  const allExecs = useMemo(() => [
    ...(executions.active || []),
    ...(executions.completed || []).reverse(),
  ], [executions]);

  // ---- Open Positions Columns ----
  const positionColumns = [
    { key: 'market_question', label: 'Market', render: (v) => <span className="text-zinc-200 max-w-[220px] truncate block">{truncate(v, 55)}</span> },
    { key: 'sniper_asset', label: 'Asset', render: (_, row) => {
      const s = row.sniper;
      return s ? <span className="text-zinc-200 font-medium">{s.asset}</span> : <span className="text-zinc-600">—</span>;
    }},
    { key: 'sniper_side', label: 'Side', render: (_, row) => {
      const s = row.sniper;
      return s ? <span className={s.side === 'buy_yes' ? 'text-emerald-400' : 'text-red-400'}>{s.side}</span> : <span className="text-zinc-600">—</span>;
    }},
    { key: 'avg_cost', label: 'Entry', align: 'right', render: (v) => <span className="font-mono">{formatPrice(v)}</span> },
    { key: 'current_price', label: 'Mark', align: 'right', render: (v) => <span className="font-mono text-zinc-200">{formatPrice(v)}</span> },
    { key: 'size', label: 'Size', align: 'right', render: (v) => <span className="font-mono">{formatNumber(v, 2)}</span> },
    { key: 'unrealized_pnl', label: 'Unrl P&L', align: 'right', sortable: true, render: (v) => (
      <span className={`font-mono font-medium ${v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-zinc-500'}`}>{formatPnl(v)}</span>
    )},
    { key: 'unrealized_pnl_pct', label: '%', align: 'right', render: (v) => (
      <span className={`font-mono text-xs ${v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-zinc-500'}`}>{v != null ? `${v > 0 ? '+' : ''}${v.toFixed(1)}%` : '—'}</span>
    )},
    { key: 'sniper_edge', label: 'Edge@Entry', align: 'right', render: (_, row) => {
      const e = row.sniper?.edge_at_entry;
      return e != null ? <span className="font-mono text-amber-400">{formatBps(e)}</span> : <span className="text-zinc-600">—</span>;
    }},
    { key: 'hours_to_resolution', label: 'Resolves', align: 'right', render: (v) => (
      <span className={`font-mono ${v != null && v < 1 ? 'text-amber-400' : 'text-zinc-400'}`}>{v != null ? (v < 1 ? `${Math.round(v * 60)}m` : `${v.toFixed(1)}h`) : '—'}</span>
    )},
  ];

  const signalColumns = [
    { key: 'asset', label: 'Asset', render: (v) => <span className="text-zinc-200 font-medium">{v}</span> },
    { key: 'direction', label: 'Dir', render: (v) => (
      <span className={v === 'above' ? 'text-emerald-400' : 'text-red-400'}>{v}</span>
    )},
    { key: 'strike', label: 'Strike', align: 'right', sortable: true, render: (v) => `$${formatNumber(v, 0)}` },
    { key: 'spot_price', label: 'Spot', align: 'right', render: (v) => `$${formatNumber(v, 2)}` },
    { key: 'market_price', label: 'Mkt', align: 'right', sortable: true, render: (v) => formatPrice(v) },
    { key: 'fair_price', label: 'Fair', align: 'right', sortable: true, render: (v) => v > 0 ? formatPrice(v) : '—' },
    { key: 'edge_bps', label: 'Edge', align: 'right', sortable: true, render: (v) => (
      <span className={v > 0 ? 'text-emerald-400' : 'text-zinc-500'}>{formatBps(v)}</span>
    )},
    { key: 'confidence', label: 'Conf', align: 'right', sortable: true, render: (v) => (
      <span className={v >= 0.5 ? 'text-emerald-400' : v >= 0.25 ? 'text-amber-400' : 'text-zinc-500'}>
        {v > 0 ? formatPercent(v * 100, 0) : '—'}
      </span>
    )},
    { key: 'time_to_expiry_seconds', label: 'TTE', align: 'right', sortable: true, render: (v) => v > 0 ? `${Math.round(v)}s` : '—' },
    { key: 'side', label: 'Side', render: (v) => (
      <span className={v === 'buy_yes' ? 'text-emerald-400' : v === 'buy_no' ? 'text-red-400' : 'text-zinc-600'}>{v}</span>
    )},
  ];

  const rejectedColumns = [
    ...signalColumns.slice(0, 6),
    { key: 'rejection_reason', label: 'Reason', render: (v) => <span className="text-zinc-500">{v}</span> },
    { key: 'detected_at', label: 'Detected', render: (v) => <span className="text-zinc-600">{formatTimeAgo(v)}</span> },
  ];

  const execColumns = [
    { key: 'asset', label: 'Asset', render: (v) => <span className="text-zinc-200 font-medium">{v}</span> },
    { key: 'side', label: 'Side', render: (v) => (
      <span className={v === 'buy_yes' ? 'text-emerald-400' : 'text-red-400'}>{v}</span>
    )},
    { key: 'size', label: 'Size', align: 'right', render: (v) => formatNumber(v, 2) },
    { key: 'entry_price', label: 'Fill', align: 'right', render: (v) => v != null ? formatPrice(v) : '—' },
    { key: 'target_edge_bps', label: 'Edge', align: 'right', sortable: true, render: (v) => formatBps(v) },
    { key: 'status', label: 'Status', render: (v) => (
      <span className={`font-medium ${SIGNAL_STATUS_COLORS[v] || 'text-zinc-400'}`}>{v}</span>
    )},
    { key: 'filled_at', label: 'Filled', render: (v) => v ? <span className="text-zinc-500">{formatTimestamp(v)}</span> : '—' },
  ];

  return (
    <div data-testid="sniper-page" className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-zinc-100">Crypto Sniper</h1>
        <span className="text-xs text-zinc-600 font-mono">
          {health.running ? 'SCANNING' : 'IDLE'} | Scans: {health.total_scans || 0}
        </span>
      </div>

      {/* Summary Cards - focused on live metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <StatCard testId="stat-sniper-open" label="Open Positions" value={sniperPositions.length}
          sub={sniperSummary.unrealized_pnl != null ? `${formatPnl(sniperSummary.unrealized_pnl)} unrl` : undefined} />
        <StatCard testId="stat-sniper-tradable" label="Tradable Signals" value={signals.total_tradable} />
        <StatCard testId="stat-sniper-executed" label="Executed" value={health.signals_executed || 0} />
        <StatCard testId="stat-sniper-filled" label="Filled" value={health.signals_filled || 0} />
        <StatCard testId="stat-sniper-classified" label="Markets Classified" value={health.markets_classified || 0} />
        <StatCard testId="stat-sniper-scan-ms" label="Scan Latency" value={`${health.last_scan_duration_ms || 0}ms`} />
      </div>

      {/* PnL Summary Bar */}
      <div data-testid="sniper-pnl-bar" className="flex items-center gap-6 px-4 py-2.5 bg-zinc-900/60 border border-zinc-800 rounded-lg text-xs">
        <div className="flex items-center gap-2">
          <span className="text-zinc-500">Realized</span>
          <span className={`font-mono font-medium ${(sniperSummary.realized_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {formatPnl(sniperSummary.realized_pnl || 0)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-zinc-500">Unrealized</span>
          <span className={`font-mono font-medium ${(sniperSummary.unrealized_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {formatPnl(sniperSummary.unrealized_pnl || 0)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-zinc-500">Total</span>
          <span className={`font-mono font-semibold ${(sniperSummary.total_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {formatPnl(sniperSummary.total_pnl || 0)}
          </span>
        </div>
        <div className="ml-auto flex items-center gap-4 text-zinc-500">
          <span>Trades: <span className="text-zinc-300 font-mono">{sniperSummary.trade_count || 0}</span></span>
          <span>W/L: <span className="text-zinc-300 font-mono">{sniperSummary.wins || 0}/{sniperSummary.losses || 0}</span></span>
          {sniperSummary.win_rate > 0 && <span>WR: <span className="text-zinc-300 font-mono">{sniperSummary.win_rate}%</span></span>}
        </div>
      </div>

      {/* Shadow Experiment Summary */}
      {shadowReport?.status === 'active' && (() => {
        const unit = shadowReport.unit_size || {};
        const le = shadowReport.live_equivalent || {};
        const comp = shadowReport.comparison || {};
        return (
          <div data-testid="shadow-summary-card" className="border border-dashed border-indigo-500/30 bg-indigo-950/10 rounded-lg px-4 py-3">
            <div className="flex items-center gap-5 text-xs flex-wrap">
              <div className="flex items-center gap-2">
                <div className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
                <span className="text-indigo-300 font-semibold tracking-wide uppercase text-[10px]">Shadow</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-zinc-500">Agreement</span>
                <span className="font-mono text-indigo-300">
                  {comp.meaningful_agreement_rate != null ? formatPercent(comp.meaningful_agreement_rate * 100, 1) : '—'}
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-amber-400/70 text-[10px]">Unit</span>
                <span className={`font-mono font-medium ${(unit.pnl_total || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {formatPnl(unit.pnl_total || 0)}
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-cyan-400/70 text-[10px]">LE</span>
                <span className={`font-mono font-medium ${(le.pnl_total || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {formatPnl(le.pnl_total || 0)}
                </span>
                {le.open_positions > 0 && (
                  <span className="text-zinc-600 font-mono">({le.open_positions} open, {le.open_total_size} shares)</span>
                )}
              </div>
              <Link
                to="/quant-lab"
                data-testid="shadow-open-lab"
                className="ml-auto flex items-center gap-1.5 text-indigo-400 hover:text-indigo-300 transition-colors"
              >
                <FlaskConical size={12} />
                <span className="font-medium">Quant Lab</span>
              </Link>
            </div>
          </div>
        );
      })()}

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-zinc-900 border border-zinc-800">
          <TabsTrigger data-testid="tab-positions" value="positions" className="text-xs data-[state=active]:bg-zinc-800">
            Open Positions ({sniperPositions.length})
          </TabsTrigger>
          <TabsTrigger value="signals" className="text-xs data-[state=active]:bg-zinc-800">
            Signals ({signals.total_tradable})
          </TabsTrigger>
          <TabsTrigger value="rejected" className="text-xs data-[state=active]:bg-zinc-800">
            Rejected ({signals.total_rejected})
          </TabsTrigger>
          <TabsTrigger value="executions" className="text-xs data-[state=active]:bg-zinc-800">
            Executions ({allExecs.length})
          </TabsTrigger>
          <TabsTrigger value="health" className="text-xs data-[state=active]:bg-zinc-800">
            Health
          </TabsTrigger>
        </TabsList>

        {/* Open Positions Tab (PRIMARY) */}
        <TabsContent value="positions" className="mt-4">
          <SectionCard title="Open Sniper Positions" testId="section-sniper-positions">
            <DataTable columns={positionColumns} data={sniperPositions}
              emptyMessage="No open sniper positions — trades will appear here when the strategy executes"
              testId="sniper-positions-table" />
          </SectionCard>
        </TabsContent>

        <TabsContent value="signals" className="mt-4">
          <SectionCard testId="section-sniper-signals">
            <DataTable columns={signalColumns} data={signals.tradable || []} emptyMessage="No tradable signals — start engine & wait for crypto market data" testId="sniper-signals-table" />
          </SectionCard>
        </TabsContent>

        <TabsContent value="rejected" className="mt-4">
          <SectionCard testId="section-sniper-rejected">
            <DataTable columns={rejectedColumns} data={signals.rejected || []} emptyMessage="No rejected signals" testId="sniper-rejected-table" />
          </SectionCard>
        </TabsContent>

        <TabsContent value="executions" className="mt-4">
          <SectionCard testId="section-sniper-executions">
            <DataTable columns={execColumns} data={allExecs} emptyMessage="No sniper executions yet" testId="sniper-exec-table" />
          </SectionCard>
        </TabsContent>

        <TabsContent value="health" className="mt-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            <SectionCard title="Volatility" testId="section-sniper-vol">
              <div className="space-y-3 text-xs">
                <div className="flex justify-between">
                  <span className="text-zinc-500">BTC Realized Vol</span>
                  <span className={`font-mono ${health.btc_realized_vol ? 'text-zinc-200' : 'text-zinc-600'}`}>
                    {health.btc_realized_vol ? formatPercent(health.btc_realized_vol * 100, 1) : 'Warming up...'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">ETH Realized Vol</span>
                  <span className={`font-mono ${health.eth_realized_vol ? 'text-zinc-200' : 'text-zinc-600'}`}>
                    {health.eth_realized_vol ? formatPercent(health.eth_realized_vol * 100, 1) : 'Warming up...'}
                  </span>
                </div>
                <div className="pt-2 border-t border-zinc-800 space-y-2">
                  {['BTC', 'ETH'].map(a => (
                    <div key={a} className="flex justify-between">
                      <span className="text-zinc-500">{a} Samples</span>
                      <span className="font-mono text-zinc-400">
                        {buffers[a] || 0} / {config.vol_min_samples || 30}
                        {(buffers[a] || 0) >= (config.vol_min_samples || 30) ? <span className="ml-2 text-emerald-400">Ready</span> : <span className="ml-2 text-amber-400">Filling</span>}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </SectionCard>

            <SectionCard title="Scanner Metrics" testId="section-sniper-metrics">
              <div className="space-y-2 text-xs">
                {[
                  ['Total Scans', health.total_scans], ['Scan Duration', `${health.last_scan_duration_ms || 0}ms`],
                  ['Markets Classified', health.markets_classified], ['Markets Evaluated', health.markets_evaluated],
                  ['Signals Generated', health.signals_generated], ['Signals Executed', health.signals_executed],
                  ['Signals Filled', health.signals_filled], ['Active Executions', health.active_executions],
                ].map(([label, val]) => (
                  <div key={label} className="flex justify-between">
                    <span className="text-zinc-500">{label}</span>
                    <span className="text-zinc-300 font-mono">{val ?? '—'}</span>
                  </div>
                ))}
              </div>
            </SectionCard>

            <SectionCard title="Rejection Reasons" testId="section-sniper-rejections">
              <div className="space-y-2 text-xs">
                {Object.keys(rejReasons).length === 0 ? (
                  <p className="text-zinc-600">No rejections yet</p>
                ) : (
                  Object.entries(rejReasons).sort(([,a],[,b]) => b - a).map(([reason, count]) => (
                    <div key={reason} className="flex justify-between">
                      <span className="text-zinc-500">{reason}</span>
                      <span className="text-zinc-300 font-mono">{count}</span>
                    </div>
                  ))
                )}
                {Object.keys(classFailReasons).length > 0 && (
                  <div className="pt-2 border-t border-zinc-800">
                    <p className="text-zinc-600 mb-2">Classification failures:</p>
                    {Object.entries(classFailReasons).sort(([,a],[,b]) => b - a).map(([reason, count]) => (
                      <div key={reason} className="flex justify-between">
                        <span className="text-zinc-500">{reason}</span>
                        <span className="text-zinc-300 font-mono">{count}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </SectionCard>

            <SectionCard title="Scanner Config" testId="section-sniper-config">
              <div className="space-y-2 text-xs">
                {[
                  ['Scan Interval', `${config.scan_interval}s`], ['Min Edge', `${config.min_edge_bps} bps`],
                  ['Min Liquidity', `$${config.min_liquidity}`], ['Min Confidence', config.min_confidence],
                  ['Default Size', config.default_size], ['Max Concurrent', config.max_concurrent_signals],
                  ['Cooldown', `${config.cooldown_seconds}s`],
                ].map(([label, val]) => (
                  <div key={label} className="flex justify-between">
                    <span className="text-zinc-500">{label}</span>
                    <span className="text-zinc-300 font-mono">{val ?? '—'}</span>
                  </div>
                ))}
              </div>
            </SectionCard>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
