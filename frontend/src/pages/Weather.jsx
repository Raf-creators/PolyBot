import { useEffect, useMemo, useState, useCallback } from 'react';
import { useDashboardStore } from '../state/dashboardStore';
import { useApi } from '../hooks/useApi';
import { StatCard } from '../components/StatCard';
import { SectionCard } from '../components/SectionCard';
import { DataTable } from '../components/DataTable';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { formatBps, formatPrice, formatNumber, formatTimestamp, formatTimeAgo, truncate } from '../utils/formatters';
import axios from 'axios';
import { API_BASE } from '../utils/constants';

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
  const demoMode = useDashboardStore((s) => s.demoMode);
  const { fetchWeatherSignals, fetchWeatherExecutions, fetchWeatherHealth, fetchWeatherForecasts } = useApi();
  const [tab, setTab] = useState('signals');

  // Calibration / accuracy state (fetched directly since these are weather-specific)
  const [shadowSummary, setShadowSummary] = useState(null);
  const [accuracyHistory, setAccuracyHistory] = useState([]);
  const [stationSummary, setStationSummary] = useState({});
  const [calibrationHealth, setCalibrationHealth] = useState(null);
  const [sigmaCalStatus, setSigmaCalStatus] = useState(null);
  const [calRunning, setCalRunning] = useState(false);

  const prefix = demoMode ? '/demo' : '';

  const fetchCalibration = useCallback(async () => {
    if (demoMode) return;
    try {
      const [ss, ah, cal, sigCal] = await Promise.all([
        axios.get(`${API_BASE}/strategies/weather/shadow-summary`),
        axios.get(`${API_BASE}/strategies/weather/accuracy/history?limit=50`),
        axios.get(`${API_BASE}/strategies/weather/accuracy/calibration`),
        axios.get(`${API_BASE}/strategies/weather/calibration/status`),
      ]);
      setShadowSummary(ss.data);
      setAccuracyHistory(ah.data);
      setCalibrationHealth(cal.data);
      setStationSummary(cal.data?.station_summaries || {});
      setSigmaCalStatus(sigCal.data);
    } catch {}
  }, [demoMode]);

  useEffect(() => {
    fetchWeatherSignals();
    fetchWeatherExecutions();
    fetchWeatherHealth();
    fetchWeatherForecasts();
    fetchCalibration();
    const interval = setInterval(() => {
      fetchWeatherSignals();
      fetchWeatherExecutions();
      fetchWeatherHealth();
      fetchWeatherForecasts();
    }, 8000);
    const calInterval = setInterval(fetchCalibration, 30000);
    return () => { clearInterval(interval); clearInterval(calInterval); };
  }, [fetchWeatherSignals, fetchWeatherExecutions, fetchWeatherHealth, fetchWeatherForecasts, fetchCalibration]);

  const config = health.config || {};
  const feedHealth = health.feed_health || {};
  const clobHealth = health.clob_ws_health || {};
  const rejReasons = health.rejection_reasons || {};
  const classFailReasons = health.classification_failure_reasons || {};
  const classifications = health.classifications || {};
  const isShadow = health.is_shadow || shadowSummary?.is_shadow;
  const execMode = health.execution_mode || shadowSummary?.execution_mode || 'paper';

  const allExecs = useMemo(() => [
    ...(executions.active || []),
    ...(executions.completed || []).reverse(),
  ], [executions]);

  const forecastRows = useMemo(() => {
    return Object.entries(forecasts).map(([key, val]) => {
      const [station, date] = key.split(':');
      const cls = Object.values(classifications).find(c => c.station === station && c.date === date);
      return {
        id: key, station_id: station, target_date: date,
        forecast_high: val?.forecast_high_f, lead_hours: val?.lead_hours,
        source: val?.source || '—', fetched_at: val?.fetched_at, buckets: cls?.buckets || 0,
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
    { key: 'model_prob', label: 'Model', align: 'right', sortable: true, render: (v) => <span className="font-mono">{v > 0 ? formatPrice(v) : '—'}</span> },
    { key: 'market_price', label: 'Mkt', align: 'right', sortable: true, render: (v) => <span className="font-mono">{v > 0 ? formatPrice(v) : '—'}</span> },
    { key: 'edge_bps', label: 'Edge', align: 'right', sortable: true, render: (v) => <span className={v > 0 ? 'text-emerald-400 font-mono' : 'text-zinc-500 font-mono'}>{formatBps(v)}</span> },
    { key: 'confidence', label: 'Conf', align: 'right', sortable: true, render: (v) => (
      <span className={`font-mono ${v >= 0.6 ? 'text-emerald-400' : v >= 0.3 ? 'text-amber-400' : 'text-zinc-500'}`}>{v > 0 ? (v * 100).toFixed(0) + '%' : '—'}</span>
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
    { key: 'status', label: 'Status', render: (v) => <span className={`font-medium ${STATUS_COLORS[v] || 'text-zinc-400'}`}>{v}</span> },
    { key: 'submitted_at', label: 'Submitted', render: (v) => <span className="text-zinc-500">{formatTimestamp(v)}</span> },
    { key: 'filled_at', label: 'Filled', render: (v) => v ? <span className="text-zinc-500">{formatTimestamp(v)}</span> : '—' },
  ];

  const forecastColumns = [
    { key: 'station_id', label: 'Station', render: (v) => <span className="text-cyan-400 font-mono font-medium">{v}</span> },
    { key: 'target_date', label: 'Date', render: (v) => <span className="text-zinc-300">{v}</span> },
    { key: 'forecast_high', label: 'Fcst High', align: 'right', sortable: true, render: (v) => <span className="font-mono text-amber-300">{v != null ? `${v}F` : '—'}</span> },
    { key: 'source', label: 'Source', render: (v) => <span className="text-zinc-500">{v}</span> },
    { key: 'lead_hours', label: 'Lead', align: 'right', render: (v) => <span className="font-mono text-zinc-400">{v != null ? `${v.toFixed(0)}h` : '—'}</span> },
    { key: 'buckets', label: 'Buckets', align: 'right', render: (v) => <span className="font-mono">{v}</span> },
    { key: 'fetched_at', label: 'Fetched', render: (v) => <span className="text-zinc-600">{formatTimeAgo(v)}</span> },
  ];

  const accuracyColumns = [
    { key: 'station_id', label: 'Station', render: (v) => <span className="text-cyan-400 font-mono">{v}</span> },
    { key: 'target_date', label: 'Date', render: (v) => <span className="text-zinc-300">{v}</span> },
    { key: 'forecast_high_f', label: 'Forecast', align: 'right', render: (v) => <span className="font-mono text-amber-300">{v?.toFixed(1)}F</span> },
    { key: 'observed_high_f', label: 'Actual', align: 'right', render: (v) => v != null ? <span className="font-mono text-emerald-400">{v.toFixed(1)}F</span> : <span className="text-zinc-600">pending</span> },
    { key: 'forecast_error_f', label: 'Error', align: 'right', render: (v) => v != null ? <span className={`font-mono ${Math.abs(v) > 3 ? 'text-red-400' : Math.abs(v) > 1.5 ? 'text-amber-400' : 'text-emerald-400'}`}>{v > 0 ? '+' : ''}{v.toFixed(1)}F</span> : '—' },
    { key: 'sigma_used', label: 'Sigma', align: 'right', render: (v) => <span className="font-mono text-zinc-400">{v?.toFixed(2)}F</span> },
    { key: 'lead_hours', label: 'Lead', align: 'right', render: (v) => <span className="font-mono text-zinc-400">{v?.toFixed(0)}h</span> },
    { key: 'calibration_source', label: 'Source', render: (v) => (
      <Badge variant="outline" className={`text-[9px] ${v === 'default_sigma_table' ? 'border-amber-500/30 text-amber-400' : 'border-emerald-500/30 text-emerald-400'}`}>
        {v === 'default_sigma_table' ? 'DEFAULT' : 'CALIBRATED'}
      </Badge>
    )},
    { key: 'resolved', label: 'Status', render: (v) => (
      <Badge variant="outline" className={`text-[9px] ${v ? 'border-emerald-500/30 text-emerald-400' : 'border-zinc-700 text-zinc-500'}`}>
        {v ? 'RESOLVED' : 'PENDING'}
      </Badge>
    )},
  ];

  return (
    <div data-testid="weather-page" className="space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-zinc-100">Weather Trader</h1>
          <Badge
            data-testid="weather-exec-mode-badge"
            variant="outline"
            className={`text-[10px] font-mono uppercase ${isShadow ? 'border-amber-500/30 text-amber-400' : execMode === 'live' ? 'border-red-500/30 text-red-400' : 'border-zinc-700 text-zinc-500'}`}
          >
            {execMode}
          </Badge>
        </div>
        <span data-testid="weather-scan-status" className="text-xs text-zinc-600 font-mono">
          {health.running ? 'SCANNING' : 'IDLE'} | Scans: {health.total_scans || 0}
        </span>
      </div>

      {/* Key Metrics */}
      <div data-testid="weather-stats-grid" className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-3">
        <StatCard testId="stat-weather-classified" label="Markets" value={health.markets_classified || health.classified_markets || 0} />
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
          <TabsTrigger data-testid="tab-calibration" value="calibration" className="text-xs data-[state=active]:bg-zinc-800">
            Calibration
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

        {/* Calibration Tab */}
        <TabsContent value="calibration" className="mt-4">
          <div className="space-y-5">
            {/* Shadow Mode Summary */}
            <ShadowSummarySection summary={shadowSummary} config={config} isShadow={isShadow} execMode={execMode} />

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              {/* Calibration Health */}
              <CalibrationHealthSection health={calibrationHealth} />
              {/* Historical Sigma Calibration */}
              <SigmaCalibrationSection
                status={sigmaCalStatus}
                calRunning={calRunning}
                onRunCalibration={async () => {
                  setCalRunning(true);
                  try {
                    await axios.post(`${API_BASE}/strategies/weather/calibration/run`);
                    await fetchCalibration();
                  } catch {}
                  setCalRunning(false);
                }}
                onReload={async () => {
                  try {
                    await axios.post(`${API_BASE}/strategies/weather/calibration/reload`);
                    fetchWeatherHealth();
                  } catch {}
                }}
              />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              {/* Per-Station Accuracy */}
              <StationAccuracySection stations={stationSummary} />
              {/* Per-Station Sigma Values */}
              <StationSigmaSection status={sigmaCalStatus} />
            </div>

            {/* Accuracy Log */}
            <SectionCard title="Forecast Accuracy Log" testId="section-accuracy-log">
              <DataTable columns={accuracyColumns} data={accuracyHistory}
                emptyMessage="No forecast accuracy records yet — data is collected as the strategy runs"
                testId="accuracy-log-table" />
            </SectionCard>
          </div>
        </TabsContent>

        {/* Health Tab */}
        <TabsContent value="health" className="mt-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
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
                  Using published NWS accuracy data for sigma estimates. See Calibration tab for live accuracy tracking.
                </div>
                <div className="space-y-1.5 pt-2 border-t border-zinc-800">
                  <div className="text-zinc-500 mb-1">Default Sigma by Lead Time</div>
                  {[['0-24h', '1.8F'],['24-48h', '2.7F'],['48-72h', '3.4F'],['72-120h', '4.8F'],['120-168h', '6.2F']].map(([bracket, sigma]) => (
                    <div key={bracket} className="flex justify-between">
                      <span className="text-zinc-500">{bracket}</span>
                      <span className="text-zinc-300 font-mono">{sigma}</span>
                    </div>
                  ))}
                </div>
              </div>
            </SectionCard>

            <SectionCard title="Scanner Metrics" testId="section-weather-metrics">
              <div className="space-y-2 text-xs">
                {[
                  ['Total Scans', health.total_scans], ['Scan Duration', `${health.last_scan_duration_ms || 0}ms`],
                  ['Markets Classified', health.markets_classified || health.classified_markets],
                  ['Forecasts Fetched', health.forecasts_fetched], ['Forecasts Missing', health.forecasts_missing],
                  ['Forecasts Stale', health.forecasts_stale], ['Opportunities Evaluated', health.opportunities_evaluated],
                  ['Opportunities Rejected', health.opportunities_rejected], ['Signals Generated', health.signals_generated],
                  ['Signals Executed', health.signals_executed], ['Signals Filled', health.signals_filled],
                  ['Active Executions', health.active_executions], ['Completed', health.completed_executions],
                ].map(([label, val]) => (
                  <div key={label} className="flex justify-between">
                    <span className="text-zinc-500">{label}</span>
                    <span className="text-zinc-300 font-mono">{val ?? '—'}</span>
                  </div>
                ))}
              </div>
            </SectionCard>

            <SectionCard title="Feed Health" testId="section-weather-feed-health">
              <div className="space-y-2 text-xs">
                {[
                  ['Open-Meteo Errors', feedHealth.open_meteo_errors],
                  ['Open-Meteo Last Error', feedHealth.open_meteo_last_error ? truncate(String(feedHealth.open_meteo_last_error), 40) : null],
                  ['NWS Errors', feedHealth.nws_errors],
                  ['NWS Last Error', feedHealth.nws_last_error ? truncate(String(feedHealth.nws_last_error), 40) : null],
                  ['Forecast Cache', feedHealth.forecast_cache_size], ['Observation Cache', feedHealth.observation_cache_size],
                ].map(([label, val]) => (
                  <div key={label} className="flex justify-between">
                    <span className="text-zinc-500">{label}</span>
                    <span className={`font-mono ${String(label).includes('Error') && val ? 'text-red-400' : 'text-zinc-300'}`}>{val ?? '—'}</span>
                  </div>
                ))}
              </div>
            </SectionCard>

            <SectionCard title="CLOB WebSocket" testId="section-clob-ws-health">
              <div className="space-y-2 text-xs">
                <div className="flex justify-between">
                  <span className="text-zinc-500">Status</span>
                  <span className={`font-mono font-medium ${clobHealth.connected ? 'text-emerald-400' : 'text-red-400'}`}>
                    {clobHealth.connected ? 'CONNECTED' : 'DISCONNECTED'}
                  </span>
                </div>
                {[
                  ['Subscribed Tokens', clobHealth.subscribed_tokens],
                  ['Messages Received', clobHealth.messages_received],
                  ['Price Updates', clobHealth.price_updates],
                  ['Book Updates', clobHealth.book_updates],
                  ['Trade Updates', clobHealth.trade_updates],
                  ['Reconnects', clobHealth.reconnect_count],
                  ['Uptime', clobHealth.uptime_seconds != null ? `${Math.floor(clobHealth.uptime_seconds / 60)}m ${Math.floor(clobHealth.uptime_seconds % 60)}s` : null],
                  ['Last Message', clobHealth.last_message_seconds_ago != null ? `${clobHealth.last_message_seconds_ago.toFixed(0)}s ago` : null],
                  ['Errors', clobHealth.errors],
                ].map(([label, val]) => (
                  <div key={label} className="flex justify-between">
                    <span className="text-zinc-500">{label}</span>
                    <span className={`font-mono ${label === 'Errors' && val > 0 ? 'text-red-400' : 'text-zinc-300'}`}>{val ?? '—'}</span>
                  </div>
                ))}
                {clobHealth.last_error && (
                  <div className="pt-2 border-t border-zinc-800">
                    <span className="text-red-400 text-[10px]">{truncate(clobHealth.last_error, 60)}</span>
                  </div>
                )}
              </div>
            </SectionCard>

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

            <SectionCard title="Strategy Config" testId="section-weather-config">
              <div className="space-y-2 text-xs">
                {[
                  ['Scan Interval', `${config.scan_interval}s`], ['Forecast Refresh', `${config.forecast_refresh_interval}s`],
                  ['Min Edge', `${config.min_edge_bps} bps`], ['Min Liquidity', `$${config.min_liquidity}`],
                  ['Min Confidence', config.min_confidence], ['Max Sigma', `${config.max_sigma}F`],
                  ['Min Lead', `${config.min_hours_to_resolution}h`], ['Max Lead', `${config.max_hours_to_resolution}h`],
                  ['Default Size', config.default_size], ['Max Size', config.max_signal_size],
                  ['Kelly Scale', config.kelly_scale], ['Max Concurrent', config.max_concurrent_signals],
                  ['Max Buckets/Market', config.max_buckets_per_market], ['Cooldown', `${config.cooldown_seconds}s`],
                  ['Max Stale Market', `${config.max_stale_market_seconds}s`],
                ].map(([label, val]) => (
                  <div key={label} className="flex justify-between">
                    <span className="text-zinc-500">{label}</span>
                    <span className="text-zinc-300 font-mono">{val ?? '—'}</span>
                  </div>
                ))}
              </div>
            </SectionCard>

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

// ---- Sub-Components for Calibration Tab ----

function ShadowSummarySection({ summary, config, isShadow, execMode }) {
  const ss = summary || {};
  const ops = ss.operational_stats || {};
  return (
    <SectionCard
      title="Shadow-Mode Summary"
      testId="section-shadow-summary"
      action={
        <Badge
          data-testid="shadow-mode-badge"
          variant="outline"
          className={`text-[10px] ${isShadow ? 'border-amber-500/30 text-amber-400' : 'border-zinc-700 text-zinc-500'}`}
        >
          {isShadow ? 'SHADOW ACTIVE' : execMode?.toUpperCase() || 'PAPER'}
        </Badge>
      }
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-xs">
        <div className="space-y-2">
          <div className="text-zinc-500 font-medium mb-2">Shadow Config</div>
          {[
            ['Min Edge', `${ss.config_snapshot?.min_edge_bps ?? config.min_edge_bps ?? '—'} bps`],
            ['Kelly Scale', ss.config_snapshot?.kelly_scale ?? config.kelly_scale ?? '—'],
            ['Max Size', `$${ss.config_snapshot?.max_signal_size ?? config.max_signal_size ?? '—'}`],
            ['Max Concurrent', ss.config_snapshot?.max_concurrent_signals ?? config.max_concurrent_signals ?? '—'],
            ['Max Stale', `${ss.config_snapshot?.max_stale_market_seconds ?? config.max_stale_market_seconds ?? '—'}s`],
            ['Cooldown', `${ss.config_snapshot?.cooldown_seconds ?? config.cooldown_seconds ?? '—'}s`],
          ].map(([label, val]) => (
            <div key={label} className="flex justify-between">
              <span className="text-zinc-500">{label}</span>
              <span className="text-zinc-300 font-mono">{val}</span>
            </div>
          ))}
        </div>
        <div className="space-y-2">
          <div className="text-zinc-500 font-medium mb-2">Operational Stats</div>
          {[
            ['Total Scans', ops.total_scans],
            ['Markets Classified', ops.markets_classified],
            ['Forecasts Fetched', ops.forecasts_fetched],
            ['Signals Generated', ops.signals_generated],
            ['Signals Executed', ops.signals_executed],
            ['Signals Filled', ops.signals_filled],
          ].map(([label, val]) => (
            <div key={label} className="flex justify-between">
              <span className="text-zinc-500">{label}</span>
              <span className="text-zinc-300 font-mono">{val ?? '—'}</span>
            </div>
          ))}
        </div>
      </div>
      {!isShadow && (
        <p className="text-zinc-600 text-xs mt-3 pt-3 border-t border-zinc-800">
          Shadow mode is not active. Switch execution mode to "shadow" in Settings to enable shadow testing.
        </p>
      )}
    </SectionCard>
  );
}

function CalibrationHealthSection({ health }) {
  const cal = health || {};
  const statusColors = {
    no_data: 'text-zinc-500', collecting: 'text-amber-400',
    partial: 'text-blue-400', ready: 'text-emerald-400',
  };

  return (
    <SectionCard title="Calibration Health" testId="section-calibration-health">
      <div className="space-y-2 text-xs">
        <div className="flex justify-between">
          <span className="text-zinc-500">Status</span>
          <span className={`font-mono font-medium ${statusColors[cal.calibration_status] || 'text-zinc-500'}`}>
            {cal.calibration_status?.toUpperCase() || 'NO DATA'}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-zinc-500">Using Defaults</span>
          <span className={`font-mono ${cal.using_defaults ? 'text-amber-400' : 'text-emerald-400'}`}>
            {cal.using_defaults !== undefined ? (cal.using_defaults ? 'Yes' : 'No') : '—'}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-zinc-500">Total Records</span>
          <span className="text-zinc-300 font-mono">{cal.total_records ?? 0}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-zinc-500">Resolved</span>
          <span className="text-zinc-300 font-mono">{cal.resolved_records ?? 0}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-zinc-500">Pending</span>
          <span className="text-zinc-300 font-mono">{cal.pending_resolution ?? 0}</span>
        </div>
        {cal.global_mae_f != null && (
          <div className="flex justify-between">
            <span className="text-zinc-500">Global MAE</span>
            <span className={`font-mono ${cal.global_mae_f > 3 ? 'text-red-400' : cal.global_mae_f > 1.5 ? 'text-amber-400' : 'text-emerald-400'}`}>
              {cal.global_mae_f}F
            </span>
          </div>
        )}
        {cal.global_bias_f != null && (
          <div className="flex justify-between">
            <span className="text-zinc-500">Global Bias</span>
            <span className="text-zinc-300 font-mono">{cal.global_bias_f > 0 ? '+' : ''}{cal.global_bias_f}F</span>
          </div>
        )}
        {cal.calibration_note && (
          <p className="text-zinc-600 pt-2 border-t border-zinc-800">{cal.calibration_note}</p>
        )}
      </div>
    </SectionCard>
  );
}

function StationAccuracySection({ stations }) {
  const entries = Object.values(stations || {});

  return (
    <SectionCard title="Per-Station Accuracy" testId="section-station-accuracy">
      <div className="space-y-3 text-xs">
        {entries.length === 0 ? (
          <p className="text-zinc-600">No resolved forecast data yet. Accuracy will populate as markets resolve.</p>
        ) : (
          entries.map((s) => (
            <div key={s.station_id} className="space-y-1 pb-2 border-b border-zinc-800 last:border-0">
              <div className="flex justify-between items-center">
                <span className="text-cyan-400 font-mono font-medium">{s.station_id}</span>
                <Badge
                  variant="outline"
                  className={`text-[9px] ${s.calibration_meaningful ? 'border-emerald-500/30 text-emerald-400' : 'border-zinc-700 text-zinc-500'}`}
                >
                  {s.sample_count} samples
                </Badge>
              </div>
              {s.mean_abs_error_f != null && (
                <div className="flex justify-between">
                  <span className="text-zinc-500">MAE</span>
                  <span className={`font-mono ${s.mean_abs_error_f > 3 ? 'text-red-400' : s.mean_abs_error_f > 1.5 ? 'text-amber-400' : 'text-emerald-400'}`}>
                    {s.mean_abs_error_f}F
                  </span>
                </div>
              )}
              {s.mean_bias_f != null && (
                <div className="flex justify-between">
                  <span className="text-zinc-500">Bias</span>
                  <span className="text-zinc-300 font-mono">{s.mean_bias_f > 0 ? '+' : ''}{s.mean_bias_f}F</span>
                </div>
              )}
              <p className="text-zinc-600 text-[10px]">{s.calibration_note}</p>
            </div>
          ))
        )}
      </div>
    </SectionCard>
  );
}

function SigmaCalibrationSection({ status, calRunning, onRunCalibration, onReload }) {
  const s = status || {};
  const ready = s.total_stations_calibrated > 0;

  return (
    <SectionCard
      title="Sigma Calibration"
      testId="section-sigma-calibration"
      action={
        <div className="flex gap-2">
          <Button
            data-testid="run-calibration-btn"
            size="sm"
            variant="outline"
            onClick={onRunCalibration}
            disabled={calRunning}
            className="h-6 text-[10px] px-2.5 border-zinc-700"
          >
            {calRunning ? 'Running...' : 'Run Calibration'}
          </Button>
          {ready && (
            <Button
              data-testid="reload-calibration-btn"
              size="sm"
              variant="outline"
              onClick={onReload}
              className="h-6 text-[10px] px-2.5 border-zinc-700"
            >
              Reload
            </Button>
          )}
        </div>
      }
    >
      <div className="space-y-2 text-xs">
        <div className="flex justify-between">
          <span className="text-zinc-500">Stations Calibrated</span>
          <span className={`font-mono ${ready ? 'text-emerald-400' : 'text-zinc-500'}`}>
            {s.total_stations_calibrated ?? 0} / {s.total_stations_registered ?? 8}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-zinc-500">Last Run</span>
          <span className="text-zinc-400 font-mono">{s.last_run ? new Date(s.last_run).toLocaleString() : 'Never'}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-zinc-500">Status</span>
          <Badge
            variant="outline"
            className={`text-[9px] ${
              s.last_status === 'completed' ? 'border-emerald-500/30 text-emerald-400'
              : s.last_status === 'running' ? 'border-amber-500/30 text-amber-400'
              : 'border-zinc-700 text-zinc-500'
            }`}
          >
            {(s.last_status || 'NOT RUN').toUpperCase()}
          </Badge>
        </div>
        {!ready && (
          <p className="text-zinc-600 pt-2 border-t border-zinc-800">
            Click "Run Calibration" to fetch 90 days of historical data from Open-Meteo and compute station-specific sigma values.
          </p>
        )}
      </div>
    </SectionCard>
  );
}

function StationSigmaSection({ status }) {
  const stations = status?.stations || {};
  const entries = Object.values(stations);

  const LEAD_LABELS = {
    '0_24': '0-24h',
    '24_48': '24-48h',
    '48_72': '48-72h',
    '72_120': '72-120h',
    '120_168': '120-168h',
  };

  return (
    <SectionCard title="Calibrated Sigma Values" testId="section-station-sigma">
      <div className="space-y-3 text-xs">
        {entries.length === 0 ? (
          <p className="text-zinc-600">No calibration data. Run calibration to compute station-specific sigma values from historical forecast accuracy.</p>
        ) : (
          entries.map((s) => (
            <div key={s.station_id} className="space-y-1.5 pb-2 border-b border-zinc-800 last:border-0">
              <div className="flex justify-between items-center">
                <span className="text-cyan-400 font-mono font-medium">{s.station_id}</span>
                <div className="flex items-center gap-2">
                  <span className="text-zinc-600 text-[10px]">{s.sample_count} samples</span>
                  <Badge
                    variant="outline"
                    className={`text-[9px] ${s.ready ? 'border-emerald-500/30 text-emerald-400' : 'border-amber-500/30 text-amber-400'}`}
                  >
                    {s.ready ? 'READY' : 'LOW DATA'}
                  </Badge>
                </div>
              </div>
              <div className="grid grid-cols-5 gap-1 text-[10px]">
                {['0_24', '24_48', '48_72', '72_120', '120_168'].map((bracket) => (
                  <div key={bracket} className="text-center">
                    <div className="text-zinc-600">{LEAD_LABELS[bracket]}</div>
                    <div className="text-zinc-300 font-mono">
                      {bracket === '0_24' && s.base_sigma_0_24 != null
                        ? `${s.base_sigma_0_24.toFixed(2)}F`
                        : bracket === '48_72' && s.base_sigma_48_72 != null
                        ? `${s.base_sigma_48_72.toFixed(2)}F`
                        : '—'}
                    </div>
                  </div>
                ))}
              </div>
              {s.mean_bias_f != null && (
                <div className="flex justify-between text-[10px]">
                  <span className="text-zinc-600">Bias</span>
                  <span className={`font-mono ${Math.abs(s.mean_bias_f) > 2 ? 'text-amber-400' : 'text-zinc-400'}`}>
                    {s.mean_bias_f > 0 ? '+' : ''}{s.mean_bias_f.toFixed(2)}F
                  </span>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </SectionCard>
  );
}

