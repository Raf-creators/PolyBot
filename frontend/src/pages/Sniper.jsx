import { useEffect, useMemo, useState } from 'react';
import { useDashboardStore } from '../state/dashboardStore';
import { useApi } from '../hooks/useApi';
import { StatCard } from '../components/StatCard';
import { SectionCard } from '../components/SectionCard';
import { DataTable } from '../components/DataTable';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { formatBps, formatPrice, formatNumber, formatPercent, formatTimestamp, formatTimeAgo, truncate } from '../utils/formatters';

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
  const { fetchSniperSignals, fetchSniperExecutions, fetchSniperHealth } = useApi();
  const [tab, setTab] = useState('signals');

  useEffect(() => {
    fetchSniperSignals();
    fetchSniperExecutions();
    fetchSniperHealth();
    const interval = setInterval(() => {
      fetchSniperSignals();
      fetchSniperExecutions();
      fetchSniperHealth();
    }, 6000);
    return () => clearInterval(interval);
  }, [fetchSniperSignals, fetchSniperExecutions, fetchSniperHealth]);

  const config = health.config || {};
  const buffers = health.price_buffer_sizes || {};
  const rejReasons = health.rejection_reasons || {};
  const classFailReasons = health.classification_failure_reasons || {};

  const allExecs = useMemo(() => [
    ...(executions.active || []),
    ...(executions.completed || []).reverse(),
  ], [executions]);

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
    { key: 'volatility', label: 'Vol', align: 'right', render: (v) => v > 0 ? formatPercent(v * 100, 1) : '—' },
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
    { key: 'signal_id', label: 'Signal', render: (v) => <span className="text-zinc-400 font-mono">{truncate(v, 12)}</span> },
    { key: 'asset', label: 'Asset', render: (v) => <span className="text-zinc-200 font-medium">{v}</span> },
    { key: 'side', label: 'Side', render: (v) => (
      <span className={v === 'buy_yes' ? 'text-emerald-400' : 'text-red-400'}>{v}</span>
    )},
    { key: 'size', label: 'Size', align: 'right', render: (v) => formatNumber(v, 2) },
    { key: 'entry_price', label: 'Fill', align: 'right', render: (v) => v != null ? formatPrice(v) : '—' },
    { key: 'target_edge_bps', label: 'Target Edge', align: 'right', sortable: true, render: (v) => formatBps(v) },
    { key: 'status', label: 'Status', render: (v) => (
      <span className={`font-medium ${SIGNAL_STATUS_COLORS[v] || 'text-zinc-400'}`}>{v}</span>
    )},
    { key: 'submitted_at', label: 'Submitted', render: (v) => <span className="text-zinc-500">{formatTimestamp(v)}</span> },
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

      {/* Key Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <StatCard testId="stat-sniper-tradable" label="Tradable" value={signals.total_tradable} />
        <StatCard testId="stat-sniper-rejected" label="Rejected" value={signals.total_rejected} />
        <StatCard testId="stat-sniper-executed" label="Executed" value={health.signals_executed || 0} />
        <StatCard testId="stat-sniper-filled" label="Filled" value={health.signals_filled || 0} />
        <StatCard testId="stat-sniper-classified" label="Markets Classified" value={health.markets_classified || 0} />
        <StatCard testId="stat-sniper-scan-ms" label="Scan Latency" value={`${health.last_scan_duration_ms || 0}ms`} />
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-zinc-900 border border-zinc-800">
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
            {/* Volatility Panel */}
            <SectionCard title="Volatility" testId="section-sniper-vol">
              <div className="space-y-3 text-xs">
                <div className="flex justify-between">
                  <span className="text-zinc-500">BTC Realized Vol</span>
                  <span className={`font-mono ${health.btc_realized_vol ? 'text-zinc-200' : 'text-zinc-600'}`}>
                    {health.btc_realized_vol ? formatPercent(health.btc_realized_vol * 100, 1) : 'Warming up…'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">ETH Realized Vol</span>
                  <span className={`font-mono ${health.eth_realized_vol ? 'text-zinc-200' : 'text-zinc-600'}`}>
                    {health.eth_realized_vol ? formatPercent(health.eth_realized_vol * 100, 1) : 'Warming up…'}
                  </span>
                </div>
                <div className="pt-2 border-t border-zinc-800 space-y-2">
                  <div className="flex justify-between">
                    <span className="text-zinc-500">BTC Samples</span>
                    <span className="font-mono text-zinc-400">
                      {buffers.BTC || 0} / {config.vol_min_samples || 30}
                      {(buffers.BTC || 0) >= (config.vol_min_samples || 30) ? (
                        <span className="ml-2 text-emerald-400">Ready</span>
                      ) : (
                        <span className="ml-2 text-amber-400">Filling</span>
                      )}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">ETH Samples</span>
                    <span className="font-mono text-zinc-400">
                      {buffers.ETH || 0} / {config.vol_min_samples || 30}
                      {(buffers.ETH || 0) >= (config.vol_min_samples || 30) ? (
                        <span className="ml-2 text-emerald-400">Ready</span>
                      ) : (
                        <span className="ml-2 text-amber-400">Filling</span>
                      )}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Vol Floor</span>
                    <span className="font-mono text-zinc-400">{config.vol_floor ? formatPercent(config.vol_floor * 100, 0) : '—'}</span>
                  </div>
                </div>
              </div>
            </SectionCard>

            {/* Scanner Metrics */}
            <SectionCard title="Scanner Metrics" testId="section-sniper-metrics">
              <div className="space-y-2 text-xs">
                {[
                  ['Total Scans', health.total_scans],
                  ['Scan Duration', `${health.last_scan_duration_ms || 0}ms`],
                  ['Markets Classified', health.markets_classified],
                  ['Markets Evaluated', health.markets_evaluated],
                  ['Signals Generated', health.signals_generated],
                  ['Signals Rejected', health.signals_rejected],
                  ['Signals Executed', health.signals_executed],
                  ['Signals Filled', health.signals_filled],
                  ['Active Executions', health.active_executions],
                  ['Completed', health.completed_executions],
                  ['Stale Feed Skips', health.stale_feed_skips],
                ].map(([label, val]) => (
                  <div key={label} className="flex justify-between">
                    <span className="text-zinc-500">{label}</span>
                    <span className="text-zinc-300 font-mono">{val ?? '—'}</span>
                  </div>
                ))}
              </div>
            </SectionCard>

            {/* Rejection Reasons */}
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

            {/* Scanner Config */}
            <SectionCard title="Scanner Config" testId="section-sniper-config">
              <div className="space-y-2 text-xs">
                {[
                  ['Scan Interval', `${config.scan_interval}s`],
                  ['Min Edge', `${config.min_edge_bps} bps`],
                  ['Min Liquidity', `$${config.min_liquidity}`],
                  ['Min Confidence', config.min_confidence],
                  ['Max Spread', config.max_spread],
                  ['Min TTE', `${config.min_tte_seconds}s`],
                  ['Max TTE', `${config.max_tte_seconds}s`],
                  ['Default Size', config.default_size],
                  ['Max Concurrent', config.max_concurrent_signals],
                  ['Cooldown', `${config.cooldown_seconds}s`],
                  ['Momentum Weight', config.momentum_weight],
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
