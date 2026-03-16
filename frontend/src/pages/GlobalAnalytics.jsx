import { useEffect, useState, useCallback } from 'react';
import { StatCard } from '../components/StatCard';
import { SectionCard } from '../components/SectionCard';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { formatPnl, formatNumber, pnlColor } from '../utils/formatters';
import axios from 'axios';
import { API_BASE } from '../utils/constants';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, AreaChart, Area, ReferenceLine, Cell, Legend,
} from 'recharts';

export default function GlobalAnalytics() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState('performance');

  const fetchData = useCallback(async () => {
    try {
      const { data: d } = await axios.get(`${API_BASE}/analytics/global`);
      setData(d);
    } catch (e) {
      console.error('Failed to fetch global analytics', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 15000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading && !data) {
    return (
      <div data-testid="global-analytics-page" className="flex items-center justify-center h-64">
        <span className="text-zinc-500 text-sm">Loading global analytics...</span>
      </div>
    );
  }

  const perf = data?.strategy_performance || {};
  const forecast = data?.forecast_quality || {};
  const liquidity = data?.liquidity_insights || {};
  const ts = data?.timeseries || {};
  const resolver = data?.auto_resolver || {};

  return (
    <div data-testid="global-analytics-page" className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-zinc-100">Global Analytics</h1>
        <Badge variant="outline" className="text-[10px] text-zinc-500 border-zinc-700">
          Shadow Evaluation
        </Badge>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList data-testid="global-analytics-tabs" className="bg-zinc-900 border border-zinc-800">
          <TabsTrigger value="performance" data-testid="tab-performance" className="text-xs data-[state=active]:bg-zinc-800">Performance</TabsTrigger>
          <TabsTrigger value="forecast" data-testid="tab-forecast" className="text-xs data-[state=active]:bg-zinc-800">Forecast Quality</TabsTrigger>
          <TabsTrigger value="liquidity" data-testid="tab-liquidity" className="text-xs data-[state=active]:bg-zinc-800">Liquidity</TabsTrigger>
          <TabsTrigger value="charts" data-testid="tab-charts" className="text-xs data-[state=active]:bg-zinc-800">Charts</TabsTrigger>
        </TabsList>

        <TabsContent value="performance" className="mt-4 space-y-4">
          <PerformanceTab perf={perf} />
        </TabsContent>
        <TabsContent value="forecast" className="mt-4 space-y-4">
          <ForecastTab forecast={forecast} resolver={resolver} />
        </TabsContent>
        <TabsContent value="liquidity" className="mt-4 space-y-4">
          <LiquidityTab liquidity={liquidity} />
        </TabsContent>
        <TabsContent value="charts" className="mt-4 space-y-4">
          <ChartsTab ts={ts} perf={perf} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Metric({ label, value, color, testId }) {
  return (
    <div data-testid={testId} className="flex justify-between items-center text-xs py-1">
      <span className="text-zinc-500">{label}</span>
      <span className={`font-mono ${color || 'text-zinc-300'}`}>{value ?? '—'}</span>
    </div>
  );
}

function GATooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-xs shadow-xl">
      <p className="text-zinc-500 mb-1">{label}</p>
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color || '#a1a1aa' }}>
          {p.name}: {typeof p.value === 'number' ? (p.dataKey === 'cumulative_pnl' || p.dataKey === 'daily_pnl' ? (p.value >= 0 ? '+' : '') + '$' + p.value.toFixed(2) : p.value) : p.value}
        </p>
      ))}
    </div>
  );
}

// ---- Performance Tab ----

