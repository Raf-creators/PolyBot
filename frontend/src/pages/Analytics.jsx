import { useEffect, useState, useCallback } from 'react';
import { StatCard } from '../components/StatCard';
import { SectionCard } from '../components/SectionCard';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { formatPnl, formatPercent, formatNumber, pnlColor } from '../utils/formatters';
import { PnlChart } from '../components/PnlChart';
import { useDashboardStore } from '../state/dashboardStore';
import { useApi } from '../hooks/useApi';
import axios from 'axios';
import { API_BASE } from '../utils/constants';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, AreaChart, Area, ReferenceLine, Cell,
} from 'recharts';

export default function Analytics() {
  const pnlHistory = useDashboardStore((s) => s.pnlHistory);
  const demoMode = useDashboardStore((s) => s.demoMode);
  const signalQuality = useDashboardStore((s) => s.signalQuality);
  const watchdog = useDashboardStore((s) => s.watchdog);
  const strategyTracker = useDashboardStore((s) => s.strategyTracker);
  const strategyAttribution = useDashboardStore((s) => s.strategyAttribution);
  const strategyPositions = useDashboardStore((s) => s.strategyPositions);
  const controls = useDashboardStore((s) => s.controls);
  const { fetchPnlHistory, fetchSignalQuality, fetchWatchdog, fetchStrategyTracker, fetchStrategyAttribution, fetchControls, fetchStrategyPositions } = useApi();
  const [summary, setSummary] = useState(null);
  const [strategies, setStrategies] = useState({});
  const [execQuality, setExecQuality] = useState(null);
  const [timeseries, setTimeseries] = useState(null);
  const [tab, setTab] = useState('comparison');

  const prefix = demoMode ? '/demo' : '';

  const fetchAll = useCallback(async () => {
    try {
      const [s, st, eq, ts] = await Promise.all([
        axios.get(`${API_BASE}${prefix}/analytics/summary`),
        axios.get(`${API_BASE}${prefix}/analytics/strategies`),
        axios.get(`${API_BASE}${prefix}/analytics/execution-quality`),
        axios.get(`${API_BASE}${prefix}/analytics/timeseries`),
      ]);
      setSummary(s.data);
      setStrategies(st.data);
      setExecQuality(eq.data);
      setTimeseries(ts.data);
    } catch {}
    fetchSignalQuality();
    fetchWatchdog();
    fetchStrategyTracker();
    fetchStrategyAttribution();
    fetchControls();
    fetchStrategyPositions();
  }, [prefix, fetchSignalQuality, fetchWatchdog, fetchStrategyTracker, fetchStrategyAttribution, fetchControls, fetchStrategyPositions]);

  useEffect(() => {
    fetchPnlHistory();
    fetchAll();
    const interval = setInterval(fetchAll, 15000);
    return () => clearInterval(interval);
  }, [fetchAll, fetchPnlHistory]);

  const s = summary || {};
  const hasData = s.trade_count > 0;

  return (
    <div data-testid="analytics-page" className="space-y-5">
      <h1 className="text-lg font-semibold text-zinc-100">Analytics</h1>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-zinc-900 border border-zinc-800 flex-wrap">
          <TabsTrigger value="comparison" className="text-xs data-[state=active]:bg-zinc-800">Strategy Comparison</TabsTrigger>
          <TabsTrigger value="controls" className="text-xs data-[state=active]:bg-zinc-800">Controls</TabsTrigger>
          <TabsTrigger value="overview" className="text-xs data-[state=active]:bg-zinc-800">Overview</TabsTrigger>
          <TabsTrigger value="signals" className="text-xs data-[state=active]:bg-zinc-800">Signal Quality</TabsTrigger>
          <TabsTrigger value="watchdog" className="text-xs data-[state=active]:bg-zinc-800">Watchdog</TabsTrigger>
          <TabsTrigger value="charts" className="text-xs data-[state=active]:bg-zinc-800">Charts</TabsTrigger>
        </TabsList>

        <TabsContent value="comparison" className="mt-4 space-y-4">
          <StrategyComparisonSection attribution={strategyAttribution} strategyTracker={strategyTracker} positionSummaries={strategyPositions?.summaries} />
        </TabsContent>

        <TabsContent value="controls" className="mt-4 space-y-4">
          <ControlsSection controls={controls} />
        </TabsContent>

        <TabsContent value="overview" className="mt-4 space-y-4">
          <OverviewSection s={s} hasData={hasData} pnlHistory={pnlHistory} />
        </TabsContent>

        <TabsContent value="signals" className="mt-4 space-y-4">
          <SignalQualitySection signalQuality={signalQuality} strategyTracker={strategyTracker} />
        </TabsContent>

        <TabsContent value="watchdog" className="mt-4 space-y-4">
          <WatchdogSection watchdog={watchdog} strategyTracker={strategyTracker} />
        </TabsContent>

        <TabsContent value="charts" className="mt-4 space-y-4">
          <ChartsSection ts={timeseries} pnlHistory={pnlHistory} />
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

function OverviewSection({ s, hasData, pnlHistory }) {
  return (
    <>
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <StatCard testId="stat-total-pnl" label="Total P&L" value={formatPnl(s.total_pnl)} format="pnl" />
        <StatCard testId="stat-win-rate" label="Win Rate" value={s.win_rate != null ? `${s.win_rate}%` : '—'} />
        <StatCard testId="stat-profit-factor" label="Profit Factor" value={s.profit_factor != null ? s.profit_factor.toFixed(2) : '—'} />
        <StatCard testId="stat-sharpe" label="Sharpe Ratio" value={s.sharpe_ratio != null ? s.sharpe_ratio.toFixed(3) : '—'} />
        <StatCard testId="stat-max-dd" label="Max Drawdown" value={s.max_drawdown != null ? `$${s.max_drawdown.toFixed(2)}` : '—'} />
        <StatCard testId="stat-expectancy" label="Expectancy" value={s.expectancy != null ? formatPnl(s.expectancy) : '—'} format="pnl" />
      </div>

      <PnlChart data={pnlHistory} testId="analytics-pnl-chart" />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SectionCard title="P&L Breakdown" testId="section-pnl-breakdown">
          <div className="space-y-0.5">
            <Metric label="Realized P&L" value={formatPnl(s.realized_pnl)} color={pnlColor(s.realized_pnl)} testId="metric-realized" />
            <Metric label="Unrealized P&L" value={formatPnl(s.unrealized_pnl)} color={pnlColor(s.unrealized_pnl)} testId="metric-unrealized" />
            <Metric label="Peak Equity" value={s.peak_equity != null ? `$${s.peak_equity.toFixed(2)}` : '—'} testId="metric-peak" />
            <Metric label="Current Drawdown" value={s.current_drawdown != null ? `$${s.current_drawdown.toFixed(2)}` : '—'} testId="metric-curr-dd" />
            <Metric label="Total Fees" value={s.total_fees != null ? `$${s.total_fees.toFixed(4)}` : '—'} testId="metric-fees" />
            <Metric label="Total Volume" value={s.total_volume != null ? `$${s.total_volume.toFixed(2)}` : '—'} testId="metric-volume" />
          </div>
        </SectionCard>
        <SectionCard title="Win/Loss Analysis" testId="section-winloss">
          <div className="space-y-0.5">
            <Metric label="Total Trades" value={formatNumber(s.trade_count)} testId="metric-trades" />
            <Metric label="Closing Trades" value={formatNumber(s.closing_trade_count)} testId="metric-closing" />
            <Metric label="Wins" value={formatNumber(s.win_count)} color="text-emerald-400" testId="metric-wins" />
            <Metric label="Losses" value={formatNumber(s.loss_count)} color="text-red-400" testId="metric-losses" />
            <Metric label="Avg Win" value={s.avg_win != null ? formatPnl(s.avg_win) : '—'} color="text-emerald-400" testId="metric-avg-win" />
            <Metric label="Avg Loss" value={s.avg_loss != null ? formatPnl(s.avg_loss) : '—'} color="text-red-400" testId="metric-avg-loss" />
            <Metric label="Win Streak" value={s.longest_win_streak} testId="metric-win-streak" />
            <Metric label="Loss Streak" value={s.longest_loss_streak} testId="metric-loss-streak" />
          </div>
        </SectionCard>
      </div>

      {!hasData && (
        <div className="text-center py-8 text-zinc-600 text-sm">
          Start the engine and generate trades to see analytics
        </div>
      )}
    </>
  );
}

function StrategiesSection({ strategies }) {
  const strats = Object.entries(strategies);
  if (!strats.length) {
    return <div className="text-center py-8 text-zinc-600 text-sm">No strategy data yet</div>;
  }

  const NAMES = { arb_scanner: 'Arb Scanner', crypto_sniper: 'Crypto Sniper' };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {strats.map(([id, m]) => (
        <SectionCard key={id} title={NAMES[id] || id} testId={`section-strat-${id}`}>
          <div className="space-y-0.5">
            <Metric label="P&L" value={formatPnl(m.pnl)} color={pnlColor(m.pnl)} testId={`strat-${id}-pnl`} />
            <Metric label="Trade Count" value={m.trade_count} testId={`strat-${id}-trades`} />
            <Metric label="Win Rate" value={m.win_rate != null ? `${m.win_rate}%` : '—'} testId={`strat-${id}-winrate`} />
            <Metric label="Profit Factor" value={m.profit_factor != null ? m.profit_factor.toFixed(2) : '—'} testId={`strat-${id}-pf`} />
            <Metric label="Expectancy" value={m.expectancy != null ? formatPnl(m.expectancy) : '—'} testId={`strat-${id}-exp`} />
            <Metric label="Sharpe" value={m.sharpe_ratio != null ? m.sharpe_ratio.toFixed(3) : '—'} testId={`strat-${id}-sharpe`} />
            <Metric label="Avg Edge" value={m.avg_edge_bps != null ? `${m.avg_edge_bps}bps` : '—'} testId={`strat-${id}-edge`} />
            <Metric label="Volume" value={m.total_volume != null ? `$${m.total_volume.toFixed(2)}` : '—'} testId={`strat-${id}-vol`} />
            <Metric label="Fees" value={m.total_fees != null ? `$${m.total_fees.toFixed(4)}` : '—'} testId={`strat-${id}-fees`} />
          </div>
        </SectionCard>
      ))}
    </div>
  );
}

function ExecutionSection({ eq }) {
  if (!eq) {
    return <div className="text-center py-8 text-zinc-600 text-sm">Loading execution data...</div>;
  }

  const reasons = Object.entries(eq.rejection_reasons || {}).sort((a, b) => b[1] - a[1]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <SectionCard title="Fill Quality" testId="section-fill-quality">
        <div className="space-y-0.5">
          <Metric label="Total Orders" value={eq.total_orders} testId="eq-total-orders" />
          <Metric label="Filled" value={eq.filled_count} testId="eq-filled" />
          <Metric label="Fill Ratio" value={eq.fill_ratio != null ? `${eq.fill_ratio}%` : '—'} testId="eq-fill-ratio" />
          <Metric label="Partial Fills" value={eq.partial_fill_count} testId="eq-partial" />
          <Metric label="Avg Latency" value={eq.avg_latency_ms != null ? `${eq.avg_latency_ms}ms` : '—'} testId="eq-latency" />
        </div>
      </SectionCard>
      <SectionCard title="Slippage & Rejections" testId="section-slippage">
        <div className="space-y-0.5">
          <Metric label="Avg Slippage" value={eq.avg_slippage_bps != null ? `${eq.avg_slippage_bps}bps` : '—'} testId="eq-avg-slip" />
          <Metric label="Max Slippage" value={eq.max_slippage_bps != null ? `${eq.max_slippage_bps}bps` : '—'} testId="eq-max-slip" />
          <Metric label="Rejected" value={eq.rejected_count} color="text-red-400" testId="eq-rejected" />
          <Metric label="Cancelled" value={eq.cancelled_count} testId="eq-cancelled" />
        </div>
        {reasons.length > 0 && (
          <div className="mt-3 pt-2 border-t border-zinc-800">
            <p className="text-[10px] text-zinc-600 mb-1.5">Top Rejection Reasons</p>
            {reasons.map(([reason, count]) => (
              <div key={reason} className="flex justify-between text-xs py-0.5">
                <span className="text-zinc-500">{reason.replace(/_/g, ' ')}</span>
                <Badge variant="secondary" className="text-[10px]">{count}</Badge>
              </div>
            ))}
          </div>
        )}
      </SectionCard>
    </div>
  );
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-xs shadow-xl">
      <p className="text-zinc-500 mb-1">{label}</p>
      {payload.map((p, i) => (
        <p key={i} className={p.value >= 0 ? 'text-emerald-400' : 'text-red-400'}>
          {p.name}: {typeof p.value === 'number' ? (p.value >= 0 ? '+' : '') + '$' + p.value.toFixed(2) : p.value}
        </p>
      ))}
    </div>
  );
}

