export function StatCard({ label, value, sub, format, testId }) {
  let colorClass = 'text-zinc-100';
  if (format === 'pnl' && typeof value === 'string') {
    if (value.startsWith('+') && value !== '+$0.00') colorClass = 'text-emerald-400';
    else if (value.startsWith('-')) colorClass = 'text-red-400';
    else colorClass = 'text-zinc-400';
  }
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
