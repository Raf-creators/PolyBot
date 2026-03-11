import { pnlColor } from '../utils/formatters';

export function StatCard({ label, value, sub, format, testId }) {
  const colorClass = format === 'pnl' ? pnlColor(typeof value === 'number' ? value : 0) : 'text-zinc-100';
  return (
    <div data-testid={testId} className="bg-zinc-900/60 border border-zinc-800 rounded-lg px-4 py-3">
      <div className="text-xs text-zinc-500 mb-1">{label}</div>
      <div className={`text-lg font-semibold font-mono leading-tight ${colorClass}`}>
        {value ?? '—'}
      </div>
      {sub && <div className="text-xs text-zinc-500 mt-1">{sub}</div>}
    </div>
  );
}
