import { useEffect, useMemo, useState, useCallback } from 'react';
import { useDashboardStore } from '../state/dashboardStore';
import { useApi } from '../hooks/useApi';
import { StatCard } from '../components/StatCard';
import { SectionCard } from '../components/SectionCard';
import { DataTable } from '../components/DataTable';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { formatBps, formatPrice, formatPnl, formatNumber, formatTimestamp, formatTimeAgo, truncate } from '../utils/formatters';
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
  const weatherAlerts = useDashboardStore((s) => s.weatherAlerts);
  const demoMode = useDashboardStore((s) => s.demoMode);
  const strategyPositions = useDashboardStore((s) => s.strategyPositions);
  const { fetchWeatherSignals, fetchWeatherExecutions, fetchWeatherHealth, fetchWeatherForecasts, fetchWeatherAlerts, fetchStrategyPositions } = useApi();
  const [tab, setTab] = useState('positions');

  const [shadowSummary, setShadowSummary] = useState(null);
  const [accuracyHistory, setAccuracyHistory] = useState([]);
  const [stationSummary, setStationSummary] = useState({});
  const [calibrationHealth, setCalibrationHealth] = useState(null);
  const [sigmaCalStatus, setSigmaCalStatus] = useState(null);
  const [rollingCalStatus, setRollingCalStatus] = useState(null);
  const [calRunning, setCalRunning] = useState(false);
  const [rollingCalRunning, setRollingCalRunning] = useState(false);
  const [posBreakdown, setPosBreakdown] = useState(null);

  const prefix = demoMode ? '/demo' : '';

  const fetchCalibration = useCallback(async () => {
    if (demoMode) return;
    try {
      const [ss, ah, cal, sigCal, rolCal, bk] = await Promise.all([
        axios.get(`${API_BASE}/strategies/weather/shadow-summary`),
        axios.get(`${API_BASE}/strategies/weather/accuracy/history?limit=50`),
        axios.get(`${API_BASE}/strategies/weather/accuracy/calibration`),
        axios.get(`${API_BASE}/strategies/weather/calibration/status`),
        axios.get(`${API_BASE}/strategies/weather/calibration/rolling/status`),
        axios.get(`${API_BASE}/positions/weather/breakdown`),
      ]);
      setShadowSummary(ss.data);
      setAccuracyHistory(ah.data);
      setCalibrationHealth(cal.data);
      setStationSummary(cal.data?.station_summaries || {});
      setSigmaCalStatus(sigCal.data);
      setRollingCalStatus(rolCal.data);
      setPosBreakdown(bk.data);
    } catch {}
  }, [demoMode]);

  useEffect(() => {
    fetchWeatherSignals();
    fetchWeatherExecutions();
    fetchWeatherHealth();
    fetchWeatherForecasts();
    fetchWeatherAlerts();
    fetchStrategyPositions();
    fetchCalibration();
    const interval = setInterval(() => {
      fetchWeatherSignals();
      fetchWeatherExecutions();
      fetchWeatherHealth();
      fetchWeatherForecasts();
      fetchWeatherAlerts();
      fetchStrategyPositions();
    }, 8000);
    const calInterval = setInterval(fetchCalibration, 30000);
    return () => { clearInterval(interval); clearInterval(calInterval); };
  }, [fetchWeatherSignals, fetchWeatherExecutions, fetchWeatherHealth, fetchWeatherForecasts, fetchWeatherAlerts, fetchStrategyPositions, fetchCalibration]);

  const config = health.config || {};
  const feedHealth = health.feed_health || {};
  const clobHealth = health.clob_ws_health || {};
  const rejReasons = health.rejection_reasons || {};
  const classFailReasons = health.classification_failure_reasons || {};
  const classifications = health.classifications || {};
  const isShadow = health.is_shadow || shadowSummary?.is_shadow;
  const execMode = health.execution_mode || shadowSummary?.execution_mode || 'paper';
  const alertStats = health.alert_stats || {};
  const alerts = weatherAlerts.alerts || [];

  // Strategy-level summary
  const weatherSummary = strategyPositions?.summaries?.weather || {};
  const weatherPositions = strategyPositions?.positions?.weather || [];

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

  // ---- Open Positions Columns ----
  const positionColumns = [
    { key: 'market_question', label: 'Market', render: (v) => <span className="text-zinc-200 max-w-[200px] truncate block">{truncate(v, 50)}</span> },
    { key: 'weather', label: 'City', render: (_, row) => {
      const w = row.weather;
      return w ? <span className="text-cyan-400 font-mono">{w.station_id}</span> : <span className="text-zinc-600">—</span>;
    }},
    { key: 'weather', label: 'Bucket', render: (_, row) => {
      const w = row.weather;
      return w ? <span className="text-zinc-300 font-medium">{w.bucket_label}</span> : <span className="text-zinc-600">—</span>;
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
    { key: 'weather', label: 'Edge@Entry', align: 'right', render: (_, row) => {
      const e = row.weather?.edge_at_entry;
      return e != null ? <span className="font-mono text-amber-400">{formatBps(e)}</span> : <span className="text-zinc-600">—</span>;
    }},
    { key: 'hours_to_resolution', label: 'Resolves', align: 'right', render: (v) => (
      <span className={`font-mono ${v != null && v < 12 ? 'text-amber-400' : 'text-zinc-400'}`}>{v != null ? `${v.toFixed(0)}h` : '—'}</span>
    )},
  ];

  // ---- Signal Columns ----
  const TYPE_BADGE_COLORS = { temperature: 'text-amber-400', precipitation: 'text-blue-400', snowfall: 'text-cyan-300', wind: 'text-teal-400' };
  const signalColumns = [
    { key: 'station_id', label: 'Station', render: (v) => <span className="text-cyan-400 font-medium font-mono">{v}</span> },
    { key: 'target_date', label: 'Date', render: (v) => <span className="text-zinc-300">{v}</span> },
    { key: 'market_type', label: 'Type', render: (v) => (
      <span className={`text-[10px] font-mono uppercase ${TYPE_BADGE_COLORS[v] || 'text-zinc-500'}`}>{v?.slice(0, 5) || 'temp'}</span>
    )},
    { key: 'bucket_label', label: 'Bucket', render: (v) => <span className="text-zinc-200 font-medium">{v}</span> },
    { key: 'forecast_high_f', label: 'Fcst', align: 'right', render: (v) => <span className="font-mono">{v ? `${v}F` : '—'}</span> },
    { key: 'model_prob', label: 'Model', align: 'right', sortable: true, render: (v) => <span className="font-mono">{v > 0 ? formatPrice(v) : '—'}</span> },
    { key: 'market_price', label: 'Mkt', align: 'right', sortable: true, render: (v) => <span className="font-mono">{v > 0 ? formatPrice(v) : '—'}</span> },
    { key: 'edge_bps', label: 'Edge', align: 'right', sortable: true, render: (v) => <span className={v > 0 ? 'text-emerald-400 font-mono' : 'text-zinc-500 font-mono'}>{formatBps(v)}</span> },
    { key: 'confidence', label: 'Conf', align: 'right', sortable: true, render: (v) => (
      <span className={`font-mono ${v >= 0.6 ? 'text-emerald-400' : v >= 0.3 ? 'text-amber-400' : 'text-zinc-500'}`}>{v > 0 ? (v * 100).toFixed(0) + '%' : '—'}</span>
    )},
    { key: 'quality_score', label: 'Quality', align: 'right', sortable: true, render: (v) => (
      <span className={`font-mono font-medium ${v >= 0.5 ? 'text-emerald-400' : v >= 0.25 ? 'text-amber-400' : 'text-zinc-500'}`}>{v > 0 ? v.toFixed(3) : '—'}</span>
    )},
    { key: 'recommended_size', label: 'Size', align: 'right', render: (v) => <span className="font-mono">{v > 0 ? formatNumber(v, 1) : '—'}</span> },
    { key: 'explanation', label: 'Thesis', render: (v) => (
      <span className="text-zinc-500 text-[10px] max-w-[200px] truncate block" title={v?.thesis || ''}>{v?.thesis || '—'}</span>
    )},
  ];

  const rejectedColumns = [
    ...signalColumns.slice(0, 5),
    { key: 'rejection_reason', label: 'Reason', render: (v) => (
      <span className={`text-xs font-medium ${v?.includes('liquidity') ? 'text-orange-400' : v?.includes('edge') ? 'text-amber-400' : v?.includes('confidence') ? 'text-amber-400' : v?.includes('stale') ? 'text-zinc-500' : 'text-red-400'}`}>{v}</span>
    )},
    { key: 'explanation', label: 'Context', render: (v) => (
      <span className="text-zinc-600 text-[10px] max-w-[180px] truncate block" title={v?.forecast_summary || ''}>{v?.forecast_summary || '—'}</span>
    )},
    { key: 'detected_at', label: 'Detected', render: (v) => <span className="text-zinc-600">{formatTimeAgo(v)}</span> },
  ];

  const execColumns = [
    { key: 'station_id', label: 'Station', render: (v) => <span className="text-cyan-400 font-mono">{v}</span> },
    { key: 'bucket_label', label: 'Bucket', render: (v) => <span className="text-zinc-200 font-medium">{v}</span> },
    { key: 'size', label: 'Size', align: 'right', render: (v) => formatNumber(v, 2) },
    { key: 'entry_price', label: 'Fill', align: 'right', render: (v) => v != null ? formatPrice(v) : '—' },
    { key: 'target_edge_bps', label: 'Edge', align: 'right', sortable: true, render: (v) => formatBps(v) },
    { key: 'status', label: 'Status', render: (v) => <span className={`font-medium ${STATUS_COLORS[v] || 'text-zinc-400'}`}>{v}</span> },
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

      {/* Summary Cards - focused on live observability */}
      <div data-testid="weather-stats-grid" className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <StatCard testId="stat-weather-open" label="Open Positions" value={weatherPositions.length}
          sub={weatherSummary.unrealized_pnl != null ? `${formatPnl(weatherSummary.unrealized_pnl)} unrl` : undefined} />
        <StatCard testId="stat-weather-tradable" label="Tradable Signals" value={signals.total_tradable} />
        <StatCard testId="stat-weather-executed" label="Executed" value={health.signals_executed || 0} />
        <StatCard testId="stat-weather-filled" label="Filled" value={health.signals_filled || 0} />
        <StatCard testId="stat-weather-forecasts" label="Forecast Coverage" value={`${health.forecasts_fetched || 0}/${(health.forecasts_fetched || 0) + (health.forecasts_missing || 0)}`} />
        <StatCard testId="stat-weather-scan-ms" label="Scan Latency" value={`${health.last_scan_duration_ms || 0}ms`} />
      </div>

      {/* PnL Summary Bar */}
      <div data-testid="weather-pnl-bar" className="flex items-center gap-6 px-4 py-2.5 bg-zinc-900/60 border border-zinc-800 rounded-lg text-xs">
        <div className="flex items-center gap-2">
          <span className="text-zinc-500">Realized</span>
          <span className={`font-mono font-medium ${(weatherSummary.realized_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {formatPnl(weatherSummary.realized_pnl || 0)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-zinc-500">Unrealized</span>
          <span className={`font-mono font-medium ${(weatherSummary.unrealized_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {formatPnl(weatherSummary.unrealized_pnl || 0)}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-zinc-500">Total</span>
          <span className={`font-mono font-semibold ${(weatherSummary.total_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {formatPnl(weatherSummary.total_pnl || 0)}
          </span>
        </div>
        <div className="ml-auto flex items-center gap-4 text-zinc-500">
          <span>Trades: <span className="text-zinc-300 font-mono">{weatherSummary.trade_count || 0}</span></span>
          <span>W/L: <span className="text-zinc-300 font-mono">{weatherSummary.wins || 0}/{weatherSummary.losses || 0}</span></span>
          {weatherSummary.win_rate > 0 && <span>WR: <span className="text-zinc-300 font-mono">{weatherSummary.win_rate}%</span></span>}
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-zinc-900 border border-zinc-800">
          <TabsTrigger data-testid="tab-positions" value="positions" className="text-xs data-[state=active]:bg-zinc-800">
            Open Positions ({weatherPositions.length})
          </TabsTrigger>
          <TabsTrigger data-testid="tab-signals" value="signals" className="text-xs data-[state=active]:bg-zinc-800">
            Signals ({signals.total_tradable})
          </TabsTrigger>
          <TabsTrigger data-testid="tab-executions" value="executions" className="text-xs data-[state=active]:bg-zinc-800">
            Executions ({allExecs.length})
          </TabsTrigger>
          <TabsTrigger data-testid="tab-rejected" value="rejected" className="text-xs data-[state=active]:bg-zinc-800">
            Rejected ({signals.total_rejected})
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

        {/* Open Positions Tab (PRIMARY) */}
        <TabsContent value="positions" className="mt-4 space-y-5">
          <SectionCard title="Open Weather Positions" testId="section-weather-positions">
            <DataTable columns={positionColumns} data={weatherPositions}
              emptyMessage="No open weather positions — trades will appear here when the strategy executes"
              testId="weather-positions-table" />
          </SectionCard>
          {posBreakdown && <PositionBreakdownSection data={posBreakdown} />}
        </TabsContent>

        {/* Signals Tab */}
        <TabsContent value="signals" className="mt-4 space-y-5">
          {health.best_signal_this_scan && (
            <div data-testid="best-signal-banner" className="px-4 py-3 bg-emerald-950/30 border border-emerald-800/30 rounded-lg">
              <div className="flex items-center gap-3 text-xs">
                <span className="text-emerald-400 font-semibold">BEST SIGNAL</span>
                <span className="text-cyan-400 font-mono">{health.best_signal_this_scan.station}</span>
                <span className="text-zinc-400">{health.best_signal_this_scan.date}</span>
                {health.best_signal_this_scan.market_type && health.best_signal_this_scan.market_type !== 'temperature' && (
                  <span className="text-blue-400 uppercase text-[10px] font-mono">{health.best_signal_this_scan.market_type}</span>
                )}
                <span className="text-zinc-200 font-medium">{health.best_signal_this_scan.bucket}</span>
                <span className="text-emerald-400 font-mono">{health.best_signal_this_scan.edge_bps}bps</span>
                <span className="text-amber-400 font-mono">Q:{health.best_signal_this_scan.quality_score?.toFixed(3)}</span>
                {health.best_signal_this_scan.thesis && (
                  <span className="text-zinc-500 truncate max-w-[300px]" title={health.best_signal_this_scan.thesis}>{health.best_signal_this_scan.thesis}</span>
                )}
              </div>
            </div>
          )}
          <SectionCard testId="section-weather-signals">
            <DataTable columns={signalColumns} data={signals.tradable || []}
              emptyMessage="No tradable weather signals — start engine & wait for weather markets" testId="weather-signals-table" />
          </SectionCard>
        </TabsContent>

        {/* Executions Tab */}
        <TabsContent value="executions" className="mt-4">
          <SectionCard testId="section-weather-executions">
            <DataTable columns={execColumns} data={allExecs}
              emptyMessage="No weather executions yet" testId="weather-exec-table" />
          </SectionCard>
        </TabsContent>

        {/* Rejected Tab */}
        <TabsContent value="rejected" className="mt-4">
          <SectionCard testId="section-weather-rejected">
            <DataTable columns={rejectedColumns} data={signals.rejected || []}
              emptyMessage="No rejected signals" testId="weather-rejected-table" />
          </SectionCard>
        </TabsContent>

        {/* Forecasts Tab */}
        <TabsContent value="forecasts" className="mt-4">
          <SectionCard testId="section-weather-forecasts">
            <DataTable columns={forecastColumns} data={forecastRows}
              emptyMessage="No forecasts cached" testId="weather-forecasts-table" />
          </SectionCard>
        </TabsContent>

        {/* Calibration Tab */}
        <TabsContent value="calibration" className="mt-4">
          <div className="space-y-5">
            <ShadowSummarySection summary={shadowSummary} config={config} isShadow={isShadow} execMode={execMode} />
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <CalibrationHealthSection health={calibrationHealth} />
              <SigmaCalibrationSection
                status={sigmaCalStatus}
                calRunning={calRunning}
                onRunCalibration={async () => {
                  setCalRunning(true);
                  try { await axios.post(`${API_BASE}/strategies/weather/calibration/run`); await fetchCalibration(); } catch {}
                  setCalRunning(false);
                }}
                onReload={async () => {
                  try { await axios.post(`${API_BASE}/strategies/weather/calibration/reload`); fetchWeatherHealth(); } catch {}
                }}
              />
            </div>
            <RollingCalibrationSection
              status={rollingCalStatus}
              running={rollingCalRunning}
              onRun={async () => {
                setRollingCalRunning(true);
                try { await axios.post(`${API_BASE}/strategies/weather/calibration/rolling/run`); await fetchCalibration(); fetchWeatherHealth(); } catch {}
                setRollingCalRunning(false);
              }}
              onReload={async () => {
                try { await axios.post(`${API_BASE}/strategies/weather/calibration/rolling/reload`); fetchWeatherHealth(); } catch {}
              }}
            />
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <StationAccuracySection stations={stationSummary} />
              <StationSigmaSection status={sigmaCalStatus} />
            </div>
            <SectionCard title="Forecast Accuracy Log" testId="section-accuracy-log">
              <DataTable columns={accuracyColumns} data={accuracyHistory}
                emptyMessage="No forecast accuracy records yet" testId="accuracy-log-table" />
            </SectionCard>
          </div>
        </TabsContent>

        {/* Health Tab */}
        <TabsContent value="health" className="mt-4">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            <CalibrationStatusCard calStatus={health.calibration_status || {}} />
            <SectionCard title="By Market Type" testId="section-market-type-breakdown">
              <div className="space-y-3 text-xs">
                {Object.entries(health.by_market_type || {}).map(([type, stats]) => {
                  const colors = { temperature: 'text-amber-400', precipitation: 'text-blue-400', snowfall: 'text-cyan-300', wind: 'text-teal-400' };
                  return (
                    <div key={type} className="space-y-1">
                      <div className={`font-mono font-medium uppercase ${colors[type] || 'text-zinc-400'}`}>{type}</div>
                      <div className="flex justify-between"><span className="text-zinc-500">Classified</span><span className="text-zinc-300 font-mono">{stats?.classified || 0}</span></div>
                      <div className="flex justify-between"><span className="text-zinc-500">Signals</span><span className="text-zinc-300 font-mono">{stats?.signals || 0}</span></div>
                      <div className="flex justify-between"><span className="text-zinc-500">Rejected</span><span className="text-zinc-300 font-mono">{stats?.rejected || 0}</span></div>
                    </div>
                  );
                })}
              </div>
            </SectionCard>
            <SectionCard title="Scanner Metrics" testId="section-weather-metrics">
              <div className="space-y-2 text-xs">
                {[
                  ['Total Scans', health.total_scans], ['Scan Duration', `${health.last_scan_duration_ms || 0}ms`],
                  ['Markets Classified', health.markets_classified || health.classified_markets],
                  ['Forecasts Fetched', health.forecasts_fetched], ['Forecasts Missing', health.forecasts_missing],
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
            <SectionCard title="Feed Health" testId="section-weather-feed-health">
              <div className="space-y-2 text-xs">
                {[
                  ['Open-Meteo Errors', feedHealth.open_meteo_errors],
                  ['NWS Errors', feedHealth.nws_errors],
                  ['Forecast Cache', feedHealth.forecast_cache_size],
                ].map(([label, val]) => (
                  <div key={label} className="flex justify-between">
                    <span className="text-zinc-500">{label}</span>
                    <span className={`font-mono ${String(label).includes('Error') && val ? 'text-red-400' : 'text-zinc-300'}`}>{val ?? '—'}</span>
                  </div>
                ))}
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
                  ['Scan Interval', `${config.scan_interval}s`], ['Min Edge', `${config.min_edge_bps} bps`],
                  ['Min Liquidity', `$${config.min_liquidity}`], ['Min Confidence', config.min_confidence],
                  ['Max Sigma', `${config.max_sigma}F`], ['Default Size', config.default_size],
                  ['Kelly Scale', config.kelly_scale], ['Max Concurrent', config.max_concurrent_signals],
                  ['Max Positions', config.max_weather_positions],
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

// ---- Sub-Components (Calibration) ----

function ShadowSummarySection({ summary, config, isShadow, execMode }) {
  const ss = summary || {};
  const ops = ss.operational_stats || {};
  return (
    <SectionCard title="Shadow-Mode Summary" testId="section-shadow-summary"
      action={<Badge data-testid="shadow-mode-badge" variant="outline" className={`text-[10px] ${isShadow ? 'border-amber-500/30 text-amber-400' : 'border-zinc-700 text-zinc-500'}`}>{isShadow ? 'SHADOW ACTIVE' : execMode?.toUpperCase() || 'PAPER'}</Badge>}>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 text-xs">
        <div className="space-y-2">
          <div className="text-zinc-500 font-medium mb-2">Shadow Config</div>
          {[['Min Edge', `${ss.config_snapshot?.min_edge_bps ?? config.min_edge_bps ?? '—'} bps`], ['Kelly Scale', ss.config_snapshot?.kelly_scale ?? config.kelly_scale ?? '—'], ['Max Size', `$${ss.config_snapshot?.max_signal_size ?? config.max_signal_size ?? '—'}`]].map(([l, v]) => (
            <div key={l} className="flex justify-between"><span className="text-zinc-500">{l}</span><span className="text-zinc-300 font-mono">{v}</span></div>
          ))}
        </div>
        <div className="space-y-2">
          <div className="text-zinc-500 font-medium mb-2">Operational Stats</div>
          {[['Total Scans', ops.total_scans], ['Signals Generated', ops.signals_generated], ['Signals Filled', ops.signals_filled]].map(([l, v]) => (
            <div key={l} className="flex justify-between"><span className="text-zinc-500">{l}</span><span className="text-zinc-300 font-mono">{v ?? '—'}</span></div>
          ))}
        </div>
      </div>
    </SectionCard>
  );
}

function CalibrationHealthSection({ health }) {
  const cal = health || {};
  return (
    <SectionCard title="Calibration Health" testId="section-calibration-health">
      <div className="space-y-2 text-xs">
        {[['Status', cal.calibration_status?.toUpperCase() || 'NO DATA'], ['Total Records', cal.total_records ?? 0], ['Resolved', cal.resolved_records ?? 0], ['Pending', cal.pending_resolution ?? 0]].map(([l, v]) => (
          <div key={l} className="flex justify-between"><span className="text-zinc-500">{l}</span><span className="text-zinc-300 font-mono">{v}</span></div>
        ))}
        {cal.global_mae_f != null && <div className="flex justify-between"><span className="text-zinc-500">Global MAE</span><span className={`font-mono ${cal.global_mae_f > 3 ? 'text-red-400' : 'text-emerald-400'}`}>{cal.global_mae_f}F</span></div>}
      </div>
    </SectionCard>
  );
}

function StationAccuracySection({ stations }) {
  const entries = Object.values(stations || {});
  return (
    <SectionCard title="Per-Station Accuracy" testId="section-station-accuracy">
      <div className="space-y-3 text-xs">
        {entries.length === 0 ? <p className="text-zinc-600">No resolved forecast data yet.</p> : entries.map((s) => (
          <div key={s.station_id} className="space-y-1 pb-2 border-b border-zinc-800 last:border-0">
            <div className="flex justify-between items-center">
              <span className="text-cyan-400 font-mono font-medium">{s.station_id}</span>
              <Badge variant="outline" className={`text-[9px] ${s.calibration_meaningful ? 'border-emerald-500/30 text-emerald-400' : 'border-zinc-700 text-zinc-500'}`}>{s.sample_count} samples</Badge>
            </div>
            {s.mean_abs_error_f != null && <div className="flex justify-between"><span className="text-zinc-500">MAE</span><span className={`font-mono ${s.mean_abs_error_f > 3 ? 'text-red-400' : 'text-emerald-400'}`}>{s.mean_abs_error_f}F</span></div>}
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

function SigmaCalibrationSection({ status, calRunning, onRunCalibration, onReload }) {
  const s = status || {};
  return (
    <SectionCard title="Sigma Calibration" testId="section-sigma-calibration"
      action={<div className="flex gap-2"><Button data-testid="run-calibration-btn" size="sm" variant="outline" onClick={onRunCalibration} disabled={calRunning} className="h-6 text-[10px] px-2.5 border-zinc-700">{calRunning ? 'Running...' : 'Run Calibration'}</Button>{s.total_stations_calibrated > 0 && <Button data-testid="reload-calibration-btn" size="sm" variant="outline" onClick={onReload} className="h-6 text-[10px] px-2.5 border-zinc-700">Reload</Button>}</div>}>
      <div className="space-y-2 text-xs">
        <div className="flex justify-between"><span className="text-zinc-500">Stations Calibrated</span><span className="text-zinc-300 font-mono">{s.total_stations_calibrated ?? 0} / {s.total_stations_registered ?? 8}</span></div>
        <div className="flex justify-between"><span className="text-zinc-500">Last Run</span><span className="text-zinc-400 font-mono">{s.last_run ? new Date(s.last_run).toLocaleString() : 'Never'}</span></div>
      </div>
    </SectionCard>
  );
}

function StationSigmaSection({ status }) {
  const entries = Object.values(status?.stations || {});
  return (
    <SectionCard title="Calibrated Sigma Values" testId="section-station-sigma">
      <div className="space-y-3 text-xs">
        {entries.length === 0 ? <p className="text-zinc-600">Run calibration to compute station-specific sigma values.</p> : entries.map((s) => (
          <div key={s.station_id} className="flex justify-between items-center pb-1 border-b border-zinc-800 last:border-0">
            <span className="text-cyan-400 font-mono">{s.station_id}</span>
            <span className="text-zinc-500 text-[10px]">{s.sample_count} samples</span>
            <Badge variant="outline" className={`text-[9px] ${s.ready ? 'border-emerald-500/30 text-emerald-400' : 'border-amber-500/30 text-amber-400'}`}>{s.ready ? 'READY' : 'LOW DATA'}</Badge>
          </div>
        ))}
      </div>
    </SectionCard>
  );
}

function CalibrationStatusCard({ calStatus }) {
  const source = calStatus.calibration_source || 'default_sigma_table';
  const SOURCE_STYLES = { rolling_live: { label: 'ROLLING LIVE', color: 'text-emerald-400' }, historical_bootstrap: { label: 'HISTORICAL', color: 'text-amber-400' }, default_sigma_table: { label: 'DEFAULT', color: 'text-zinc-500' } };
  const style = SOURCE_STYLES[source] || SOURCE_STYLES.default_sigma_table;
  return (
    <SectionCard title="Calibration Source" testId="section-weather-calibration">
      <div className="space-y-2 text-xs">
        <div className="flex justify-between items-center"><span className="text-zinc-500">Active Source</span><Badge data-testid="calibration-source-badge" variant="outline" className={`text-[9px] ${style.color}`}>{style.label}</Badge></div>
        <div className="flex justify-between"><span className="text-zinc-500">Calibrated</span><span className="text-zinc-300 font-mono">{calStatus.calibrated_stations?.length || 0} / {calStatus.total_stations || 0}</span></div>
      </div>
    </SectionCard>
  );
}

function RollingCalibrationSection({ status, running, onRun, onReload }) {
  if (!status) return null;
  const stationList = Object.values(status.stations || {});
  return (
    <SectionCard title="Rolling Live Calibration" testId="section-rolling-calibration"
      action={<div className="flex gap-2"><Button data-testid="run-rolling-calibration-btn" size="sm" variant="outline" disabled={running} onClick={onRun} className="h-6 text-[10px] px-3 border-zinc-700">{running ? 'Running...' : 'Run Now'}</Button><Button data-testid="reload-rolling-calibration-btn" size="sm" variant="outline" onClick={onReload} className="h-6 text-[10px] px-3 border-zinc-700">Reload</Button></div>}>
      <div className="space-y-3 text-xs">
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-zinc-500">
          <span>Enabled: <span className={`font-mono ${status.enabled ? 'text-emerald-400' : 'text-zinc-500'}`}>{status.enabled ? 'YES' : 'NO'}</span></span>
          <span>Resolved: <span className="text-zinc-300 font-mono">{status.total_resolved_records || 0}</span></span>
          <span>Calibrated: <span className="text-zinc-300 font-mono">{status.total_stations_calibrated || 0}</span></span>
        </div>
        {stationList.length > 0 ? stationList.map((s) => (
          <div key={s.station_id} className="border border-zinc-800 rounded-md px-3 py-2">
            <div className="flex items-center justify-between">
              <span className="text-cyan-400 font-mono font-medium">{s.station_id}</span>
              <Badge variant="outline" className={`text-[9px] ${s.sufficient ? 'border-emerald-500/30 text-emerald-400' : 'border-zinc-700 text-zinc-500'}`}>{s.sufficient ? 'SUFFICIENT' : 'SPARSE'}</Badge>
            </div>
            <div className="flex flex-wrap gap-x-4 text-[10px] text-zinc-500 mt-1">
              <span>Bias: <span className="font-mono">{s.mean_bias_f > 0 ? '+' : ''}{s.mean_bias_f?.toFixed(2)}F</span></span>
              <span>Samples: <span className="font-mono">{s.sample_count}</span></span>
            </div>
          </div>
        )) : <p className="text-zinc-600">No rolling calibrations computed yet.</p>}
      </div>
    </SectionCard>
  );
}


function PositionBreakdownSection({ data }) {
  const bd = data || {};
  const resolutionEntries = Object.entries(bd.by_resolution_date || {});
  const staleCount = bd.stale_positions || 0;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
      {/* Resolution Date Breakdown */}
      <SectionCard title="By Resolution Date" testId="section-resolution-breakdown">
        <div className="space-y-2 text-xs">
          {resolutionEntries.length === 0 ? (
            <p className="text-zinc-600">No resolution data</p>
          ) : resolutionEntries.map(([date, info]) => (
            <div key={date} className="flex justify-between items-center">
              <span className={`font-mono ${date === 'unknown' ? 'text-zinc-600' : 'text-zinc-300'}`}>{date}</span>
              <div className="flex items-center gap-3">
                <span className="text-zinc-400">{info.count} pos</span>
                <span className="text-zinc-500">${info.capital}</span>
                <span className={`font-mono ${info.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {info.unrealized_pnl >= 0 ? '+' : ''}{info.unrealized_pnl?.toFixed(2)}
                </span>
              </div>
            </div>
          ))}
          {staleCount > 0 && (
            <div className="pt-2 border-t border-zinc-800">
              <span className="text-red-400 font-medium">{staleCount} stale positions</span>
              <span className="text-zinc-600 ml-2">(past resolution)</span>
            </div>
          )}
        </div>
      </SectionCard>

      {/* Biggest Winners */}
      <SectionCard title="Biggest Winners" testId="section-biggest-winners">
        <div className="space-y-2 text-xs">
          {(bd.biggest_winners || []).length === 0 ? (
            <p className="text-zinc-600">No open positions</p>
          ) : (bd.biggest_winners || []).map((p, i) => (
            <div key={i} className="flex justify-between items-center">
              <span className="text-zinc-300 truncate max-w-[150px]">{p.city || p.market_question?.substring(0, 30)}</span>
              <div className="flex items-center gap-2">
                <span className="text-zinc-500 font-mono">{p.size?.toFixed(1)}</span>
                <span className={`font-mono font-medium ${p.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {p.unrealized_pnl >= 0 ? '+' : ''}{p.unrealized_pnl?.toFixed(3)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </SectionCard>

      {/* Oldest Open / Biggest Losers */}
      <SectionCard title="Oldest Open" testId="section-oldest-open">
        <div className="space-y-2 text-xs">
          {(bd.oldest_open || []).length === 0 ? (
            <p className="text-zinc-600">No open positions</p>
          ) : (bd.oldest_open || []).map((p, i) => (
            <div key={i} className="flex justify-between items-center">
              <span className="text-zinc-300 truncate max-w-[120px]">{p.city || p.market_question?.substring(0, 25)}</span>
              <div className="flex items-center gap-2">
                <span className="text-amber-400 font-mono">{p.hours_open != null ? `${p.hours_open.toFixed(0)}h` : '—'}</span>
                <span className="text-zinc-500 font-mono">{p.hours_to_resolution != null ? `→${p.hours_to_resolution.toFixed(0)}h` : ''}</span>
                <span className={`font-mono ${p.unrealized_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {p.unrealized_pnl >= 0 ? '+' : ''}{p.unrealized_pnl?.toFixed(3)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}
