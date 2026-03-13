import { useMemo } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';

function CustomTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-xs shadow-xl">
      <p className="text-zinc-500 mb-1">{formatChartTime(d.timestamp)}</p>
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
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
}

export function PnlChart({ data, testId }) {
  const { points, current_pnl, peak_pnl, trough_pnl, max_drawdown, total_trades } = data;

  const isPositive = current_pnl >= 0;
  const strokeColor = isPositive ? '#34d399' : '#f87171';
  const gradientId = 'pnl-gradient';

  const yDomain = useMemo(() => {
    if (!points.length) return [-1, 1];
    const vals = points.map((p) => p.cumulative_pnl);
    const min = Math.min(0, ...vals);
    const max = Math.max(0, ...vals);
    const pad = Math.max(Math.abs(max - min) * 0.15, 0.5);
    return [min - pad, max + pad];
  }, [points]);

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
        <h3 className="text-sm font-medium text-zinc-300">P&L Curve</h3>
        <div className="flex items-center gap-4 text-xs font-mono">
          <span className="text-zinc-600">Peak <span className="text-emerald-400">{peak_pnl >= 0 ? '+' : ''}${peak_pnl.toFixed(2)}</span></span>
          <span className="text-zinc-600">Trough <span className="text-red-400">{trough_pnl >= 0 ? '+' : ''}${trough_pnl.toFixed(2)}</span></span>
          <span className="text-zinc-600">DD <span className="text-amber-400">${max_drawdown.toFixed(2)}</span></span>
          <span className={`font-semibold ${isPositive ? 'text-emerald-400' : 'text-red-400'}`}>
            {current_pnl >= 0 ? '+' : ''}${current_pnl.toFixed(2)}
          </span>
        </div>
      </div>
      <div className="p-3">
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={points} margin={{ top: 4, right: 8, bottom: 4, left: 4 }}>
            <defs>
              <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={strokeColor} stopOpacity={0.25} />
                <stop offset="100%" stopColor={strokeColor} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
            <XAxis
              dataKey="timestamp"
              tickFormatter={formatChartTime}
              tick={{ fill: '#52525b', fontSize: 10 }}
              axisLine={{ stroke: '#27272a' }}
              tickLine={false}
              minTickGap={50}
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
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
