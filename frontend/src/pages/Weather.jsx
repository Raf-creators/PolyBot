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
  const [asymSummary, setAsymSummary] = useState(null);
  const [calMetrics, setCalMetrics] = useState(null);
  const [weatherByType, setWeatherByType] = useState(null);
  const [autoTune, setAutoTune] = useState(null);

  const prefix = demoMode ? '/demo' : '';

  const fetchCalibration = useCallback(async () => {
    if (demoMode) return;
    try {
      const [ss, ah, cal, sigCal, rolCal, bk, asym, cm, wbt, at] = await Promise.all([
        axios.get(`${API_BASE}/strategies/weather/shadow-summary`),
        axios.get(`${API_BASE}/strategies/weather/accuracy/history?limit=50`),
        axios.get(`${API_BASE}/strategies/weather/accuracy/calibration`),
        axios.get(`${API_BASE}/strategies/weather/calibration/status`),
        axios.get(`${API_BASE}/strategies/weather/calibration/rolling/status`),
        axios.get(`${API_BASE}/positions/weather/breakdown`),
        axios.get(`${API_BASE}/strategies/weather-asymmetric/summary`),
        axios.get(`${API_BASE}/strategies/weather/calibration/metrics`),
        axios.get(`${API_BASE}/analytics/weather-by-type`),
        axios.get(`${API_BASE}/strategies/weather/calibration/auto-tune`),
      ]);
      setShadowSummary(ss.data);
      setAccuracyHistory(ah.data);
      setCalibrationHealth(cal.data);
      setStationSummary(cal.data?.station_summaries || {});
      setSigmaCalStatus(sigCal.data);
      setRollingCalStatus(rolCal.data);
      setPosBreakdown(bk.data);
      setAsymSummary(asym.data);
      setCalMetrics(cm.data);
      setWeatherByType(wbt.data);
      setAutoTune(at.data);
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
  const sigmaPipeline = health.sigma_pipeline || {};

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

  // ---- Time helpers ----
  const formatTimeLeft = (seconds) => {
    if (seconds == null) return '—';
    if (seconds <= 0) return 'Resolved';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h >= 48) return `${Math.floor(h / 24)}d ${h % 24}h`;
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
  };
  const formatTimeHeld = (seconds) => {
    if (seconds == null) return '—';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    if (h >= 48) return `${Math.floor(h / 24)}d ${h % 24}h`;
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m`;
  };
  const formatResolvesAt = (isoStr) => {
    if (!isoStr) return '—';
    try {
      const d = new Date(isoStr);
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) +
        ', ' + d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' }) + ' UTC';
    } catch { return '—'; }
  };

  const resCatColors = { near: 'text-red-400', medium: 'text-amber-400', long: 'text-zinc-400', resolved: 'text-emerald-400' };
  const resCatLabels = { near: '<6h', medium: '6-24h', long: '>24h' };

  // ---- Resolution filter ----
  const [resFilter, setResFilter] = useState('all'); // all | near | medium | long
  const [posSort, setPosSort] = useState('time_left_asc'); // time_left_asc | time_held_desc | pnl_desc

  // ---- Open Positions Columns ----
  const positionColumns = [
    { key: 'market_question', label: 'Market', render: (v) => <span className="text-zinc-200 max-w-[180px] truncate block">{truncate(v, 45)}</span> },
    { key: 'weather_city', label: 'City', render: (_, row) => {
      const w = row.weather;
      return w ? <span className="text-cyan-400 font-mono">{w.station_id}</span> : <span className="text-zinc-600">—</span>;
    }},
    { key: 'weather_bucket', label: 'Bucket', render: (_, row) => {
      const w = row.weather;
      return w ? <span className="text-zinc-300 font-medium">{w.bucket_label}</span> : <span className="text-zinc-600">—</span>;
    }},
    { key: 'avg_cost', label: 'Entry', align: 'right', render: (v) => <span className="font-mono">{formatPrice(v)}</span> },
    { key: 'current_price', label: 'Mark', align: 'right', render: (v) => <span className="font-mono text-zinc-200">{formatPrice(v)}</span> },
    { key: 'size', label: 'Size', align: 'right', render: (v) => <span className="font-mono">{formatNumber(v, 2)}</span> },
    { key: 'unrealized_pnl', label: 'P&L', align: 'right', sortable: true, render: (v) => (
      <span className={`font-mono font-medium ${v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-zinc-500'}`}>{formatPnl(v)}</span>
    )},
    { key: 'resolves_at', label: 'Resolves', align: 'right', render: (v) => (
      <span className="text-zinc-300 text-[10px] font-mono">{formatResolvesAt(v)}</span>
    )},
    { key: 'time_to_resolution_seconds', label: 'Time Left', align: 'right', sortable: true, render: (v, row) => {
      const cat = row?.resolution_category;
      return (
        <span className={`font-mono font-medium ${resCatColors[cat] || 'text-zinc-500'}`}>
          {formatTimeLeft(v)}
        </span>
      );
    }},
    { key: 'time_open_seconds', label: 'Held', align: 'right', render: (v) => (
      <span className="text-zinc-400 font-mono">{formatTimeHeld(v)}</span>
    )},
    { key: 'resolution_category', label: '', render: (v) => {
      if (!v || v === 'resolved') return null;
      const colors = { near: 'border-red-500/30 text-red-400', medium: 'border-amber-500/30 text-amber-400', long: 'border-zinc-700 text-zinc-500' };
      return <Badge variant="outline" className={`text-[8px] ${colors[v] || ''}`}>{resCatLabels[v] || v}</Badge>;
    }},
  ];

  // ---- Filtered & sorted positions ----
  const filteredPositions = useMemo(() => {
    let positions = [...weatherPositions];

    // Filter by resolution category
    if (resFilter !== 'all') {
      positions = positions.filter(p => p.resolution_category === resFilter);
    }

    // Sort
    positions.sort((a, b) => {
      if (posSort === 'time_left_asc') {
        const aT = a.time_to_resolution_seconds ?? Infinity;
        const bT = b.time_to_resolution_seconds ?? Infinity;
        return aT - bT;
      }
      if (posSort === 'time_held_desc') {
        const aT = a.time_open_seconds ?? 0;
        const bT = b.time_open_seconds ?? 0;
        return bT - aT;
      }
      if (posSort === 'pnl_desc') {
        return (b.unrealized_pnl ?? 0) - (a.unrealized_pnl ?? 0);
      }
      return 0;
    });

    return positions;
  }, [weatherPositions, resFilter, posSort]);

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
          <TabsTrigger data-testid="tab-asymmetric" value="asymmetric" className="text-xs data-[state=active]:bg-rose-900/40">
            Asymmetric
          </TabsTrigger>
          <TabsTrigger data-testid="tab-market-types" value="market-types" className="text-xs data-[state=active]:bg-zinc-800">
            By Type
          </TabsTrigger>
          <TabsTrigger data-testid="tab-health" value="health" className="text-xs data-[state=active]:bg-zinc-800">
            Health
          </TabsTrigger>
        </TabsList>

        {/* Open Positions Tab (PRIMARY) */}
        <TabsContent value="positions" className="mt-4 space-y-5">
          <SectionCard title="Open Weather Positions" testId="section-weather-positions">
            {/* Filter & Sort Controls */}
            <div data-testid="position-controls" className="flex items-center gap-3 mb-3 flex-wrap">
              <div className="flex items-center gap-1.5 text-xs">
                <span className="text-zinc-500">Resolution:</span>
                {['all', 'near', 'medium', 'long'].map(f => (
                  <button key={f} data-testid={`filter-${f}`}
                    onClick={() => setResFilter(f)}
                    className={`px-2 py-0.5 rounded text-[10px] font-mono transition-colors ${
                      resFilter === f
                        ? 'bg-zinc-700 text-zinc-100'
                        : 'bg-zinc-900 text-zinc-500 hover:text-zinc-300'
                    }`}>
                    {f === 'all' ? 'All' : f === 'near' ? '<6h' : f === 'medium' ? '6–24h' : '>24h'}
                  </button>
                ))}
              </div>
              <div className="flex items-center gap-1.5 text-xs">
                <span className="text-zinc-500">Sort:</span>
                {[
                  { key: 'time_left_asc', label: 'Resolves soonest' },
                  { key: 'time_held_desc', label: 'Held longest' },
                  { key: 'pnl_desc', label: 'Best P&L' },
                ].map(s => (
                  <button key={s.key} data-testid={`sort-${s.key}`}
                    onClick={() => setPosSort(s.key)}
                    className={`px-2 py-0.5 rounded text-[10px] font-mono transition-colors ${
                      posSort === s.key
                        ? 'bg-zinc-700 text-zinc-100'
                        : 'bg-zinc-900 text-zinc-500 hover:text-zinc-300'
                    }`}>
                    {s.label}
                  </button>
                ))}
              </div>
            </div>
            <DataTable columns={positionColumns} data={filteredPositions}
              emptyMessage={resFilter !== 'all'
                ? `No ${resFilter === 'near' ? '<6h' : resFilter === 'medium' ? '6–24h' : '>24h'} positions`
                : "No open weather positions — trades will appear here when the strategy executes"}
              testId="weather-positions-table" />
            {/* Summary below table */}
            {weatherPositions.length > 0 && (
              <div className="flex gap-4 text-[10px] text-zinc-600 mt-2 pt-2 border-t border-zinc-800/50">
                <span>{weatherPositions.filter(p => p.resolution_category === 'near').length} near ({'<'}6h)</span>
                <span>{weatherPositions.filter(p => p.resolution_category === 'medium').length} medium (6-24h)</span>
                <span>{weatherPositions.filter(p => p.resolution_category === 'long').length} long ({'>'}24h)</span>
                <span>{weatherPositions.filter(p => !p.resolution_category).length} unknown</span>
              </div>
            )}
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
            {/* Sigma Pipeline Status */}
            <SigmaPipelineSection pipeline={sigmaPipeline} calMetrics={calMetrics} autoTune={autoTune} />
            <CalibrationMetricsSection metrics={calMetrics} />
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

        {/* Asymmetric Mode Tab */}
        <TabsContent value="asymmetric" className="mt-4 space-y-5">
          <AsymmetricSection data={asymSummary} asymMetrics={health.asymmetric} bestAsymSignal={health.asymmetric?.best_signal_this_scan} />
        </TabsContent>

        {/* Market Types Tab */}
        <TabsContent value="market-types" className="mt-4 space-y-5">
          <WeatherByTypeSection data={weatherByType} />
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


function AsymmetricSection({ data, asymMetrics, bestAsymSignal }) {
  const d = data || {};
  const positions = d.open_positions || [];
  const config = d.config || {};
  const metrics = asymMetrics || d.metrics || {};

  const posColumns = [
    { key: 'market_question', label: 'Market', render: (v) => <span className="text-zinc-200 max-w-[180px] truncate block">{truncate(v, 45)}</span> },
    { key: 'outcome', label: 'Outcome', render: (v) => <span className="text-zinc-300 font-medium">{v}</span> },
    { key: 'avg_cost', label: 'Entry', align: 'right', render: (v) => <span className="font-mono text-rose-300">{formatPrice(v)}</span> },
    { key: 'current_price', label: 'Mark', align: 'right', render: (v) => <span className="font-mono text-zinc-200">{v != null ? formatPrice(v) : '—'}</span> },
    { key: 'size', label: 'Size', align: 'right', render: (v) => <span className="font-mono">{formatNumber(v, 2)}</span> },
    { key: 'risk', label: 'Risk', align: 'right', render: (v) => <span className="font-mono text-red-400">${v?.toFixed(2)}</span> },
    { key: 'max_reward', label: 'Max Reward', align: 'right', render: (v) => <span className="font-mono text-emerald-400">${v?.toFixed(2)}</span> },
    { key: 'expected_payoff_pct', label: 'Payoff', align: 'right', render: (v) => <span className="font-mono text-rose-300">{v}%</span> },
    { key: 'unrealized_pnl', label: 'Unrl P&L', align: 'right', render: (v) => (
      <span className={`font-mono font-medium ${v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-zinc-500'}`}>{formatPnl(v)}</span>
    )},
  ];

  return (
    <div className="space-y-5">
      {/* Asymmetric Summary */}
      <div data-testid="asymmetric-summary" className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <StatCard testId="stat-asym-positions" label="Open Positions" value={d.position_count || 0} />
        <StatCard testId="stat-asym-realized" label="Realized PnL" value={formatPnl(d.realized_pnl || 0)} />
        <StatCard testId="stat-asym-unrealized" label="Unrealized PnL" value={formatPnl(d.unrealized_pnl || 0)} />
        <StatCard testId="stat-asym-signals" label="Signals Generated" value={metrics.signals_generated || 0} />
        <StatCard testId="stat-asym-executed" label="Executed" value={metrics.signals_executed || 0} />
        <StatCard testId="stat-asym-winrate" label="Win Rate" value={d.win_rate != null ? `${d.win_rate}%` : '—'} />
      </div>

      {/* Config */}
      <SectionCard title="Asymmetric Mode Configuration" testId="section-asym-config">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
          <div>
            <span className="text-zinc-500 block">Status</span>
            <Badge variant="outline" className={`text-[10px] mt-1 ${config.enabled ? 'border-emerald-500/30 text-emerald-400' : 'border-red-500/30 text-red-400'}`}>
              {config.enabled ? 'ENABLED' : 'DISABLED'}
            </Badge>
          </div>
          <div>
            <span className="text-zinc-500 block">Max Price</span>
            <span className="text-rose-300 font-mono">{config.max_market_price ? `${(config.max_market_price * 100).toFixed(0)}¢` : '—'}</span>
          </div>
          <div>
            <span className="text-zinc-500 block">Min Model Prob</span>
            <span className="text-zinc-300 font-mono">{config.min_model_prob ? `${(config.min_model_prob * 100).toFixed(0)}%` : '—'}</span>
          </div>
          <div>
            <span className="text-zinc-500 block">Min Edge</span>
            <span className="text-zinc-300 font-mono">{config.min_edge ? `${(config.min_edge * 100).toFixed(0)}%` : '—'}</span>
          </div>
          <div>
            <span className="text-zinc-500 block">Default Size</span>
            <span className="text-zinc-300 font-mono">${config.default_size || '—'}</span>
          </div>
          <div>
            <span className="text-zinc-500 block">Max Positions</span>
            <span className="text-zinc-300 font-mono">{config.max_positions || '—'}</span>
          </div>
        </div>
        <div className="mt-3 text-[10px] text-zinc-600">
          Targets contracts priced ≤ {config.max_market_price ? `${(config.max_market_price * 100).toFixed(0)}¢` : '25¢'} where the model sees ≥ {config.min_model_prob ? `${(config.min_model_prob * 100).toFixed(0)}%` : '40%'} probability. Holds to resolution for maximum asymmetric payoff.
        </div>
      </SectionCard>

      {/* Best Asymmetric Signal */}
      {bestAsymSignal && (
        <div data-testid="best-asym-signal" className="px-4 py-3 bg-rose-950/30 border border-rose-800/30 rounded-lg">
          <div className="flex items-center gap-3 text-xs flex-wrap">
            <span className="text-rose-400 font-semibold">BEST ASYMMETRIC</span>
            <span className="text-cyan-400 font-mono">{bestAsymSignal.station}</span>
            <span className="text-zinc-400">{bestAsymSignal.date}</span>
            <span className="text-zinc-200 font-medium">{bestAsymSignal.bucket}</span>
            <span className="text-rose-300 font-mono">Price: {formatPrice(bestAsymSignal.market_price)}</span>
            <span className="text-emerald-400 font-mono">Model: {(bestAsymSignal.model_prob * 100).toFixed(0)}%</span>
            <span className="text-amber-400 font-mono">Edge: {(bestAsymSignal.edge * 100).toFixed(0)}%</span>
            <span className="text-emerald-400 font-mono">Payoff: +{bestAsymSignal.expected_payoff}%</span>
          </div>
          {bestAsymSignal.thesis && (
            <div className="text-zinc-500 text-[10px] mt-1">{bestAsymSignal.thesis}</div>
          )}
        </div>
      )}

      {/* Open Asymmetric Positions */}
      <SectionCard title="Open Asymmetric Positions" testId="section-asym-positions">
        <DataTable columns={posColumns} data={positions}
          emptyMessage="No open asymmetric positions — waiting for low-priced, high-conviction signals"
          testId="asym-positions-table" />
      </SectionCard>

      {/* PnL Summary + Expected Value */}
      <SectionCard title="Asymmetric Performance" testId="section-asym-perf">
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4 text-xs">
          <div>
            <span className="text-zinc-500 block">Realized PnL</span>
            <span className={`font-mono font-medium ${(d.realized_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {formatPnl(d.realized_pnl || 0)}
            </span>
          </div>
          <div>
            <span className="text-zinc-500 block">Unrealized PnL</span>
            <span className={`font-mono font-medium ${(d.unrealized_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {formatPnl(d.unrealized_pnl || 0)}
            </span>
          </div>
          <div>
            <span className="text-zinc-500 block">Win / Loss</span>
            <span className="text-zinc-300 font-mono">{d.wins || 0} / {d.losses || 0}</span>
          </div>
          <div>
            <span className="text-zinc-500 block">Win Rate</span>
            <span className="text-zinc-300 font-mono">{d.win_rate > 0 ? `${d.win_rate}%` : '—'}</span>
          </div>
          <div>
            <span className="text-zinc-500 block">Total Risk</span>
            <span className="text-red-400 font-mono">
              ${positions.reduce((s, p) => s + (p.risk || 0), 0).toFixed(2)}
            </span>
          </div>
          <div>
            <span className="text-zinc-500 block">Max Reward</span>
            <span className="text-emerald-400 font-mono">
              ${positions.reduce((s, p) => s + (p.max_reward || 0), 0).toFixed(2)}
            </span>
          </div>
        </div>
        {positions.length > 0 && (
          <div className="mt-3 text-[10px] text-zinc-600">
            Avg expected payoff: {(positions.reduce((s, p) => s + (p.expected_payoff_pct || 0), 0) / positions.length).toFixed(0)}% per position.
            Holding {positions.length} positions to resolution.
          </div>
        )}
      </SectionCard>
    </div>
  );
}


function CalibrationMetricsSection({ metrics }) {
  const m = metrics || {};
  if (!m.brier_score && m.brier_score !== 0) {
    return (
      <SectionCard title="Calibration Metrics" testId="section-cal-metrics">
        <div className="text-zinc-600 text-sm text-center py-4">
          {m.status === 'no_data' ? 'No resolved forecast data yet' : 'Collecting data...'}
        </div>
      </SectionCard>
    );
  }

  const byLead = m.by_lead_bracket || {};
  const byType = m.by_market_type || {};
  const calCurve = m.calibration_curve || [];
  const sigmaEvo = m.sigma_evolution || [];

  const coverageColor = (cov) => {
    const diff = Math.abs(cov - 0.6827);
    if (diff < 0.05) return 'text-emerald-400';
    if (diff < 0.15) return 'text-amber-400';
    return 'text-red-400';
  };

  return (
    <div className="space-y-5">
      {/* Overall Metrics */}
      <div data-testid="cal-metrics-overview" className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <StatCard testId="stat-brier" label="Brier Score" value={m.brier_score?.toFixed(3)}
          sub="Lower = better. 0 = perfect" />
        <StatCard testId="stat-coverage-1s" label="1σ Coverage" value={`${(m.coverage_1sigma * 100).toFixed(1)}%`}
          sub={`Target: 68.3%`} />
        <StatCard testId="stat-coverage-2s" label="2σ Coverage" value={`${(m.coverage_2sigma * 100).toFixed(1)}%`}
          sub="Target: 95.5%" />
        <StatCard testId="stat-cal-error" label="Calibration Error" value={m.calibration_error?.toFixed(3)}
          sub="0 = perfect" />
        <StatCard testId="stat-overconfident" label="Over-confident" value={`${(m.over_confident_pct * 100).toFixed(0)}%`}
          sub="Error > 1.5σ" />
        <StatCard testId="stat-underconfident" label="Under-confident" value={`${(m.under_confident_pct * 100).toFixed(0)}%`}
          sub="Error < 0.25σ" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* By Lead Time */}
        <SectionCard title="Calibration by Forecast Horizon" testId="section-cal-by-lead">
          <div className="space-y-3 text-xs">
            {Object.entries(byLead).map(([bracket, data]) => (
              <div key={bracket} className="space-y-1 border-b border-zinc-800/50 pb-2 last:border-0">
                <div className="flex justify-between items-center">
                  <span className="text-zinc-200 font-mono font-medium">{bracket.replace('_', '-')}h</span>
                  <span className="text-zinc-500">n={data.count}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Avg Error</span>
                  <span className="text-zinc-300 font-mono">{data.avg_error}°F</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Avg Sigma</span>
                  <span className="text-zinc-300 font-mono">{data.avg_sigma}°F</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">1σ Coverage</span>
                  <span className={`font-mono ${coverageColor(data.coverage_1sigma)}`}>{(data.coverage_1sigma * 100).toFixed(1)}%</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Sigma Rec.</span>
                  <span className="text-amber-400 font-mono">{data.sigma_recommendation}°F</span>
                </div>
                {data.is_overconfident && <Badge variant="outline" className="text-[9px] border-red-500/30 text-red-400">OVERCONFIDENT</Badge>}
                {data.is_underconfident && <Badge variant="outline" className="text-[9px] border-blue-500/30 text-blue-400">UNDERCONFIDENT</Badge>}
              </div>
            ))}
            {Object.keys(byLead).length === 0 && <div className="text-zinc-600 text-center py-2">No lead-time data yet</div>}
          </div>
        </SectionCard>

        {/* By Market Type */}
        <SectionCard title="Calibration by Market Type" testId="section-cal-by-type">
          <div className="space-y-3 text-xs">
            {Object.entries(byType).map(([type, data]) => {
              const colors = { temperature: 'text-amber-400', precipitation: 'text-blue-400', snowfall: 'text-cyan-300', wind: 'text-teal-400' };
              return (
                <div key={type} className="space-y-1 border-b border-zinc-800/50 pb-2 last:border-0">
                  <div className="flex justify-between items-center">
                    <span className={`font-mono font-medium uppercase ${colors[type] || 'text-zinc-400'}`}>{type}</span>
                    <span className="text-zinc-500">n={data.count}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Avg Error</span>
                    <span className="text-zinc-300 font-mono">{data.avg_error}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">1σ Coverage</span>
                    <span className={`font-mono ${coverageColor(data.coverage_1sigma)}`}>{(data.coverage_1sigma * 100).toFixed(1)}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Brier Score</span>
                    <span className="text-zinc-300 font-mono">{data.brier_score}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Sigma Rec.</span>
                    <span className="text-amber-400 font-mono">{data.sigma_recommendation}</span>
                  </div>
                </div>
              );
            })}
            {Object.keys(byType).length === 0 && <div className="text-zinc-600 text-center py-2">No market type data yet</div>}
          </div>
        </SectionCard>
      </div>

      {/* Calibration Curve */}
      {calCurve.length > 0 && (
        <SectionCard title="Calibration Curve (Predicted σ vs Actual Error)" testId="section-cal-curve">
          <div className="space-y-2 text-xs">
            <div className="flex items-center gap-4 text-zinc-500 border-b border-zinc-800/50 pb-1.5">
              <span className="w-24">Pred. Sigma</span>
              <span className="w-24">Actual Error</span>
              <span className="w-16">Ratio</span>
              <span className="w-12">N</span>
              <span className="flex-1">Visual</span>
            </div>
            {calCurve.map((p, i) => {
              const ratio = p.ratio || 0;
              const barWidth = Math.min(ratio * 50, 100);
              const barColor = ratio > 1.3 ? 'bg-red-500' : ratio > 0.8 ? 'bg-emerald-500' : 'bg-blue-500';
              return (
                <div key={i} className="flex items-center gap-4">
                  <span className="w-24 text-zinc-300 font-mono">{p.predicted_sigma}°F</span>
                  <span className="w-24 text-zinc-300 font-mono">{p.actual_error}°F</span>
                  <span className={`w-16 font-mono ${ratio > 1.3 ? 'text-red-400' : ratio > 0.8 ? 'text-emerald-400' : 'text-blue-400'}`}>
                    {ratio.toFixed(2)}x
                  </span>
                  <span className="w-12 text-zinc-500">{p.count}</span>
                  <div className="flex-1 bg-zinc-800 rounded-full h-2">
                    <div className={`h-2 rounded-full ${barColor}`} style={{ width: `${barWidth}%` }} />
                  </div>
                </div>
              );
            })}
            <div className="text-zinc-600 text-[10px] mt-2">
              Ratio = Actual Error / Predicted Sigma. 1.0x = perfectly calibrated. {'>'} 1.3x = overconfident. {'<'} 0.8x = underconfident.
            </div>
          </div>
        </SectionCard>
      )}

      {/* Sigma Evolution (last 100 forecasts) */}
      {sigmaEvo.length > 0 && (
        <SectionCard title="Sigma Evolution (Recent)" testId="section-sigma-evo">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-zinc-500 border-b border-zinc-800">
                  <th className="text-left py-1 px-2">Date</th>
                  <th className="text-left py-1 px-2">Station</th>
                  <th className="text-right py-1 px-2">σ Used</th>
                  <th className="text-right py-1 px-2">Actual Error</th>
                  <th className="text-right py-1 px-2">Z-Score</th>
                  <th className="text-right py-1 px-2">Lead</th>
                </tr>
              </thead>
              <tbody>
                {sigmaEvo.slice(-20).map((row, i) => (
                  <tr key={i} className="border-b border-zinc-800/30">
                    <td className="py-1 px-2 text-zinc-400">{row.date}</td>
                    <td className="py-1 px-2 text-cyan-400 font-mono">{row.station}</td>
                    <td className="py-1 px-2 text-right text-zinc-300 font-mono">{row.sigma_used}°F</td>
                    <td className="py-1 px-2 text-right font-mono">
                      <span className={row.actual_error > row.sigma_used ? 'text-red-400' : 'text-emerald-400'}>{row.actual_error}°F</span>
                    </td>
                    <td className="py-1 px-2 text-right font-mono">
                      <span className={row.z_score > 2 ? 'text-red-400' : row.z_score > 1 ? 'text-amber-400' : 'text-emerald-400'}>{row.z_score}</span>
                    </td>
                    <td className="py-1 px-2 text-right text-zinc-400 font-mono">{row.lead_hours?.toFixed(0)}h</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}
    </div>
  );
}


function SigmaPipelineSection({ pipeline, calMetrics, autoTune }) {
  const p = pipeline || {};
  const m = calMetrics || {};
  const at = autoTune || {};
  const isActive = p.overconfidence_active;
  const mult = p.overconfidence_multiplier || 1.0;
  const maxAdj = p.calibration_max_adjustment_pct || 0.25;
  const minSamples = p.calibration_min_samples || 30;
  const totalValid = m.total_valid || 0;
  const samplesProgress = Math.min(totalValid / minSamples * 100, 100);

  // Auto-tune data
  const atEnabled = at.auto_tune_enabled || false;
  const mgmtMode = at.management_mode || 'manual';
  const recMult = at.recommended_multiplier;
  const recDirection = at.recommended_direction || 'hold';
  const wouldChange = at.would_change || false;
  const coverage = at.coverage_1sigma;
  const targetBand = at.target_band || [0.6327, 0.7327];

  // Mode label and color
  const modeConfig = {
    manual: { label: 'MANUAL', color: 'text-zinc-400', border: 'border-zinc-700', bg: 'bg-zinc-900/50' },
    auto_pending: { label: 'AUTO (PENDING)', color: 'text-amber-400', border: 'border-amber-700/40', bg: 'bg-amber-950/20' },
    auto: { label: 'AUTO', color: 'text-emerald-400', border: 'border-emerald-700/40', bg: 'bg-emerald-950/20' },
  };
  const mc = modeConfig[mgmtMode] || modeConfig.manual;

  // Calibration status
  let calLabel = 'Insufficient Data';
  let calColor = 'text-zinc-500';
  if (totalValid >= minSamples) {
    calLabel = 'Active';
    calColor = 'text-emerald-400';
  } else if (totalValid > 0) {
    calLabel = `Blending (${totalValid}/${minSamples})`;
    calColor = 'text-amber-400';
  }

  return (
    <SectionCard title="Sigma Pipeline & Auto-Tune" testId="section-sigma-pipeline">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: Current State */}
        <div className="space-y-4">
          <div className="text-zinc-500 text-[10px] uppercase tracking-wider font-medium">Current State</div>

          <div className="grid grid-cols-2 gap-4">
            {/* Current Multiplier */}
            <div data-testid="sigma-current-mult">
              <span className="text-zinc-500 text-xs block mb-1">Current Multiplier</span>
              <span className="text-3xl font-mono font-bold text-amber-300">{mult.toFixed(2)}x</span>
              <div className="mt-1">
                <Badge variant="outline" className={`text-[9px] ${isActive ? 'border-amber-500/30 text-amber-400' : 'border-zinc-700 text-zinc-600'}`}>
                  {isActive ? 'ACTIVE' : 'NEUTRAL'}
                </Badge>
              </div>
            </div>

            {/* Management Mode */}
            <div data-testid="sigma-mgmt-mode">
              <span className="text-zinc-500 text-xs block mb-1">Management</span>
              <div className={`inline-block px-3 py-1.5 rounded-md border text-sm font-mono font-bold ${mc.color} ${mc.border} ${mc.bg}`}>
                {mc.label}
              </div>
              <div className="text-[10px] text-zinc-600 mt-1">
                {mgmtMode === 'manual' && 'Operator sets multiplier directly'}
                {mgmtMode === 'auto_pending' && 'Auto-tune enabled, waiting for data'}
                {mgmtMode === 'auto' && 'Multiplier adjusts per step automatically'}
              </div>
            </div>
          </div>

          {/* Guardrails */}
          <div className="space-y-1.5 text-xs">
            <div className="flex justify-between">
              <span className="text-zinc-500">Max Cal. Adjustment</span>
              <span className="text-zinc-300 font-mono">&plusmn;{(maxAdj * 100).toFixed(0)}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">Calibration Samples</span>
              <span className={`font-mono ${calColor}`}>{calLabel}</span>
            </div>
            <div className="w-full bg-zinc-800 rounded-full h-1.5">
              <div
                className={`h-1.5 rounded-full transition-all duration-500 ${samplesProgress >= 100 ? 'bg-emerald-500' : 'bg-amber-500'}`}
                style={{ width: `${samplesProgress}%` }}
              />
            </div>
          </div>
        </div>

        {/* Right: Auto-Tune Recommendation */}
        <div className="space-y-4">
          <div className="text-zinc-500 text-[10px] uppercase tracking-wider font-medium">Auto-Tune Recommendation</div>

          {at.status === 'insufficient_data' ? (
            <div className="space-y-3">
              <div className="text-zinc-600 text-sm">
                Waiting for {minSamples} resolved samples ({totalValid} collected)
              </div>
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                  <span className="text-zinc-500 block">Samples</span>
                  <span className="text-amber-400 font-mono text-lg">{totalValid}/{minSamples}</span>
                </div>
                <div>
                  <span className="text-zinc-500 block">Auto-Tune</span>
                  <Badge variant="outline" className={`text-[9px] ${atEnabled ? 'border-amber-500/30 text-amber-400' : 'border-zinc-700 text-zinc-600'}`}>
                    {atEnabled ? 'ENABLED (WAITING)' : 'DISABLED'}
                  </Badge>
                </div>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {/* Recommended Multiplier */}
              <div className="grid grid-cols-3 gap-3">
                <div data-testid="sigma-recommended-mult">
                  <span className="text-zinc-500 text-xs block">Recommended</span>
                  <span className={`text-2xl font-mono font-bold ${wouldChange ? (recDirection === 'decrease' ? 'text-emerald-400' : 'text-amber-400') : 'text-zinc-400'}`}>
                    {recMult != null ? `${recMult.toFixed(2)}x` : '—'}
                  </span>
                </div>
                <div data-testid="sigma-direction">
                  <span className="text-zinc-500 text-xs block">Direction</span>
                  <span className={`text-lg font-mono font-bold ${
                    recDirection === 'decrease' ? 'text-emerald-400' : recDirection === 'increase' ? 'text-amber-400' : 'text-zinc-500'
                  }`}>
                    {recDirection === 'decrease' ? 'NARROW' : recDirection === 'increase' ? 'WIDEN' : 'HOLD'}
                  </span>
                </div>
                <div data-testid="sigma-step-size">
                  <span className="text-zinc-500 text-xs block">Step Size</span>
                  <span className="text-zinc-300 font-mono text-lg">{(at.step_size || 0.05).toFixed(2)}</span>
                </div>
              </div>

              {/* Coverage vs Target */}
              <div className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="text-zinc-500">1σ Coverage</span>
                  <span className={`font-mono ${
                    coverage != null && Math.abs(coverage - 0.6827) < 0.05 ? 'text-emerald-400'
                    : coverage != null && coverage < 0.6327 ? 'text-red-400'
                    : 'text-amber-400'
                  }`}>
                    {coverage != null ? `${(coverage * 100).toFixed(1)}%` : '—'}
                  </span>
                </div>
                {coverage != null && (
                  <div className="relative w-full h-3 bg-zinc-800 rounded-full overflow-hidden">
                    {/* Target band */}
                    <div className="absolute h-full bg-emerald-900/40 rounded"
                      style={{ left: `${targetBand[0] * 100}%`, width: `${(targetBand[1] - targetBand[0]) * 100}%` }} />
                    {/* Current coverage marker */}
                    <div className="absolute top-0 h-full w-0.5 bg-white rounded"
                      style={{ left: `${Math.min(coverage * 100, 100)}%` }} />
                    {/* Labels */}
                    <div className="absolute text-[8px] text-emerald-500/80 font-mono"
                      style={{ left: `${targetBand[0] * 100 + 1}%`, top: '-1px' }}>target</div>
                  </div>
                )}
              </div>

              {/* Reasoning */}
              <div className="text-[10px] text-zinc-600 mt-1">
                {at.reason}
              </div>

              {/* Multiplier range */}
              <div className="flex items-center gap-2 text-[10px] text-zinc-600">
                <span>Range: {at.min_multiplier?.toFixed(2)}x</span>
                <div className="flex-1 h-1 bg-zinc-800 rounded-full relative">
                  <div className="absolute h-1 rounded-full bg-amber-800/40"
                    style={{
                      left: `${((mult - (at.min_multiplier || 1.0)) / ((at.max_multiplier || 1.5) - (at.min_multiplier || 1.0))) * 100}%`,
                      width: '4px'
                    }} />
                </div>
                <span>{at.max_multiplier?.toFixed(2)}x</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </SectionCard>
  );
}


function WeatherByTypeSection({ data }) {
  const d = data || {};
  const types = ['temperature', 'precipitation', 'snowfall', 'wind'];
  const typeColors = {
    temperature: { accent: 'text-amber-400', bg: 'bg-amber-950/30', border: 'border-amber-800/30' },
    precipitation: { accent: 'text-blue-400', bg: 'bg-blue-950/30', border: 'border-blue-800/30' },
    snowfall: { accent: 'text-cyan-300', bg: 'bg-cyan-950/30', border: 'border-cyan-800/30' },
    wind: { accent: 'text-teal-400', bg: 'bg-teal-950/30', border: 'border-teal-800/30' },
  };

  return (
    <div className="space-y-5">
      <div data-testid="weather-by-type" className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {types.map(type => {
          const td = d[type] || {};
          const colors = typeColors[type];
          const totalPnl = td.total_pnl || 0;
          const hasTrades = (td.buy_count || 0) > 0;

          return (
            <div key={type} data-testid={`type-card-${type}`}
              className={`p-4 rounded-lg border ${colors.bg} ${colors.border}`}>
              <div className="flex items-center justify-between mb-3">
                <span className={`font-mono font-bold text-sm uppercase ${colors.accent}`}>{type}</span>
                {hasTrades && (
                  <span className={`text-xs font-mono font-medium ${totalPnl > 0 ? 'text-emerald-400' : totalPnl < 0 ? 'text-red-400' : 'text-zinc-500'}`}>
                    {formatPnl(totalPnl)}
                  </span>
                )}
              </div>

              {hasTrades ? (
                <div className="space-y-2 text-xs">
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Buys / Closes</span>
                    <span className="text-zinc-300 font-mono">{td.buy_count || 0} / {td.close_count || 0}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Open Positions</span>
                    <span className="text-zinc-300 font-mono">{td.open_positions || 0}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Realized PnL</span>
                    <span className={`font-mono ${(td.realized_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {formatPnl(td.realized_pnl || 0)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Unrealized PnL</span>
                    <span className={`font-mono ${(td.unrealized_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {formatPnl(td.unrealized_pnl || 0)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Win / Loss</span>
                    <span className="text-zinc-300 font-mono">{td.wins || 0} / {td.losses || 0}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Win Rate</span>
                    <span className="text-zinc-300 font-mono">{td.win_rate > 0 ? `${td.win_rate}%` : '—'}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Total Size</span>
                    <span className="text-zinc-300 font-mono">${td.total_size?.toFixed(1) || '0.0'}</span>
                  </div>
                </div>
              ) : (
                <div className="text-zinc-600 text-xs text-center py-4">No {type} trades yet</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
