import { useMemo, useState, useRef, useCallback } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Brush,
} from 'recharts';

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-xs shadow-xl">
      <p className="text-zinc-500 mb-1">{formatChartDate(d.timestamp)} UTC</p>
      <p className={d.cumulative_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}>
        P&L: {d.cumulative_pnl >= 0 ? '+' : ''}${d.cumulative_pnl.toFixed(2)}
      </p>
      {d.trade_pnl !== 0 && (
        <p className={d.trade_pnl >= 0 ? 'text-emerald-500/70' : 'text-red-500/70'}>
          Trade: {d.trade_pnl >= 0 ? '+' : ''}${d.trade_pnl.toFixed(2)}
        </p>
      )}
      {d.strategy && <p className="text-zinc-600 mt-0.5">{d.strategy}</p>}
    </div>
  );
}

function formatChartTime(isoString) {
  if (!isoString) return '';
  const d = new Date(isoString);
  if (isNaN(d.getTime())) return '';
  // Always show in UTC so it matches Telegram / server timestamps
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
  return `${hh}:${mm}`;
}

function formatChartDate(isoString) {
  if (!isoString) return '';
  const d = new Date(isoString);
  if (isNaN(d.getTime())) return '';
  const mon = String(d.getUTCMonth() + 1).padStart(2, '0');
  const day = String(d.getUTCDate()).padStart(2, '0');
  const hh = String(d.getUTCHours()).padStart(2, '0');
  const mm = String(d.getUTCMinutes()).padStart(2, '0');
  return `${mon}/${day} ${hh}:${mm}`;
}

function buildTickFormatter(points) {
  if (!points || points.length < 2) return formatChartTime;
  const first = new Date(points[0].timestamp);
  const last = new Date(points[points.length - 1].timestamp);
  // If range spans more than 18 hours, show date + time
  if (last - first > 18 * 3600_000) return formatChartDate;
  return formatChartTime;
}

export function PnlChart({ data, testId }) {
  const { points, current_pnl, peak_pnl, trough_pnl, max_drawdown, total_trades, latest_close_at, server_time } = data;
  const [viewRange, setViewRange] = useState('recent'); // 'recent' | 'all'

  const isPositive = current_pnl >= 0;
  const strokeColor = isPositive ? '#34d399' : '#f87171';
  const gradientId = 'pnl-gradient';

  const tickFormatter = useMemo(() => buildTickFormatter(points), [points]);

  // Default to showing the recent ~30% of data for easier inspection
  const brushDefault = useMemo(() => {
    if (!points.length) return { start: 0, end: 0 };
    if (viewRange === 'all') return { start: 0, end: points.length - 1 };
    const recentStart = Math.max(0, Math.floor(points.length * 0.7));
    return { start: recentStart, end: points.length - 1 };
  }, [points, viewRange]);

  const yDomain = useMemo(() => {
    if (!points.length) return [-1, 1];
    const vals = points.map((p) => p.cumulative_pnl);
    const min = Math.min(0, ...vals);
    const max = Math.max(0, ...vals);
    const pad = Math.max(Math.abs(max - min) * 0.15, 0.5);
    return [min - pad, max + pad];
  }, [points]);

  const lastCloseLabel = useMemo(() => {
    if (!latest_close_at) return null;
    return formatChartDate(latest_close_at) + ' UTC';
  }, [latest_close_at]);

  if (!points.length) {
    return (
      <div data-testid={testId} className="bg-zinc-900/40 border border-zinc-800 rounded-lg">
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <h3 className="text-sm font-medium text-zinc-300">P&L Curve</h3>
        </div>
        <div className="flex items-center justify-center h-48 text-zinc-600 text-xs">
          No trades yet — start the engine to see your equity curve
        </div>
      </div>
    );
  }

  return (
    <div data-testid={testId} className="bg-zinc-900/40 border border-zinc-800 rounded-lg">
      <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-medium text-zinc-300">P&L Curve</h3>
          {lastCloseLabel && (
            <span className="text-[10px] font-mono text-zinc-600">
              last close {lastCloseLabel}
            </span>
          )}
        </div>
        <div className="flex items-center gap-4 text-xs font-mono">
          {/* View range toggle */}
          <div className="flex items-center gap-1 mr-2">
            <button
              data-testid="pnl-chart-recent"
              onClick={() => setViewRange('recent')}
              className={`px-2 py-0.5 rounded text-[10px] transition-colors ${
                viewRange === 'recent'
                  ? 'bg-zinc-700 text-zinc-200'
                  : 'text-zinc-500 hover:text-zinc-400'
              }`}
            >
              Recent
            </button>
            <button
              data-testid="pnl-chart-all"
              onClick={() => setViewRange('all')}
              className={`px-2 py-0.5 rounded text-[10px] transition-colors ${
                viewRange === 'all'
                  ? 'bg-zinc-700 text-zinc-200'
                  : 'text-zinc-500 hover:text-zinc-400'
              }`}
            >
              All
            </button>
          </div>
          <span className="text-zinc-600">Peak <span className="text-emerald-400">{peak_pnl >= 0 ? '+' : ''}${peak_pnl.toFixed(2)}</span></span>
          <span className="text-zinc-600">Trough <span className="text-red-400">{trough_pnl >= 0 ? '+' : ''}${trough_pnl.toFixed(2)}</span></span>
          <span className="text-zinc-600">DD <span className="text-amber-400">${max_drawdown.toFixed(2)}</span></span>
          <span className={`font-semibold ${isPositive ? 'text-emerald-400' : 'text-red-400'}`}>
            {current_pnl >= 0 ? '+' : ''}${current_pnl.toFixed(2)}
          </span>
        </div>
      </div>
      <div className="p-3">
        <ResponsiveContainer width="100%" height={260}>
          <AreaChart data={points} margin={{ top: 4, right: 8, bottom: 24, left: 4 }}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={strokeColor} stopOpacity={0.25} />
                <stop offset="100%" stopColor={strokeColor} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
            <XAxis
              dataKey="timestamp"
              tickFormatter={tickFormatter}
              tick={{ fill: '#52525b', fontSize: 10 }}
              axisLine={{ stroke: '#27272a' }}
              tickLine={false}
              minTickGap={40}
            />
            <YAxis
              domain={yDomain}
              tick={{ fill: '#52525b', fontSize: 10 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v) => `$${v.toFixed(0)}`}
              width={48}
            />
            <Tooltip content={<CustomTooltip />} />
            <ReferenceLine y={0} stroke="#3f3f46" strokeDasharray="4 2" />
            <Area
              type="monotone"
              dataKey="cumulative_pnl"
              stroke={strokeColor}
              strokeWidth={1.5}
              fill={`url(#${gradientId})`}
              dot={false}
              activeDot={{ r: 3, fill: strokeColor, stroke: '#18181b', strokeWidth: 2 }}
              isAnimationActive={false}
            />
            {points.length > 20 && (
              <Brush
                dataKey="timestamp"
                height={20}
                stroke="#3f3f46"
                fill="#18181b"
                tickFormatter={tickFormatter}
                startIndex={brushDefault.start}
                endIndex={brushDefault.end}
                travellerWidth={8}
              >
                <AreaChart data={points}>
                  <Area
                    type="monotone"
                    dataKey="cumulative_pnl"
                    stroke={strokeColor}
                    strokeWidth={0.5}
                    fill={`url(#${gradientId})`}
                    dot={false}
                    isAnimationActive={false}
                  />
                </AreaChart>
              </Brush>
            )}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
