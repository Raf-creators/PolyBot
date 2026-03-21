import { useEffect, useMemo, useState } from 'react';
import { useDashboardStore } from '../state/dashboardStore';
import { useApi } from '../hooks/useApi';
import { StatCard } from '../components/StatCard';
import { SectionCard } from '../components/SectionCard';
import { DataTable } from '../components/DataTable';
import { formatBps, formatPrice, formatPnl, formatNumber, formatTimestamp, formatTimeAgo, truncate } from '../utils/formatters';
import { ARB_STATUS_COLORS } from '../utils/constants';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';

export default function Arbitrage() {
  const arbOpps = useDashboardStore((s) => s.arbOpportunities);
  const arbExecs = useDashboardStore((s) => s.arbExecutions);
  const arbHealth = useDashboardStore((s) => s.arbHealth);
  const arbDiag = useDashboardStore((s) => s.arbDiagnostics);
  const strategyPositions = useDashboardStore((s) => s.strategyPositions);
  const { fetchArbOpportunities, fetchArbExecutions, fetchArbHealth, fetchArbDiagnostics, fetchStrategyPositions } = useApi();
  const [tab, setTab] = useState('gabagool');
  const [gabaReport, setGabaReport] = useState({});
  const [gabaOpen, setGabaOpen] = useState([]);
  const [gabaClosed, setGabaClosed] = useState([]);

  const API = process.env.REACT_APP_BACKEND_URL;

  useEffect(() => {
    const fetchGaba = async () => {
      try {
        const [r, o, c] = await Promise.all([
          fetch(`${API}/api/gabagool/report`).then(r => r.json()),
          fetch(`${API}/api/gabagool/positions`).then(r => r.json()),
          fetch(`${API}/api/gabagool/closed`).then(r => r.json()),
        ]);
        setGabaReport(r);
        setGabaOpen(o);
        setGabaClosed(c);
      } catch {}
    };
    fetchArbOpportunities();
    fetchArbExecutions();
    fetchArbHealth();
    fetchArbDiagnostics();
    fetchStrategyPositions();
    fetchGaba();
    const interval = setInterval(() => {
      fetchArbOpportunities();
      fetchArbExecutions();
      fetchArbHealth();
      fetchArbDiagnostics();
      fetchStrategyPositions();
      fetchGaba();
    }, 8000);
    return () => clearInterval(interval);
  }, [fetchArbOpportunities, fetchArbExecutions, fetchArbHealth, fetchArbDiagnostics, fetchStrategyPositions, API]);

  const arbSummary = strategyPositions?.summaries?.arb || {};

  const oppColumns = [
    { key: 'question', label: 'Market', render: (v) => <span className="text-zinc-300">{truncate(v, 40)}</span> },
    { key: 'yes_price', label: 'Yes', align: 'right', sortable: true, render: (v) => <span className="text-emerald-400">{formatPrice(v)}</span> },
    { key: 'no_price', label: 'No', align: 'right', sortable: true, render: (v) => <span className="text-red-400">{formatPrice(v)}</span> },
    { key: 'gross_edge_bps', label: 'Gross', align: 'right', sortable: true, render: (v) => formatBps(v) },
    { key: 'net_edge_bps', label: 'Net Edge', align: 'right', sortable: true, render: (v) => (
      <span className={v > 0 ? 'text-emerald-400' : 'text-red-400'}>{formatBps(v)}</span>
    )},
    { key: 'confidence_score', label: 'Conf', align: 'right', sortable: true, render: (v) => (
      <span className={v >= 0.5 ? 'text-emerald-400' : v >= 0.25 ? 'text-amber-400' : 'text-red-400'}>
        {(v * 100).toFixed(0)}%
      </span>
    )},
    { key: 'liquidity_estimate', label: 'Liquidity', align: 'right', sortable: true, render: (v) => `$${formatNumber(v, 0)}` },
    { key: 'detected_at', label: 'Detected', render: (v) => <span className="text-zinc-500">{formatTimeAgo(v)}</span> },
  ];

  const rejectedColumns = [
    ...oppColumns.slice(0, 5),
    { key: 'rejection_reason', label: 'Reason', render: (v) => <span className="text-zinc-500 text-xs">{v}</span> },
    { key: 'detected_at', label: 'Detected', render: (v) => <span className="text-zinc-500">{formatTimeAgo(v)}</span> },
  ];

  const execColumns = [
    { key: 'question', label: 'Market', render: (v) => <span className="text-zinc-300">{truncate(v, 35)}</span> },
    { key: 'status', label: 'Status', render: (v) => (
      <span className={`font-medium ${ARB_STATUS_COLORS[v] || 'text-zinc-400'}`}>{v}</span>
    )},
    { key: 'target_edge_bps', label: 'Target', align: 'right', sortable: true, render: (v) => formatBps(v) },
    { key: 'realized_edge_bps', label: 'Realized', align: 'right', sortable: true, render: (v) => (
      v != null ? <span className={v > 0 ? 'text-emerald-400' : 'text-red-400'}>{formatBps(v)}</span> : '—'
    )},
    { key: 'yes_fill_price', label: 'Yes Fill', align: 'right', render: (v) => v != null ? formatPrice(v) : '—' },
    { key: 'no_fill_price', label: 'No Fill', align: 'right', render: (v) => v != null ? formatPrice(v) : '—' },
    { key: 'size', label: 'Size', align: 'right', render: (v) => formatNumber(v, 2) },
    { key: 'submitted_at', label: 'Time', render: (v) => <span className="text-zinc-500">{formatTimestamp(v)}</span> },
  ];

  const allExecs = useMemo(() => [
    ...(arbExecs.active || []),
    ...(arbExecs.completed || []).reverse(),
  ], [arbExecs]);

  const config = arbHealth.config || {};
  const rejReasons = arbHealth.rejection_reasons || {};
  const diag = arbDiag || {};
  const diagMetrics = diag.metrics || {};
  const gabaPerf = gabaReport.performance || {};
  const gabaMetrics = gabaReport.metrics || {};
  const gabaConfig = gabaReport.config || {};

  const gabaOpenCols = [
    { key: 'question', label: 'Market', render: v => <span className="text-zinc-300 max-w-[180px] truncate block">{truncate(v, 50)}</span> },
    { key: 'yes_entry', label: 'YES', align: 'right', render: v => <span className="font-mono text-emerald-400">{formatPrice(v)}</span> },
    { key: 'no_entry', label: 'NO', align: 'right', render: v => <span className="font-mono text-red-400">{formatPrice(v)}</span> },
    { key: 'pair_cost', label: 'Pair $', align: 'right', render: v => <span className={`font-mono ${v < 0.96 ? 'text-cyan-300 font-semibold' : 'text-zinc-400'}`}>{v?.toFixed(4)}</span> },
    { key: 'guaranteed_edge_pct', label: 'Edge', align: 'right', sortable: true, render: v => <span className="font-mono text-cyan-300">{v}%</span> },
    { key: 'guaranteed_profit', label: 'Guar PnL', align: 'right', render: v => <span className="font-mono text-emerald-400">${v?.toFixed(4)}</span> },
    { key: 'size', label: 'Size/Side', align: 'right', render: v => <span className="font-mono text-cyan-300">${v}</span> },
    { key: 'opened_at', label: 'Opened', render: v => <span className="text-zinc-500">{formatTimeAgo(v)}</span> },
  ];

  const gabaClosedCols = [
    { key: 'question', label: 'Market', render: v => <span className="text-zinc-300 max-w-[180px] truncate block">{truncate(v, 50)}</span> },
    { key: 'pair_cost', label: 'Pair $', align: 'right', render: v => <span className="font-mono text-cyan-300">{v?.toFixed(4)}</span> },
    { key: 'guaranteed_edge_pct', label: 'Edge', align: 'right', render: v => <span className="font-mono text-cyan-300">{v}%</span> },
    { key: 'pnl', label: 'PnL', align: 'right', sortable: true, render: v => <span className={`font-mono font-semibold ${v >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{formatPnl(v)}</span> },
    { key: 'won', label: 'Result', render: v => <span className={v ? 'text-emerald-400 font-semibold' : 'text-red-400'}>{v ? 'WIN' : 'LOSS'}</span> },
    { key: 'size', label: 'Size', align: 'right', render: v => <span className="font-mono">${v}</span> },
    { key: 'closed_at', label: 'Closed', render: v => <span className="text-zinc-500">{formatTimestamp(v)}</span> },
  ];

  return (
    <div data-testid="arbitrage-page" className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-zinc-100">Arbitrage & Gabagool</h1>
        <span className="text-xs text-zinc-600 font-mono">
          {arbHealth.running ? 'SCANNING' : 'IDLE'} | Scans: {diagMetrics.total_scans || arbHealth.total_scans || 0}
        </span>
      </div>

      {/* Gabagool Live Arb Banner */}
      <div data-testid="gabagool-live-section" className="border border-cyan-900/50 bg-gradient-to-r from-cyan-950/20 to-zinc-900/40 rounded-lg p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-cyan-300">GABAGOOL</span>
            <span className="text-[10px] px-1.5 py-0.5 bg-cyan-900/40 border border-cyan-800/40 rounded text-cyan-400 font-mono">LIVE ARB</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded font-mono ${gabaReport.status === 'active' ? 'bg-emerald-900/40 text-emerald-400' : 'bg-zinc-800 text-zinc-500'}`}>
              {gabaReport.status === 'active' ? 'ACTIVE' : 'OFFLINE'}
            </span>
          </div>
          <span className="text-[10px] text-zinc-600 font-mono">threshold &lt; ${gabaConfig.threshold || 0.96} | ${gabaConfig.size_per_side || 10}/side</span>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <StatCard testId="gaba-pnl" label="Gabagool PnL" value={formatPnl(gabaPerf.pnl_total || 0)} color={(gabaPerf.pnl_total || 0) >= 0 ? 'emerald' : 'red'} />
          <StatCard testId="gaba-wr" label="Win Rate" value={`${gabaPerf.win_rate || 0}%`} color={gabaPerf.win_rate >= 80 ? 'emerald' : 'amber'} />
          <StatCard testId="gaba-open" label="Open Pairs" value={gabaPerf.open_pairs || 0} />
          <StatCard testId="gaba-closed" label="Closed Pairs" value={gabaPerf.closed_pairs || 0} />
          <StatCard testId="gaba-found" label="Pairs Found" value={gabaMetrics.pairs_found || 0} />
        </div>
      </div>

      {/* PnL Summary Bar — matches Sniper and Weather pages */}
      <div data-testid="arb-pnl-bar" className="flex items-center gap-6 px-4 py-2.5 bg-zinc-900/60 border border-zinc-800 rounded-lg text-xs">
        <div className="flex items-center gap-2">
          <span className="text-zinc-500">Realized</span>
          <span className={`font-mono font-medium ${(arbSummary.realized_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {formatPnl(arbSummary.realized_pnl || 0)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-zinc-500">Unrealized</span>
          <span className={`font-mono font-medium ${(arbSummary.unrealized_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {formatPnl(arbSummary.unrealized_pnl || 0)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-zinc-500">Total</span>
          <span className={`font-mono font-semibold ${(arbSummary.total_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {formatPnl(arbSummary.total_pnl || 0)}
          </span>
        </div>
        <div className="ml-auto flex items-center gap-4 text-zinc-500">
          <span>Trades: <span className="text-zinc-300 font-mono">{arbSummary.trade_count || 0}</span></span>
          <span>W/L: <span className="text-zinc-300 font-mono">{arbSummary.wins || 0}/{arbSummary.losses || 0}</span></span>
          {arbSummary.win_rate > 0 && <span>WR: <span className="text-zinc-300 font-mono">{arbSummary.win_rate}%</span></span>}
          <span>Capital: <span className="text-zinc-300 font-mono">${formatNumber(arbSummary.capital_allocated || 0, 2)}</span></span>
        </div>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        <StatCard testId="stat-markets" label="Markets Scanned" value={diag.markets_scanned || 0} />
        <StatCard testId="stat-binary" label="Binary Pairs" value={diag.binary_pairs_found || 0} />
        <StatCard testId="stat-multi" label="Multi-Outcome" value={diag.multi_outcome_groups_found || 0} />
        <StatCard testId="stat-raw-edges" label="Raw Edges" value={diagMetrics.raw_edges_found || 0} />
        <StatCard testId="stat-eligible" label="Eligible" value={diagMetrics.eligible_count || 0} />
        <StatCard testId="stat-executed" label="Executed" value={diagMetrics.executed_count || 0} />
        <StatCard testId="stat-last-scan" label="Last Scan" value={formatTimeAgo(diagMetrics.last_scan_time || arbHealth.last_scan_time)} />
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-zinc-900 border border-zinc-800">
          <TabsTrigger value="gabagool" className="text-xs data-[state=active]:bg-cyan-900/40 data-[state=active]:text-cyan-300">
            Gabagool ({gabaOpen.length} open / {gabaClosed.length} closed)
          </TabsTrigger>
          <TabsTrigger value="opportunities" className="text-xs data-[state=active]:bg-zinc-800">
            Opportunities ({arbOpps.total_tradable})
          </TabsTrigger>
          <TabsTrigger value="rejected" className="text-xs data-[state=active]:bg-zinc-800">
            Rejected ({arbOpps.total_rejected})
          </TabsTrigger>
          <TabsTrigger value="executions" className="text-xs data-[state=active]:bg-zinc-800">
            Executions ({allExecs.length})
          </TabsTrigger>
          <TabsTrigger value="diagnostics" className="text-xs data-[state=active]:bg-zinc-800">
            Diagnostics
          </TabsTrigger>
          <TabsTrigger value="health" className="text-xs data-[state=active]:bg-zinc-800">
            Health
          </TabsTrigger>
        </TabsList>

        <TabsContent value="gabagool" className="mt-4 space-y-4">
          <SectionCard title="Open Pairs (Awaiting Resolution)" testId="section-gaba-open">
            <DataTable columns={gabaOpenCols} data={gabaOpen} emptyMessage="No open Gabagool pairs — waiting for YES+NO sum < threshold" testId="gaba-open-table" />
          </SectionCard>
          <SectionCard title="Closed Pairs (Resolved)" testId="section-gaba-closed">
            <DataTable columns={gabaClosedCols} data={gabaClosed} emptyMessage="No closed Gabagool trades yet — pairs resolve when markets close" testId="gaba-closed-table" />
          </SectionCard>
        </TabsContent>

        <TabsContent value="opportunities" className="mt-4">
          <SectionCard testId="section-arb-opportunities">
            <DataTable columns={oppColumns} data={arbOpps.tradable || []} emptyMessage="No tradable opportunities — start engine & wait for market data" testId="arb-opp-table" />
          </SectionCard>
        </TabsContent>

        <TabsContent value="rejected" className="mt-4">
          <SectionCard testId="section-arb-rejected">
            <DataTable columns={rejectedColumns} data={arbOpps.rejected || []} emptyMessage="No rejected opportunities" testId="arb-rejected-table" />
          </SectionCard>
        </TabsContent>

        <TabsContent value="executions" className="mt-4">
          <SectionCard testId="section-arb-executions">
            <DataTable columns={execColumns} data={allExecs} emptyMessage="No arb executions yet" testId="arb-exec-table" />
          </SectionCard>
        </TabsContent>

        <TabsContent value="diagnostics" className="mt-4">
          <div className="space-y-5">
            {/* Raw Edges */}
            <SectionCard title="Recent Raw Edges (Pre-Filter)" testId="section-raw-edges">
              <div className="max-h-80 overflow-y-auto">
                <table className="w-full text-xs">
                  <thead className="text-zinc-500 sticky top-0 bg-zinc-900">
                    <tr>
                      <th className="text-left p-2">Type</th>
                      <th className="text-left p-2">Market</th>
                      <th className="text-right p-2">Gross Edge</th>
                      <th className="text-right p-2">Outcomes</th>
                      <th className="text-right p-2">Cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(diag.raw_edges || []).map((e, i) => (
                      <tr key={i} className="border-t border-zinc-800/50 hover:bg-zinc-800/30">
                        <td className="p-2">
                          <span className={`px-1 py-0.5 rounded text-[10px] ${e.type === 'multi_outcome' ? 'bg-purple-900/50 text-purple-300' : e.type === 'cross_market' ? 'bg-blue-900/50 text-blue-300' : 'bg-zinc-800 text-zinc-400'}`}>
                            {e.type}
                          </span>
                        </td>
                        <td className="p-2 text-zinc-300 max-w-[300px] truncate">{e.question || '—'}</td>
                        <td className="p-2 text-right font-mono">
                          <span className={e.gross_edge_bps > 0 ? 'text-emerald-400' : 'text-red-400'}>{e.gross_edge_bps}bps</span>
                        </td>
                        <td className="p-2 text-right text-zinc-400">{e.outcome_count || '—'}</td>
                        <td className="p-2 text-right text-zinc-400">{e.total_cost ? e.total_cost.toFixed(4) : '—'}</td>
                      </tr>
                    ))}
                    {(!diag.raw_edges || diag.raw_edges.length === 0) && (
                      <tr><td colSpan={5} className="text-center p-4 text-zinc-600">No raw edges found yet</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </SectionCard>

            {/* Rejection Log */}
            <SectionCard title="Recent Rejections (Post-Filter)" testId="section-rejection-log">
              <div className="max-h-80 overflow-y-auto">
                <table className="w-full text-xs">
                  <thead className="text-zinc-500 sticky top-0 bg-zinc-900">
                    <tr>
                      <th className="text-left p-2">Type</th>
                      <th className="text-left p-2">Market</th>
                      <th className="text-right p-2">Gross</th>
                      <th className="text-right p-2">Net</th>
                      <th className="text-right p-2">Liquidity</th>
                      <th className="text-left p-2">Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(diag.rejection_log || []).map((r, i) => (
                      <tr key={i} className="border-t border-zinc-800/50 hover:bg-zinc-800/30">
                        <td className="p-2">
                          <span className={`px-1 py-0.5 rounded text-[10px] ${r.type === 'multi_outcome' ? 'bg-purple-900/50 text-purple-300' : 'bg-zinc-800 text-zinc-400'}`}>
                            {r.type}
                          </span>
                        </td>
                        <td className="p-2 text-zinc-300 max-w-[250px] truncate">{r.question || '—'}</td>
                        <td className="p-2 text-right font-mono text-zinc-400">{r.gross_edge_bps}bps</td>
                        <td className="p-2 text-right font-mono text-red-400">{r.net_edge_bps}bps</td>
                        <td className="p-2 text-right text-zinc-400">${formatNumber(r.liquidity, 0)}</td>
                        <td className="p-2 text-zinc-500 max-w-[200px] truncate">{r.reason}</td>
                      </tr>
                    ))}
                    {(!diag.rejection_log || diag.rejection_log.length === 0) && (
                      <tr><td colSpan={6} className="text-center p-4 text-zinc-600">No rejections logged</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </SectionCard>
          </div>
        </TabsContent>

        <TabsContent value="health" className="mt-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            <SectionCard title="Scanner Metrics" testId="section-scanner-metrics">
              <div className="space-y-2 text-xs">
                {[
                  ['Total Scans', diagMetrics.total_scans || arbHealth.total_scans],
                  ['Markets Scanned', diag.markets_scanned],
                  ['Binary Pairs', diag.binary_pairs_found],
                  ['Multi-Outcome Groups', diag.multi_outcome_groups_found],
                  ['Raw Edges Found', diagMetrics.raw_edges_found],
                  ['Eligible', diagMetrics.eligible_count],
                  ['Executed', diagMetrics.executed_count],
                  ['Completed', diagMetrics.completed_count || arbHealth.completed_count],
                  ['Invalidated', diagMetrics.invalidated_count || arbHealth.invalidated_count],
                  ['Active Executions', diag.active_executions || arbHealth.active_executions],
                ].map(([label, val]) => (
                  <div key={label} className="flex justify-between">
                    <span className="text-zinc-500">{label}</span>
                    <span className="text-zinc-300 font-mono">{val ?? '—'}</span>
                  </div>
                ))}
              </div>
            </SectionCard>

            <SectionCard title="Scanner Config" testId="section-scanner-config">
              <div className="space-y-2 text-xs">
                {[
                  ['Scan Interval', `${config.scan_interval}s`],
                  ['Min Net Edge', `${config.min_net_edge_bps} bps`],
                  ['Min Liquidity', `$${config.min_liquidity}`],
                  ['Min Confidence', config.min_confidence],
                  ['Max Stale Age', `${config.max_stale_age_seconds}s`],
                  ['Default Size', config.default_size],
                  ['Max Concurrent Arbs', config.max_concurrent_arbs],
                ].map(([label, val]) => (
                  <div key={label} className="flex justify-between">
                    <span className="text-zinc-500">{label}</span>
                    <span className="text-zinc-300 font-mono">{val ?? '—'}</span>
                  </div>
                ))}
              </div>
            </SectionCard>

            {Object.keys(diagMetrics.rejection_reasons || rejReasons || {}).length > 0 && (
              <SectionCard title="Rejection Reasons" testId="section-rejection-reasons">
                <div className="space-y-2 text-xs">
                  {Object.entries(diagMetrics.rejection_reasons || rejReasons || {}).sort(([,a],[,b]) => b - a).map(([reason, count]) => (
                    <div key={reason} className="flex justify-between">
                      <span className="text-zinc-500">{reason}</span>
                      <span className="text-zinc-300 font-mono">{count}</span>
                    </div>
                  ))}
                </div>
              </SectionCard>
            )}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
