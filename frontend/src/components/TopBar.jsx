import { useDashboardStore } from '../state/dashboardStore';
import { useApi } from '../hooks/useApi';
import { formatUptime } from '../utils/formatters';
import { ENGINE_STATUS_COLORS } from '../utils/constants';
import { Button } from './ui/button';
import { Play, Square, Zap } from 'lucide-react';
import { toast } from 'sonner';

export function TopBar() {
  const status = useDashboardStore((s) => s.status);
  const mode = useDashboardStore((s) => s.mode);
  const uptime = useDashboardStore((s) => s.uptime);
  const killSwitch = useDashboardStore((s) => s.risk?.kill_switch_active);
  const { startEngine, stopEngine } = useApi();

  const handleToggleEngine = async () => {
    try {
      if (status === 'running') {
        await stopEngine();
        toast.success('Engine stopped');
      } else {
        await startEngine();
        toast.success('Engine started');
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Engine action failed');
    }
  };

  return (
    <header data-testid="top-bar" className="h-12 border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-sm flex items-center justify-between px-5 shrink-0">
      <div className="flex items-center gap-4 text-xs">
        <span className="text-zinc-500">Engine</span>
        <span className={`font-medium ${ENGINE_STATUS_COLORS[status]}`}>{status.toUpperCase()}</span>
        <span className="text-zinc-700">|</span>
        <span className="text-zinc-500">Mode</span>
        <span className="text-zinc-300 uppercase font-medium">{mode}</span>
        {status === 'running' && (
          <>
            <span className="text-zinc-700">|</span>
            <span className="text-zinc-500">Uptime</span>
            <span className="text-zinc-300 font-mono">{formatUptime(uptime)}</span>
          </>
        )}
        {killSwitch && (
          <>
            <span className="text-zinc-700">|</span>
            <span className="text-red-400 font-medium flex items-center gap-1">
              <Zap size={12} /> KILL SWITCH
            </span>
          </>
        )}
      </div>
      <div className="flex items-center gap-2">
        <Button
          data-testid="engine-toggle-btn"
          size="sm"
          variant={status === 'running' ? 'destructive' : 'default'}
          onClick={handleToggleEngine}
          disabled={status === 'starting' || status === 'stopping'}
          className="h-7 text-xs px-3"
        >
          {status === 'running' ? (
            <><Square size={12} className="mr-1" /> Stop</>
          ) : (
            <><Play size={12} className="mr-1" /> Start</>
          )}
        </Button>
      </div>
    </header>
  );
}