function PerformanceTab({ perf }) {
  const byStrat = perf.by_strategy || {};
  const NAMES = {
    weather_trader: 'Weather Trader',
    arb_scanner: 'Arb Scanner',
    crypto_sniper: 'Crypto Sniper',
  };

  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <StatCard testId="ga-total-signals" label="Total Signals" value={formatNumber(perf.total_signals)} />
        <StatCard testId="ga-total-executed" label="Executions" value={formatNumber(perf.total_executions)} />
        <StatCard testId="ga-total-filled" label="Filled" value={formatNumber(perf.total_filled)} />
        <StatCard testId="ga-realized-pnl" label="Realized P&L" value={formatPnl(perf.realized_pnl)} format="pnl" />
        <StatCard testId="ga-win-rate" label="Win Rate" value={perf.win_rate != null ? `${perf.win_rate}%` : '—'} />
        <StatCard testId="ga-total-trades" label="Total Trades" value={formatNumber(perf.total_trades)} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SectionCard title="Aggregate Performance" testId="section-aggregate-perf">
          <div className="space-y-0.5">
            <Metric label="Wins" value={formatNumber(perf.win_count)} color="text-emerald-400" testId="ga-wins" />
            <Metric label="Losses" value={formatNumber(perf.loss_count)} color="text-red-400" testId="ga-losses" />
            <Metric label="Avg Win" value={perf.avg_win ? formatPnl(perf.avg_win) : '—'} color="text-emerald-400" testId="ga-avg-win" />
            <Metric label="Avg Loss" value={perf.avg_loss ? formatPnl(perf.avg_loss) : '—'} color="text-red-400" testId="ga-avg-loss" />
          </div>
        </SectionCard>

        {Object.entries(byStrat).map(([id, s]) => (
          <SectionCard key={id} title={NAMES[id] || id} testId={`section-strat-${id}`}>
            <div className="space-y-0.5">
              <Metric label="Signals" value={formatNumber(s.total_signals)} testId={`ga-${id}-signals`} />
              <Metric label="Executed" value={formatNumber(s.total_executed)} testId={`ga-${id}-exec`} />
              <Metric label="Filled" value={formatNumber(s.total_filled)} testId={`ga-${id}-filled`} />
              <Metric label="Active" value={formatNumber(s.active_executions)} testId={`ga-${id}-active`} />
              {s.avg_expected_edge_bps != null && (
                <Metric label="Avg Expected Edge" value={`${s.avg_expected_edge_bps}bps`} testId={`ga-${id}-edge`} />
              )}
              {s.classified_markets != null && (
                <Metric label="Classified Markets" value={formatNumber(s.classified_markets)} testId={`ga-${id}-classified`} />
              )}
              {s.total_scans != null && (
                <Metric label="Total Scans" value={formatNumber(s.total_scans)} testId={`ga-${id}-scans`} />
              )}
            </div>
          </SectionCard>
        ))}
      </div>

      {perf.total_signals === 0 && (
        <div data-testid="ga-empty-perf" className="text-center py-8 text-zinc-600 text-sm">
          Start the engine to generate signals and track performance
        </div>
      )}
    </>
  );
}

// ---- Forecast Quality Tab ----

