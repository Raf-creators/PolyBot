import { useEffect, useMemo, useState } from 'react';
import { useDashboardStore } from '../state/dashboardStore';
import { useApi } from '../hooks/useApi';
import { StatCard } from '../components/StatCard';
import { SectionCard } from '../components/SectionCard';
import { DataTable } from '../components/DataTable';
import { EmptyState } from '../components/EmptyState';
import { formatBps, formatPrice, formatNumber, formatTimestamp, formatTimeAgo, truncate } from '../utils/formatters';
import { ARB_STATUS_COLORS } from '../utils/constants';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { ArrowLeftRight, CheckCircle, XCircle, Clock, TrendingUp } from 'lucide-react';

export default function Arbitrage() {
  const arbOpps = useDashboardStore((s) => s.arbOpportunities);
  const arbExecs = useDashboardStore((s) => s.arbExecutions);
  const arbHealth = useDashboardStore((s) => s.arbHealth);
  const { fetchArbOpportunities, fetchArbExecutions, fetchArbHealth } = useApi();
  const [tab, setTab] = useState('opportunities');

  useEffect(() => {
    fetchArbOpportunities();
    fetchArbExecutions();
    fetchArbHealth();
    const interval = setInterval(() => {
      fetchArbOpportunities();
      fetchArbExecutions();
      fetchArbHealth();
    }, 8000);
    return () => clearInterval(interval);
  }, [fetchArbOpportunities, fetchArbExecutions, fetchArbHealth]);

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

  return (
    <div data-testid="arbitrage-page" className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-zinc-100">Arbitrage Scanner</h1>
        <span className="text-xs text-zinc-600 font-mono">
          {arbHealth.running ? 'SCANNING' : 'IDLE'} | Scans: {arbHealth.total_scans || 0}
        </span>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <StatCard testId="stat-tradable" label="Tradable" value={arbOpps.total_tradable} />
        <StatCard testId="stat-rejected" label="Rejected" value={arbOpps.total_rejected} />
        <StatCard testId="stat-executed" label="Executed" value={arbHealth.executed_count || 0} />
        <StatCard testId="stat-completed" label="Completed" value={arbHealth.completed_count || 0} />
        <StatCard testId="stat-pairs-scanned" label="Pairs Scanned" value={arbHealth.pairs_scanned || 0} />
        <StatCard testId="stat-last-scan" label="Last Scan" value={formatTimeAgo(arbHealth.last_scan_time)} />
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-zinc-900 border border-zinc-800">
          <TabsTrigger value="opportunities" className="text-xs data-[state=active]:bg-zinc-800">
            Opportunities ({arbOpps.total_tradable})
          </TabsTrigger>
          <TabsTrigger value="rejected" className="text-xs data-[state=active]:bg-zinc-800">
            Rejected ({arbOpps.total_rejected})
          </TabsTrigger>
          <TabsTrigger value="executions" className="text-xs data-[state=active]:bg-zinc-800">
            Executions ({allExecs.length})
          </TabsTrigger>
          <TabsTrigger value="health" className="text-xs data-[state=active]:bg-zinc-800">
            Health
          </TabsTrigger>
        </TabsList>

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

        <TabsContent value="health" className="mt-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <SectionCard title="Scanner Metrics" testId="section-scanner-metrics">
              <div className="space-y-2 text-xs">
                {[
                  ['Total Scans', arbHealth.total_scans],
                  ['Pairs Scanned', arbHealth.pairs_scanned],
                  ['Raw Edges Found', arbHealth.raw_edges_found],
                  ['Eligible', arbHealth.eligible_count],
                  ['Executed', arbHealth.executed_count],
                  ['Completed', arbHealth.completed_count],
                  ['Invalidated', arbHealth.invalidated_count],
                  ['Active Executions', arbHealth.active_executions],
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

            {Object.keys(rejReasons).length > 0 && (
              <SectionCard title="Rejection Reasons" testId="section-rejection-reasons">
                <div className="space-y-2 text-xs">
                  {Object.entries(rejReasons).sort(([,a],[,b]) => b - a).map(([reason, count]) => (
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
