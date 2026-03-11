import { ENGINE_STATUS_COLORS } from '../utils/constants';

export function HealthBadge({ status, label }) {
  const color = ENGINE_STATUS_COLORS[status] || 'text-zinc-500';
  const dotColor = status === 'running' ? 'bg-emerald-500' : status === 'error' ? 'bg-red-500' : 'bg-zinc-600';
  return (
    <span className={`inline-flex items-center gap-1.5 text-xs ${color}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${dotColor}`} />
      {label || status}
    </span>
  );
}