function ForecastTab({ forecast, resolver }) {
  const stations = Object.entries(forecast.station_metrics || {});
  const errorDist = forecast.error_distribution || [];
  const hasData = forecast.total_forecasts > 0;

  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <StatCard testId="ga-global-mae" label="Global MAE" value={forecast.global_mae_f != null ? `${forecast.global_mae_f.toFixed(1)}F` : '—'} />
        <StatCard testId="ga-global-bias" label="Global Bias" value={forecast.global_bias_f != null ? `${forecast.global_bias_f > 0 ? '+' : ''}${forecast.global_bias_f.toFixed(1)}F` : '—'} />
        <StatCard testId="ga-total-forecasts" label="Total Forecasts" value={formatNumber(forecast.total_forecasts)} />
        <StatCard testId="ga-resolved" label="Resolved" value={formatNumber(forecast.resolved_forecasts)} />
        <StatCard testId="ga-pending" label="Pending" value={formatNumber(forecast.pending_resolution)} />
        <StatCard testId="ga-cal-status" label="Calibration" value={forecast.calibration_status || '—'} />
      </div>

      {resolver.running != null && (
        <SectionCard title="Auto-Resolver" testId="section-auto-resolver">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-1">
            <Metric label="Status" value={resolver.running ? 'Running' : 'Stopped'} color={resolver.running ? 'text-emerald-400' : 'text-red-400'} testId="ga-resolver-status" />
            <Metric label="Interval" value={resolver.interval_hours ? `${resolver.interval_hours}h` : '—'} testId="ga-resolver-interval" />
            <Metric label="Total Runs" value={formatNumber(resolver.total_runs)} testId="ga-resolver-runs" />
            <Metric label="Total Resolved" value={formatNumber(resolver.total_resolved)} testId="ga-resolver-total-resolved" />
            <Metric label="Pending Records" value={formatNumber(resolver.pending_records)} testId="ga-resolver-pending" />
            <Metric label="Last Run Resolved" value={formatNumber(resolver.last_run_resolved)} testId="ga-resolver-last-resolved" />
            <Metric label="Last Run" value={resolver.last_run_at ? new Date(resolver.last_run_at).toLocaleTimeString() : 'Not yet'} testId="ga-resolver-last-run" />
            <Metric label="Last Error" value={resolver.last_error || 'None'} color={resolver.last_error ? 'text-red-400' : 'text-zinc-500'} testId="ga-resolver-error" />
          </div>
        </SectionCard>
      )}

      {errorDist.length > 0 && (
        <SectionCard title="Forecast Error Distribution" testId="section-error-dist">
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={errorDist} margin={{ top: 4, right: 8, bottom: 4, left: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
              <XAxis
                dataKey="error_f"
                tick={{ fill: '#52525b', fontSize: 9 }}
                axisLine={{ stroke: '#27272a' }}
                tickLine={false}
                tickFormatter={(v) => `${v > 0 ? '+' : ''}${v}F`}
              />
              <YAxis tick={{ fill: '#52525b', fontSize: 9 }} axisLine={false} tickLine={false} width={30} />
              <Tooltip content={<GATooltip />} />
              <Bar dataKey="count" name="Forecasts" radius={[2, 2, 0, 0]}>
                {errorDist.map((d, i) => (
                  <Cell key={i} fill={Math.abs(d.error_f) <= 2 ? '#34d399' : Math.abs(d.error_f) <= 4 ? '#fbbf24' : '#f87171'} fillOpacity={0.7} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          <p className="text-[10px] text-zinc-600 mt-1 text-center">
            Green = within 2F, Yellow = within 4F, Red = 4F+
          </p>
        </SectionCard>
      )}

      {stations.length > 0 && (
        <SectionCard title="Station Forecast Metrics" testId="section-station-metrics">
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-zinc-800 text-zinc-500">
                  <th className="text-left py-2 px-2">Station</th>
                  <th className="text-right py-2 px-2">Samples</th>
                  <th className="text-right py-2 px-2">MAE</th>
                  <th className="text-right py-2 px-2">Bias</th>
                  <th className="text-right py-2 px-2">Max Error</th>
                  <th className="text-right py-2 px-2">Avg Sigma</th>
                  <th className="text-center py-2 px-2">Status</th>
                </tr>
              </thead>
              <tbody>
                {stations.map(([id, m]) => (
                  <tr key={id} className="border-b border-zinc-800/50 hover:bg-zinc-900/50">
                    <td className="py-2 px-2 text-zinc-300 font-mono">{id}</td>
                    <td className="py-2 px-2 text-right text-zinc-400">{m.sample_count}</td>
                    <td className="py-2 px-2 text-right font-mono text-zinc-300">
                      {m.mean_abs_error_f != null ? `${m.mean_abs_error_f.toFixed(1)}F` : '—'}
                    </td>
                    <td className={`py-2 px-2 text-right font-mono ${m.mean_bias_f > 0 ? 'text-amber-400' : m.mean_bias_f < 0 ? 'text-blue-400' : 'text-zinc-400'}`}>
                      {m.mean_bias_f != null ? `${m.mean_bias_f > 0 ? '+' : ''}${m.mean_bias_f.toFixed(1)}F` : '—'}
                    </td>
                    <td className="py-2 px-2 text-right font-mono text-zinc-400">
                      {m.max_abs_error_f != null ? `${m.max_abs_error_f.toFixed(1)}F` : '—'}
                    </td>
                    <td className="py-2 px-2 text-right font-mono text-zinc-400">
                      {m.avg_sigma_used != null ? `${m.avg_sigma_used.toFixed(1)}` : '—'}
                    </td>
                    <td className="py-2 px-2 text-center">
                      <Badge
                        variant={m.calibration_meaningful ? 'default' : 'secondary'}
                        className={`text-[10px] ${m.calibration_meaningful ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' : ''}`}
                      >
                        {m.calibration_meaningful ? 'Ready' : 'Collecting'}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}

      {!hasData && (
        <div data-testid="ga-empty-forecast" className="text-center py-8 text-zinc-600 text-sm">
          No forecast accuracy data collected yet — run the engine in shadow mode to begin
        </div>
      )}
    </>
  );
}

// ---- Liquidity Tab ----

function LiquidityTab({ liquidity }) {
  const weatherRej = liquidity.weather_rejections || {};
  const rejEntries = Object.entries(weatherRej).sort((a, b) => b[1] - a[1]);
  const totalRej = liquidity.total_weather_rejections || 0;

  const REJ_COLORS = {
    edge: 'bg-red-500/20 text-red-400',
    liquidity_too_low: 'bg-orange-500/20 text-orange-400',
    spread: 'bg-amber-500/20 text-amber-400',
    stale_market: 'bg-zinc-500/20 text-zinc-400',
    confidence: 'bg-blue-500/20 text-blue-400',
    risk: 'bg-purple-500/20 text-purple-400',
    cooldown: 'bg-cyan-500/20 text-cyan-400',
  };

  // Build rejection chart data
  const rejChartData = rejEntries.map(([reason, count]) => ({
    reason: reason.replace(/_/g, ' '),
    count,
    pct: totalRej > 0 ? round((count / totalRej) * 100, 1) : 0,
  }));

  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard testId="ga-avg-liq" label="Avg Liquidity Score" value={liquidity.avg_traded_liquidity_score || '—'} />
        <StatCard testId="ga-min-liq" label="Min Score" value={liquidity.min_traded_liquidity_score || '—'} />
        <StatCard testId="ga-max-liq" label="Max Score" value={liquidity.max_traded_liquidity_score || '—'} />
        <StatCard testId="ga-markets-scored" label="Markets Scored" value={formatNumber(liquidity.markets_with_scores)} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SectionCard title="Weather Rejection Breakdown" testId="section-rejection-breakdown">
          {rejEntries.length > 0 ? (
            <div className="space-y-2">
              {rejEntries.map(([reason, count]) => {
                const pct = totalRej > 0 ? ((count / totalRej) * 100).toFixed(1) : 0;
                const colorClass = REJ_COLORS[reason] || 'bg-zinc-500/20 text-zinc-400';
                return (
                  <div key={reason} data-testid={`rej-${reason}`} className="space-y-1">
                    <div className="flex justify-between items-center text-xs">
                      <span className="text-zinc-400">{reason.replace(/_/g, ' ')}</span>
                      <span className="text-zinc-500 font-mono">{count} ({pct}%)</span>
                    </div>
                    <div className="w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${colorClass.split(' ')[0].replace('/20', '/50')}`}
                        style={{ width: `${Math.min(pct, 100)}%` }}
                      />
                    </div>
                  </div>
                );
              })}
              <div className="pt-2 border-t border-zinc-800 flex justify-between text-xs">
                <span className="text-zinc-500">Total Rejections</span>
                <span className="text-zinc-300 font-mono">{formatNumber(totalRej)}</span>
              </div>
            </div>
          ) : (
            <p className="text-xs text-zinc-600 py-4 text-center">No rejections recorded yet</p>
          )}
        </SectionCard>

        {rejChartData.length > 0 && (
          <SectionCard title="Rejection Distribution" testId="section-rejection-chart">
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={rejChartData} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" horizontal={false} />
                <XAxis type="number" tick={{ fill: '#52525b', fontSize: 9 }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="reason" tick={{ fill: '#71717a', fontSize: 9 }} axisLine={false} tickLine={false} width={100} />
                <Tooltip content={<GATooltip />} />
                <Bar dataKey="count" name="Rejections" fill="#f59e0b" fillOpacity={0.6} radius={[0, 3, 3, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </SectionCard>
        )}
      </div>

      {totalRej === 0 && liquidity.markets_with_scores === 0 && (
        <div data-testid="ga-empty-liquidity" className="text-center py-8 text-zinc-600 text-sm">
          No liquidity data yet — start the engine to score markets
        </div>
      )}
    </>
  );
}

// ---- Charts Tab ----

function ChartsTab({ ts, perf }) {
  const cumPnl = ts.cumulative_pnl || [];
  const sigFreq = ts.signal_frequency || [];
  const hasData = cumPnl.length > 0;

  return (
    <>
      {hasData ? (
        <>
          <SectionCard title="Cumulative P&L" testId="section-cum-pnl">
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={cumPnl} margin={{ top: 4, right: 8, bottom: 4, left: 4 }}>
                <defs>
                  <linearGradient id="cumPnlGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#34d399" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#34d399" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: '#52525b', fontSize: 9 }} axisLine={{ stroke: '#27272a' }} tickLine={false} />
                <YAxis tick={{ fill: '#52525b', fontSize: 9 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v}`} width={50} />
                <Tooltip content={<GATooltip />} />
                <ReferenceLine y={0} stroke="#3f3f46" />
                <Area type="monotone" dataKey="cumulative_pnl" name="Cumulative P&L" stroke="#34d399" fill="url(#cumPnlGrad)" strokeWidth={2} dot={false} isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </SectionCard>

          <SectionCard title="Daily P&L" testId="section-daily-ga-pnl">
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={cumPnl} margin={{ top: 4, right: 8, bottom: 4, left: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: '#52525b', fontSize: 9 }} axisLine={{ stroke: '#27272a' }} tickLine={false} />
                <YAxis tick={{ fill: '#52525b', fontSize: 9 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v}`} width={44} />
                <Tooltip content={<GATooltip />} />
                <ReferenceLine y={0} stroke="#3f3f46" />
                <Bar dataKey="daily_pnl" name="Daily P&L" radius={[2, 2, 0, 0]}>
                  {cumPnl.map((d, i) => (
                    <Cell key={i} fill={d.daily_pnl >= 0 ? '#34d399' : '#f87171'} fillOpacity={0.7} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </SectionCard>

          <SectionCard title="Signal Frequency" testId="section-signal-freq">
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={sigFreq} margin={{ top: 4, right: 8, bottom: 4, left: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: '#52525b', fontSize: 9 }} axisLine={{ stroke: '#27272a' }} tickLine={false} />
                <YAxis tick={{ fill: '#52525b', fontSize: 9 }} axisLine={false} tickLine={false} width={30} />
                <Tooltip content={<GATooltip />} />
                <Legend iconSize={8} wrapperStyle={{ fontSize: 10, color: '#71717a' }} />
                <Bar dataKey="weather_trader" name="Weather" stackId="a" fill="#38bdf8" fillOpacity={0.6} />
                <Bar dataKey="arb_scanner" name="Arb" stackId="a" fill="#a78bfa" fillOpacity={0.6} />
                <Bar dataKey="crypto_sniper" name="Sniper" stackId="a" fill="#fbbf24" fillOpacity={0.6} radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </SectionCard>
        </>
      ) : (
        <div data-testid="ga-empty-charts" className="text-center py-8 text-zinc-600 text-sm">
          Generate trades to see cumulative P&L, daily P&L, and signal frequency charts
        </div>
      )}
    </>
  );
}

function round(v, d) {
  const f = Math.pow(10, d);
  return Math.round(v * f) / f;
}
