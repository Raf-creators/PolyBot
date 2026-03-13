import { useEffect, useMemo, useState } from 'react';
import { useDashboardStore } from '../state/dashboardStore';
import { useApi } from '../hooks/useApi';
import { StatCard } from '../components/StatCard';
import { SectionCard } from '../components/SectionCard';
import { DataTable } from '../components/DataTable';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { formatBps, formatPrice, formatNumber, formatTimestamp, formatTimeAgo, truncate } from '../utils/formatters';

const STATUS_COLORS = {
  generated: 'text-blue-400',
  submitted: 'text-blue-400',
  filled: 'text-emerald-400',
  rejected: 'text-red-400',
  expired: 'text-zinc-500',
};

export default function Weather() {
  const signals = useDashboardStore((s) => s.weatherSignals);
  const executions = useDashboardStore((s) => s.weatherExecutions);
  const health = useDashboardStore((s) => s.weatherHealth);
  const forecasts = useDashboardStore((s) => s.weatherForecasts);
  const { fetchWeatherSignals, fetchWeatherExecutions, fetchWeatherHealth, fetchWeatherForecasts } = useApi();
  const [tab, setTab] = useState('signals');

  useEffect(() => {
    fetchWeatherSignals();
    fetchWeatherExecutions();
    fetchWeatherHealth();
    fetchWeatherForecasts();
    const interval = setInterval(() => {
      fetchWeatherSignals();
      fetchWeatherExecutions();
      fetchWeatherHealth();
      fetchWeatherForecasts();
    }, 8000);
    return () => clearInterval(interval);
  }, [fetchWeatherSignals, fetchWeatherExecutions, fetchWeatherHealth, fetchWeatherForecasts]);

  const config = health.config || {};
  const feedHealth = health.feed_health || {};
  const rejReasons = health.rejection_reasons || {};
  const classFailReasons = health.classification_failure_reasons || {};
  const classifications = health.classifications || {};

  const allExecs = useMemo(() => [
    ...(executions.active || []),
    ...(executions.completed || []).reverse(),
  ], [executions]);

  // Forecasts as array for table
  const forecastRows = useMemo(() => {
    return Object.entries(forecasts).map(([key, val]) => {
      const [station, date] = key.split(':');
      const cls = Object.values(classifications).find(c => c.station === station && c.date === date);
      return {
        id: key,
        station_id: station,
        target_date: date,
        forecast_high: val?.forecast_high_f,
        lead_hours: val?.lead_hours,
        source: val?.source || '—',
        fetched_at: val?.fetched_at,
        buckets: cls?.buckets || 0,
      };
    });
  }, [forecasts, classifications]);

  // ---- Column Definitions ----
  const signalColumns = [
    { key: 'station_id', label: 'Station', render: (v) => <span className="text-cyan-400 font-medium font-mono">{v}</span> },
    { key: 'target_date', label: 'Date', render: (v) => <span className="text-zinc-300">{v}</span> },
    { key: 'bucket_label', label: 'Bucket', render: (v) => <span className="text-zinc-200 font-medium">{v}</span> },
    { key: 'forecast_high_f', label: 'Fcst', align: 'right', render: (v) => <span className="font-mono">{v ? `${v}F` : '—'}</span> },
    { key: 'sigma', label: 'Sigma', align: 'right', render: (v) => <span className="font-mono text-zinc-400">{v ? `${v}F` : '—'}</span> },
    { key: 'model_prob', label: 'Model', align: 'right', sortable: true, render: (v) => (
      <span className="font-mono">{v > 0 ? formatPrice(v) : '—'}</span>
    )},
    { key: 'market_price', label: 'Mkt', align: 'right', sortable: true, render: (v) => (
      <span className="font-mono">{v > 0 ? formatPrice(v) : '—'}</span>
    )},
    { key: 'edge_bps', label: 'Edge', align: 'right', sortable: true, render: (v) => (
      <span className={v > 0 ? 'text-emerald-400 font-mono' : 'text-zinc-500 font-mono'}>{formatBps(v)}</span>
    )},
    { key: 'confidence', label: 'Conf', align: 'right', sortable: true, render: (v) => (
      <span className={`font-mono ${v >= 0.6 ? 'text-emerald-400' : v >= 0.3 ? 'text-amber-400' : 'text-zinc-500'}`}>
        {v > 0 ? (v * 100).toFixed(0) + '%' : '—'}
      </span>
    )},
    { key: 'recommended_size', label: 'Size', align: 'right', render: (v) => <span className="font-mono">{v > 0 ? formatNumber(v, 1) : '—'}</span> },
    { key: 'lead_hours', label: 'Lead', align: 'right', render: (v) => <span className="font-mono text-zinc-400">{v > 0 ? `${v.toFixed(0)}h` : '—'}</span> },
  ];

  const rejectedColumns = [
    ...signalColumns.slice(0, 5),
    { key: 'rejection_reason', label: 'Reason', render: (v) => <span className="text-zinc-500 text-xs">{v}</span> },
    { key: 'detected_at', label: 'Detected', render: (v) => <span className="text-zinc-600">{formatTimeAgo(v)}</span> },
  ];

  const execColumns = [
    { key: 'signal_id', label: 'Signal', render: (v) => <span className="text-zinc-400 font-mono">{truncate(v, 10)}</span> },
    { key: 'station_id', label: 'Station', render: (v) => <span className="text-cyan-400 font-mono">{v}</span> },
    { key: 'bucket_label', label: 'Bucket', render: (v) => <span className="text-zinc-200 font-medium">{v}</span> },
    { key: 'size', label: 'Size', align: 'right', render: (v) => formatNumber(v, 2) },
    { key: 'entry_price', label: 'Fill', align: 'right', render: (v) => v != null ? formatPrice(v) : '—' },
    { key: 'target_edge_bps', label: 'Edge', align: 'right', sortable: true, render: (v) => formatBps(v) },
    { key: 'status', label: 'Status', render: (v) => (
      <span className={`font-medium ${STATUS_COLORS[v] || 'text-zinc-400'}`}>{v}</span>
    )},
    { key: 'submitted_at', label: 'Submitted', render: (v) => <span className="text-zinc-500">{formatTimestamp(v)}</span> },
    { key: 'filled_at', label: 'Filled', render: (v) => v ? <span className="text-zinc-500">{formatTimestamp(v)}</span> : '—' },
  ];

  const forecastColumns = [
    { key: 'station_id', label: 'Station', render: (v) => <span className="text-cyan-400 font-mono font-medium">{v}</span> },
    { key: 'target_date', label: 'Date', render: (v) => <span className="text-zinc-300">{v}</span> },
    { key: 'forecast_high', label: 'Fcst High', align: 'right', sortable: true, render: (v) => (
      <span className="font-mono text-amber-300">{v != null ? `${v}F` : '—'}</span>
    )},
    { key: 'source', label: 'Source', render: (v) => <span className="text-zinc-500">{v}</span> },
    { key: 'lead_hours', label: 'Lead', align: 'right', render: (v) => <span className="font-mono text-zinc-400">{v != null ? `${v.toFixed(0)}h` : '—'}</span> },
    { key: 'buckets', label: 'Buckets', align: 'right', render: (v) => <span className="font-mono">{v}</span> },
    { key: 'fetched_at', label: 'Fetched', render: (v) => <span className="text-zinc-600">{formatTimeAgo(v)}</span> },
  ];

  return (
    <div data-testid="weather-page" className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-zinc-100">Weather Trader</h1>
        <span data-testid="weather-scan-status" className="text-xs text-zinc-600 font-mono">
          {health.running ? 'SCANNING' : 'IDLE'} | Scans: {health.total_scans || 0}
        </span>
      </div>

      {/* Key Metrics */}
      <div data-testid="weather-stats-grid" className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        <StatCard testId="stat-weather-classified" label="Markets" value={health.markets_classified || 0} />
        <StatCard testId="stat-weather-tradable" label="Tradable" value={signals.total_tradable} />
        <StatCard testId="stat-weather-rejected" label="Rejected" value={signals.total_rejected} />
        <StatCard testId="stat-weather-executed" label="Executed" value={health.signals_executed || 0} />
        <StatCard testId="stat-weather-filled" label="Filled" value={health.signals_filled || 0} />
        <StatCard testId="stat-weather-forecasts" label="Forecasts" value={health.forecasts_fetched || 0}
          sub={health.forecasts_missing ? `${health.forecasts_missing} missing` : undefined} />
        <StatCard testId="stat-weather-scan-ms" label="Scan Latency" value={`${health.last_scan_duration_ms || 0}ms`} />
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-zinc-900 border border-zinc-800">
          <TabsTrigger data-testid="tab-signals" value="signals" className="text-xs data-[state=active]:bg-zinc-800">
            Signals ({signals.total_tradable})
          </TabsTrigger>
          <TabsTrigger data-testid="tab-rejected" value="rejected" className="text-xs data-[state=active]:bg-zinc-800">
            Rejected ({signals.total_rejected})
          </TabsTrigger>
          <TabsTrigger data-testid="tab-executions" value="executions" className="text-xs data-[state=active]:bg-zinc-800">
            Executions ({allExecs.length})
          </TabsTrigger>
          <TabsTrigger data-testid="tab-forecasts" value="forecasts" className="text-xs data-[state=active]:bg-zinc-800">
            Forecasts ({forecastRows.length})
          </TabsTrigger>
          <TabsTrigger data-testid="tab-health" value="health" className="text-xs data-[state=active]:bg-zinc-800">
            Health
          </TabsTrigger>
        </TabsList>

        {/* Signals Tab */}
        <TabsContent value="signals" className="mt-4">
          <SectionCard testId="section-weather-signals">
            <DataTable columns={signalColumns} data={signals.tradable || []}
              emptyMessage="No tradable weather signals — start engine & wait for weather markets" testId="weather-signals-table" />
          </SectionCard>
        </TabsContent>

        {/* Rejected Tab */}
        <TabsContent value="rejected" className="mt-4">
          <SectionCard testId="section-weather-rejected">
            <DataTable columns={rejectedColumns} data={signals.rejected || []}
              emptyMessage="No rejected signals" testId="weather-rejected-table" />
          </SectionCard>
        </TabsContent>

        {/* Executions Tab */}
        <TabsContent value="executions" className="mt-4">
          <SectionCard testId="section-weather-executions">
            <DataTable columns={execColumns} data={allExecs}
              emptyMessage="No weather executions yet" testId="weather-exec-table" />
          </SectionCard>
        </TabsContent>

        {/* Forecasts Tab */}
        <TabsContent value="forecasts" className="mt-4">
          <SectionCard testId="section-weather-forecasts">
            <DataTable columns={forecastColumns} data={forecastRows}
              emptyMessage="No forecasts cached — weather markets will trigger forecast fetches" testId="weather-forecasts-table" />
          </SectionCard>
        </TabsContent>

        {/* Health Tab */}
        <TabsContent value="health" className="mt-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {/* Calibration Status */}
            <SectionCard title="Calibration" testId="section-weather-calibration">
              <div className="space-y-3 text-xs">
                <div className="flex justify-between">
                  <span className="text-zinc-500">Sigma Source</span>
                  <span className="text-amber-400 font-mono">Default NWS MOS Table</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Historical Calibration</span>
                  <span className="text-zinc-500 font-mono">Not Available</span>
                </div>
                <div className="pt-2 border-t border-zinc-800 text-zinc-600">
                  Using published NWS accuracy data for sigma estimates. Historical calibration requires Open-Meteo Previous Runs API bootstrap (planned enhancement).
                </div>
                <div className="space-y-1.5 pt-2 border-t border-zinc-800">
                  <div className="text-zinc-500 mb-1">Default Sigma by Lead Time</div>
                  {[
                    ['0-24h', '1.8F'],
                    ['24-48h', '2.7F'],
                    ['48-72h', '3.4F'],
                    ['72-120h', '4.8F'],
                    ['120-168h', '6.2F'],
                  ].map(([bracket, sigma]) => (
                    <div key={bracket} className="flex justify-between">
                      <span className="text-zinc-500">{bracket}</span>
                      <span className="text-zinc-300 font-mono">{sigma}</span>
                    </div>
                  ))}
                </div>
              </div>
            </SectionCard>

            {/* Scanner Metrics */}
            <SectionCard title="Scanner Metrics" testId="section-weather-metrics">
              <div className="space-y-2 text-xs">
                {[
                  ['Total Scans', health.total_scans],
                  ['Scan Duration', `${health.last_scan_duration_ms || 0}ms`],
                  ['Markets Classified', health.markets_classified],
                  ['Forecasts Fetched', health.forecasts_fetched],
                  ['Forecasts Missing', health.forecasts_missing],
                  ['Forecasts Stale', health.forecasts_stale],
                  ['Opportunities Evaluated', health.opportunities_evaluated],
                  ['Opportunities Rejected', health.opportunities_rejected],
                  ['Signals Generated', health.signals_generated],
                  ['Signals Executed', health.signals_executed],
                  ['Signals Filled', health.signals_filled],
                  ['Active Executions', health.active_executions],
                  ['Completed', health.completed_executions],
                ].map(([label, val]) => (
                  <div key={label} className="flex justify-between">
                    <span className="text-zinc-500">{label}</span>
                    <span className="text-zinc-300 font-mono">{val ?? '—'}</span>
                  </div>
                ))}
              </div>
            </SectionCard>

            {/* Feed Health */}
            <SectionCard title="Feed Health" testId="section-weather-feed-health">
              <div className="space-y-2 text-xs">
                {[
                  ['Open-Meteo Errors', feedHealth.open_meteo_errors],
                  ['Open-Meteo Last Error', feedHealth.open_meteo_last_error ? truncate(String(feedHealth.open_meteo_last_error), 40) : null],
                  ['NWS Errors', feedHealth.nws_errors],
                  ['NWS Last Error', feedHealth.nws_last_error ? truncate(String(feedHealth.nws_last_error), 40) : null],
                  ['Forecast Cache', feedHealth.forecast_cache_size],
                  ['Observation Cache', feedHealth.observation_cache_size],
                ].map(([label, val]) => (
                  <div key={label} className="flex justify-between">
                    <span className="text-zinc-500">{label}</span>
                    <span className={`font-mono ${String(label).includes('Error') && val ? 'text-red-400' : 'text-zinc-300'}`}>
                      {val ?? '—'}
                    </span>
                  </div>
                ))}
              </div>
            </SectionCard>

            {/* Rejection Reasons */}
            <SectionCard title="Rejection Reasons" testId="section-weather-rejections">
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

            {/* Strategy Config */}
            <SectionCard title="Strategy Config" testId="section-weather-config">
              <div className="space-y-2 text-xs">
                {[
                  ['Scan Interval', `${config.scan_interval}s`],
                  ['Forecast Refresh', `${config.forecast_refresh_interval}s`],
                  ['Min Edge', `${config.min_edge_bps} bps`],
                  ['Min Liquidity', `$${config.min_liquidity}`],
                  ['Min Confidence', config.min_confidence],
                  ['Max Sigma', `${config.max_sigma}F`],
                  ['Min Lead', `${config.min_hours_to_resolution}h`],
                  ['Max Lead', `${config.max_hours_to_resolution}h`],
                  ['Default Size', config.default_size],
                  ['Max Size', config.max_signal_size],
                  ['Kelly Scale', config.kelly_scale],
                  ['Max Concurrent', config.max_concurrent_signals],
                  ['Max Buckets/Market', config.max_buckets_per_market],
                  ['Cooldown', `${config.cooldown_seconds}s`],
                ].map(([label, val]) => (
                  <div key={label} className="flex justify-between">
                    <span className="text-zinc-500">{label}</span>
                    <span className="text-zinc-300 font-mono">{val ?? '—'}</span>
                  </div>
                ))}
              </div>
            </SectionCard>

            {/* Classified Markets */}
            <SectionCard title="Classified Markets" testId="section-weather-classified">
              <div className="space-y-2 text-xs">
                {Object.keys(classifications).length === 0 ? (
                  <p className="text-zinc-600">No weather markets classified</p>
                ) : (
                  Object.entries(classifications).map(([cid, info]) => (
                    <div key={cid} className="flex justify-between items-center">
                      <span className="text-cyan-400 font-mono">{info.station}</span>
                      <span className="text-zinc-400">{info.date}</span>
                      <span className="text-zinc-500">{info.buckets} buckets</span>
                    </div>
                  ))
                )}
              </div>
            </SectionCard>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