function ChartsSection({ ts, pnlHistory }) {
  if (!ts) {
    return <div className="text-center py-8 text-zinc-600 text-sm">Loading chart data...</div>;
  }

  const dailyPnl = ts.daily_pnl || [];
  const drawdownCurve = ts.drawdown_curve || [];
  const tradeFreq = ts.trade_frequency || [];
  const hasChartData = dailyPnl.length > 0;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard testId="ts-rolling-7d" label="Rolling 7D P&L" value={ts.rolling_7d_pnl != null ? formatPnl(ts.rolling_7d_pnl) : '—'} format="pnl" />
        <StatCard testId="ts-rolling-30d" label="Rolling 30D P&L" value={ts.rolling_30d_pnl != null ? formatPnl(ts.rolling_30d_pnl) : '—'} format="pnl" />
        <StatCard testId="ts-days-traded" label="Days Traded" value={dailyPnl.length} />
        <StatCard testId="ts-avg-daily" label="Avg Daily P&L" value={dailyPnl.length > 0 ? formatPnl(dailyPnl.reduce((s, d) => s + d.pnl, 0) / dailyPnl.length) : '—'} format="pnl" />
      </div>

      <PnlChart data={pnlHistory} testId="charts-equity-curve" />

      {hasChartData && (
        <>
          <SectionCard title="Daily P&L" testId="section-daily-pnl">
            <ResponsiveContainer width="100%" height={180}>
              <BarChart data={dailyPnl} margin={{ top: 4, right: 8, bottom: 4, left: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: '#52525b', fontSize: 9 }} axisLine={{ stroke: '#27272a' }} tickLine={false} />
                <YAxis tick={{ fill: '#52525b', fontSize: 9 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v}`} width={44} />
                <Tooltip content={<ChartTooltip />} />
                <ReferenceLine y={0} stroke="#3f3f46" />
                <Bar dataKey="pnl" name="P&L" radius={[2, 2, 0, 0]}>
                  {dailyPnl.map((d, i) => (
                    <Cell key={i} fill={d.pnl >= 0 ? '#34d399' : '#f87171'} fillOpacity={0.7} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </SectionCard>

          <SectionCard title="Drawdown" testId="section-drawdown-chart">
            <ResponsiveContainer width="100%" height={140}>
              <AreaChart data={drawdownCurve} margin={{ top: 4, right: 8, bottom: 4, left: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: '#52525b', fontSize: 9 }} axisLine={{ stroke: '#27272a' }} tickLine={false} />
                <YAxis tick={{ fill: '#52525b', fontSize: 9 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v}`} width={44} />
                <Tooltip content={<ChartTooltip />} />
                <Area type="monotone" dataKey="drawdown" name="Drawdown" stroke="#f87171" fill="#f87171" fillOpacity={0.15} dot={false} isAnimationActive={false} />
              </AreaChart>
            </ResponsiveContainer>
          </SectionCard>

          <SectionCard title="Trade Frequency" testId="section-trade-freq">
            <ResponsiveContainer width="100%" height={140}>
              <BarChart data={tradeFreq} margin={{ top: 4, right: 8, bottom: 4, left: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
                <XAxis dataKey="date" tick={{ fill: '#52525b', fontSize: 9 }} axisLine={{ stroke: '#27272a' }} tickLine={false} />
                <YAxis tick={{ fill: '#52525b', fontSize: 9 }} axisLine={false} tickLine={false} width={30} />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="count" name="Trades" fill="#60a5fa" fillOpacity={0.5} radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </SectionCard>
        </>
      )}

      {!hasChartData && (
        <div className="text-center py-8 text-zinc-600 text-sm">
          Generate trades to see time-based charts
        </div>
      )}
    </div>
  );
}


function SignalQualitySection({ signalQuality, strategyTracker }) {
  const signals = signalQuality || {};
  const stPerf = (strategyTracker || {}).performance || {};
  const stSlots = (strategyTracker || {}).position_slots || {};

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Object.entries(signals).map(([strategy, data]) => (
          <SectionCard key={strategy} title={strategy.replace(/_/g, ' ').toUpperCase()} testId={`signal-quality-${strategy}`}>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-zinc-500">Signals Generated</span>
                <span className="text-zinc-300 font-mono">{data.signals_generated}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-zinc-500">Accepted</span>
                <span className="text-emerald-400 font-mono">{data.signals_accepted}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-zinc-500">Rejected</span>
                <span className="text-red-400 font-mono">{data.signals_rejected}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-zinc-500">Acceptance Rate</span>
                <span className={`font-mono ${data.acceptance_rate > 10 ? 'text-emerald-400' : 'text-amber-400'}`}>
                  {data.acceptance_rate}%
                </span>
              </div>

              {data.rejection_reasons && Object.keys(data.rejection_reasons).length > 0 && (
                <>
                  <div className="border-t border-zinc-800 pt-2 mt-2 text-zinc-500">Rejection Reasons:</div>
                  {Object.entries(data.rejection_reasons).sort(([,a],[,b]) => b - a).map(([reason, count]) => (
                    <div key={reason} className="flex justify-between pl-2">
                      <span className="text-zinc-500">{reason}</span>
                      <span className="text-zinc-400 font-mono">{count}</span>
                    </div>
                  ))}
                </>
              )}
            </div>
          </SectionCard>
        ))}
      </div>

      {/* Position Slots */}
      {stSlots.by_strategy && (
        <SectionCard title="Position Slots" testId="section-position-slots">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
            {[
              { name: 'Weather', count: stSlots.weather_count, limit: stSlots.limits?.max_weather, headroom: stSlots.headroom?.weather, size: stSlots.sizing?.weather },
              { name: 'Crypto', count: stSlots.crypto_count, limit: stSlots.limits?.max_crypto, headroom: stSlots.headroom?.crypto, size: stSlots.sizing?.crypto },
              { name: 'Arb', count: stSlots.arb_count, limit: stSlots.limits?.max_arb, headroom: stSlots.headroom?.arb, size: stSlots.sizing?.arb },
              { name: 'Global', count: stSlots.total, limit: stSlots.limits?.max_global, headroom: stSlots.headroom?.global, size: null },
            ].map((b) => (
              <div key={b.name} className="space-y-2">
                <div className="text-zinc-500 font-medium">{b.name}</div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Active</span>
                  <span className="text-zinc-300 font-mono">{b.count || 0} / {b.limit ?? '—'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Headroom</span>
                  <span className={`font-mono ${(b.headroom || 0) > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {b.headroom || 0}
                  </span>
                </div>
                {b.size != null && (
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Size</span>
                    <span className="text-zinc-300 font-mono">${b.size}</span>
                  </div>
                )}
              </div>
            ))}
          </div>
          {stSlots.by_strategy && Object.keys(stSlots.by_strategy).length > 0 && (
            <div className="mt-4 pt-3 border-t border-zinc-800">
              <div className="text-zinc-500 text-xs mb-2">Positions by Strategy:</div>
              <div className="flex flex-wrap gap-3">
                {Object.entries(stSlots.by_strategy).sort(([,a],[,b]) => b - a).map(([sid, cnt]) => (
                  <span key={sid} className="text-xs bg-zinc-800 px-2 py-1 rounded text-zinc-300">
                    {sid}: <span className="font-mono">{cnt}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
          {stSlots.blocked_by_position_limit && Object.keys(stSlots.blocked_by_position_limit).length > 0 && (
            <div className="mt-3 pt-3 border-t border-zinc-800">
              <div className="text-zinc-500 text-xs mb-2">Blocked by Position Limit:</div>
              <div className="flex gap-3">
                {Object.entries(stSlots.blocked_by_position_limit).map(([bucket, cnt]) => (
                  <span key={bucket} className="text-xs bg-red-900/30 px-2 py-1 rounded text-red-300">
                    {bucket}: <span className="font-mono">{cnt}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </SectionCard>
      )}
    </div>
  );
}

function WatchdogSection({ watchdog, strategyTracker }) {
  const wd = watchdog || {};
  const thresholds = wd.thresholds || {};

  const items = [
    {
      label: 'Last New Market',
      time: wd.last_new_market_at,
      minutes: wd.minutes_since_new_market,
      threshold: thresholds.no_market_alert_minutes,
    },
    {
      label: 'Last Trade Opened',
      time: wd.last_trade_opened_at,
      minutes: wd.minutes_since_trade_opened,
      threshold: thresholds.no_trade_open_alert_minutes,
    },
    {
      label: 'Last Trade Closed',
      time: wd.last_trade_closed_at,
      minutes: wd.minutes_since_trade_closed,
      threshold: thresholds.no_trade_close_alert_minutes,
    },
  ];

  return (
    <div className="space-y-4">
      <SectionCard title="Discovery Watchdog" testId="section-watchdog">
        <div className="space-y-4">
          {items.map((item) => {
            const overThreshold = item.minutes != null && item.threshold != null && item.minutes > item.threshold;
            return (
              <div key={item.label} className="flex justify-between items-center text-xs py-2 border-b border-zinc-800/50 last:border-0">
                <div>
                  <div className="text-zinc-300">{item.label}</div>
                  <div className="text-zinc-600 text-[10px] mt-0.5">
                    {item.time || 'Never'} | Threshold: {item.threshold || '—'} min
                  </div>
                </div>
                <div className="text-right">
                  {item.minutes != null ? (
                    <span className={`font-mono ${overThreshold ? 'text-red-400' : 'text-emerald-400'}`}>
                      {item.minutes.toFixed(0)} min ago
                    </span>
                  ) : (
                    <span className="text-zinc-600">N/A</span>
                  )}
                  {overThreshold && (
                    <div className="text-red-400 text-[10px] mt-0.5">ALERT</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </SectionCard>

      {/* Per-strategy performance from tracker */}
      {strategyTracker?.performance && Object.keys(strategyTracker.performance).length > 0 && (
        <SectionCard title="Strategy Performance (Tracker)" testId="section-tracker-perf">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {Object.entries(strategyTracker.performance).map(([sid, perf]) => (
              <div key={sid} className="bg-zinc-800/40 rounded p-3 text-xs space-y-1.5">
                <div className="text-zinc-200 font-medium">{sid.replace(/_/g, ' ').toUpperCase()}</div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Total P&L</span>
                  <span className={`font-mono ${perf.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    ${perf.total_pnl?.toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Trades</span>
                  <span className="text-zinc-300 font-mono">{perf.trade_count}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">Win Rate</span>
                  <span className={`font-mono ${perf.win_rate > 50 ? 'text-emerald-400' : 'text-amber-400'}`}>
                    {perf.win_rate}%
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-zinc-500">W/L</span>
                  <span className="text-zinc-300 font-mono">{perf.wins}/{perf.losses}</span>
                </div>
              </div>
            ))}
          </div>
        </SectionCard>
      )}
    </div>
  );
}


const STRATEGY_COLORS = {
  crypto: { bg: 'bg-sky-950/50', border: 'border-sky-800/40', accent: 'text-sky-400', label: 'CRYPTO' },
  weather: { bg: 'bg-amber-950/50', border: 'border-amber-800/40', accent: 'text-amber-400', label: 'WEATHER' },
  arb: { bg: 'bg-violet-950/50', border: 'border-violet-800/40', accent: 'text-violet-400', label: 'ARB' },
  resolver: { bg: 'bg-zinc-900/50', border: 'border-zinc-800/40', accent: 'text-zinc-400', label: 'RESOLVER' },
};

function StrategyComparisonSection({ attribution, strategyTracker, positionSummaries }) {
  const attr = attribution || {};
  const posSums = positionSummaries || {};
  const displayBuckets = ['crypto', 'weather', 'arb'];

  // Merge: prefer positionSummaries for unrealized/total as it uses live mark-to-market
  const merged = {};
  for (const b of displayBuckets) {
    const a = attr[b] || {};
    const p = posSums[b] || {};
    merged[b] = {
      ...a,
      unrealized_pnl: p.unrealized_pnl ?? a.unrealized_pnl ?? 0,
      total_pnl: p.total_pnl ?? a.total_pnl ?? 0,
      open_positions: p.open_positions ?? a.open_positions ?? 0,
      capital_allocated: p.capital_allocated ?? a.capital_allocated ?? 0,
    };
  }

  const rows = [
    { key: 'realized_pnl', label: 'Realized PnL', fmt: (v) => <PnlValue v={v} />, important: true },
    { key: 'unrealized_pnl', label: 'Unrealized PnL', fmt: (v) => <PnlValue v={v} />, important: true },
    { key: 'total_pnl', label: 'Total PnL', fmt: (v) => <PnlValue v={v} />, important: true },
    { key: 'open_positions', label: 'Open Positions', fmt: (v) => <span className="text-zinc-300 font-mono">{v}</span>, important: true },
    { key: 'trade_count', label: 'Closed Trades', fmt: (v) => <span className="text-zinc-300 font-mono">{v}</span> },
    { key: 'win_rate', label: 'Win Rate', fmt: (v) => <span className={`font-mono ${v > 55 ? 'text-emerald-400' : v > 45 ? 'text-amber-400' : v > 0 ? 'text-red-400' : 'text-zinc-500'}`}>{v > 0 ? `${v}%` : '—'}</span> },
    { key: 'avg_pnl_per_trade', label: 'Avg PnL/Trade', fmt: (v) => <PnlValue v={v} /> },
    { key: 'capital_allocated', label: 'Capital Deployed', fmt: (v) => <span className="text-zinc-300 font-mono">${v}</span> },
    { key: 'best_trade', label: 'Best Trade', fmt: (v) => <PnlValue v={v} /> },
    { key: 'worst_trade', label: 'Worst Trade', fmt: (v) => <PnlValue v={v} /> },
  ];

  const ranked = displayBuckets
    .filter(b => merged[b])
    .sort((a, b) => (merged[b]?.total_pnl || 0) - (merged[a]?.total_pnl || 0));

  return (
    <div className="space-y-5">
      {/* Strategy cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {displayBuckets.map((bucket) => {
          const s = merged[bucket] || {};
          const c = STRATEGY_COLORS[bucket] || STRATEGY_COLORS.resolver;
          const isTop = ranked[0] === bucket && ((s.trade_count || 0) + (s.open_positions || 0)) > 0;
          return (
            <div key={bucket} data-testid={`strategy-card-${bucket}`}
              className={`rounded-lg border p-4 space-y-3 ${c.bg} ${c.border} ${isTop ? 'ring-1 ring-emerald-500/30' : ''}`}>
              <div className="flex items-center justify-between">
                <span className={`text-sm font-semibold ${c.accent}`}>{c.label}</span>
                {isTop && <span className="text-[10px] bg-emerald-900/60 text-emerald-300 px-1.5 py-0.5 rounded">TOP</span>}
              </div>
              {/* PnL breakdown */}
              <div className="py-2 space-y-1">
                <div className="flex justify-between items-baseline">
                  <span className="text-[10px] text-zinc-500">Total</span>
                  <span className="text-xl font-bold font-mono">
                    <PnlValue v={s.total_pnl || 0} large />
                  </span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-zinc-500">Realized</span>
                  <PnlValue v={s.realized_pnl || 0} />
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-zinc-500">Unrealized</span>
                  <PnlValue v={s.unrealized_pnl || 0} />
                </div>
              </div>
              {/* Key metrics */}
              <div className="space-y-1.5 text-xs pt-2 border-t border-zinc-800/50">
                <Row label="Open" value={s.open_positions || 0} />
                <Row label="Closed" value={s.trade_count || 0} />
                <Row label="W/L" value={`${s.wins || 0}/${s.losses || 0}`} />
                {s.win_rate > 0 && <Row label="Win Rate" value={`${s.win_rate}%`} color={s.win_rate > 55 ? 'text-emerald-400' : 'text-amber-400'} />}
                <Row label="Capital" value={`$${s.capital_allocated || 0}`} />
              </div>
            </div>
          );
        })}
      </div>

      {/* Comparison table */}
      <SectionCard title="Strategy Comparison" testId="section-strategy-comparison-table">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-zinc-500 border-b border-zinc-800">
                <th className="text-left p-2 w-40">Metric</th>
                {displayBuckets.map(b => (
                  <th key={b} className={`text-right p-2 ${(STRATEGY_COLORS[b] || {}).accent || 'text-zinc-400'}`}>
                    {(STRATEGY_COLORS[b] || {}).label || b.toUpperCase()}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key} className={`border-b border-zinc-800/30 ${row.important ? 'bg-zinc-800/20' : ''}`}>
                  <td className={`p-2 ${row.important ? 'text-zinc-200 font-medium' : 'text-zinc-500'}`}>{row.label}</td>
                  {displayBuckets.map(b => (
                    <td key={b} className="p-2 text-right">
                      {row.fmt((merged[b] || {})[row.key] ?? 0)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}

function Row({ label, value, color }) {
  return (
    <div className="flex justify-between">
      <span className="text-zinc-500">{label}</span>
      <span className={`font-mono ${color || 'text-zinc-300'}`}>{value}</span>
    </div>
  );
}

function PnlValue({ v, large }) {
  if (v == null || v === 0) return <span className={`font-mono text-zinc-500 ${large ? 'text-2xl' : ''}`}>$0.00</span>;
  const sign = v >= 0 ? '+' : '';
  const color = v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-zinc-500';
  return <span className={`font-mono ${color} ${large ? '' : ''}`}>{sign}${v.toFixed(2)}</span>;
}

function ControlsSection({ controls }) {
  const c = controls || {};
  const limits = c.limits_status || {};

  return (
    <div className="space-y-5">
      {/* Mode Banner */}
      <div data-testid="mode-banner" className={`rounded-lg border p-4 flex items-center gap-4
        ${c.mode === 'paper' ? 'bg-amber-950/30 border-amber-800/40' : 'bg-red-950/40 border-red-600/50'}`}>
        <div className={`w-3 h-3 rounded-full ${c.mode === 'paper' ? 'bg-amber-500' : 'bg-red-500'} animate-pulse`} />
        <div>
          <div className={`text-sm font-bold ${c.mode === 'paper' ? 'text-amber-300' : 'text-red-300'}`}>
            {(c.mode || 'paper').toUpperCase()} MODE
          </div>
          <div className="text-xs text-zinc-500 mt-0.5">
            {c.mode === 'paper' ? 'Simulated execution — no real funds at risk' : 'LIVE — real orders will be placed'}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* Kill Switch */}
        <SectionCard title="Kill Switch" testId="section-kill-switch">
          <div className="flex items-center gap-3 py-3">
            <div className={`w-4 h-4 rounded-full ${c.kill_switch_active ? 'bg-red-500 animate-pulse' : 'bg-emerald-500'}`} />
            <span className={`text-sm font-semibold ${c.kill_switch_active ? 'text-red-400' : 'text-emerald-400'}`}>
              {c.kill_switch_active ? 'ACTIVE — All trading halted' : 'INACTIVE — Trading enabled'}
            </span>
          </div>
        </SectionCard>

        {/* Daily PnL Status */}
        <SectionCard title="Daily PnL" testId="section-daily-pnl">
          <div className="space-y-2 text-xs">
            <div className="flex justify-between">
              <span className="text-zinc-500">Current Daily PnL</span>
              <span className={`font-mono font-bold ${(c.daily_pnl || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                ${(c.daily_pnl || 0).toFixed(2)}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">Max Daily Loss</span>
              <span className="text-zinc-300 font-mono">${c.max_daily_loss}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-zinc-500">Loss Remaining</span>
              <span className={`font-mono ${(limits.daily_loss_remaining || 0) > 20 ? 'text-emerald-400' : 'text-amber-400'}`}>
                ${(limits.daily_loss_remaining || 0).toFixed(2)}
              </span>
            </div>
            {/* Progress bar */}
            <div className="h-1.5 bg-zinc-800 rounded-full mt-2">
              <div
                className={`h-full rounded-full transition-all ${(limits.daily_loss_remaining || 0) > 20 ? 'bg-emerald-500' : 'bg-amber-500'}`}
                style={{ width: `${Math.max(0, Math.min(100, ((limits.daily_loss_remaining || 0) / Math.max(c.max_daily_loss || 1, 1)) * 100))}%` }}
              />
            </div>
          </div>
        </SectionCard>
      </div>

      {/* Risk Limits */}
      <SectionCard title="Risk Limits" testId="section-risk-limits">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
          {[
            { label: 'Max Exposure', value: `$${c.max_market_exposure || 0}`, current: `$${(c.total_exposure || 0).toFixed(0)}` },
            { label: 'Max Order Size', value: `$${c.max_order_size || 0}` },
            { label: 'Max Position Size', value: `$${c.max_position_size || 0}` },
            { label: 'Max Concurrent', value: c.max_concurrent_positions || 0 },
          ].map(item => (
            <div key={item.label} className="bg-zinc-800/40 rounded p-3 space-y-1.5">
              <div className="text-zinc-500">{item.label}</div>
              <div className="text-zinc-200 font-mono font-semibold">{item.value}</div>
              {item.current && <div className="text-zinc-500 text-[10px]">Current: {item.current}</div>}
            </div>
          ))}
        </div>
      </SectionCard>

      {/* Exposure Bar */}
      <SectionCard title="Exposure" testId="section-exposure">
        <div className="space-y-2 text-xs">
          <div className="flex justify-between">
            <span className="text-zinc-500">Current Exposure</span>
            <span className="text-zinc-300 font-mono">${(c.total_exposure || 0).toFixed(2)} / ${c.max_market_exposure || 0}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-zinc-500">Remaining</span>
            <span className={`font-mono ${(limits.exposure_remaining || 0) > 20 ? 'text-emerald-400' : 'text-amber-400'}`}>
              ${(limits.exposure_remaining || 0).toFixed(2)}
            </span>
          </div>
          <div className="h-1.5 bg-zinc-800 rounded-full mt-2">
            <div
              className="h-full bg-sky-500 rounded-full transition-all"
              style={{ width: `${Math.max(0, Math.min(100, ((c.total_exposure || 0) / Math.max(c.max_market_exposure || 1, 1)) * 100))}%` }}
            />
          </div>
        </div>
      </SectionCard>
    </div>
  );
}
