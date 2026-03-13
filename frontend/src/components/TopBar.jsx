import { useDashboardStore } from '../state/dashboardStore';
import { useApi } from '../hooks/useApi';
import { formatUptime } from '../utils/formatters';
import { ENGINE_STATUS_COLORS } from '../utils/constants';
import { Button } from './ui/button';
import { Play, Square, Zap, Wallet, ShieldAlert } from 'lucide-react';
import { toast } from 'sonner';

const MODE_COLORS = {
  paper: 'text-zinc-300',
  shadow: 'text-amber-400',
  live: 'text-red-400',
};

export function TopBar() {
  const status = useDashboardStore((s) => s.status);
  const mode = useDashboardStore((s) => s.mode);
  const uptime = useDashboardStore((s) => s.uptime);
  const killSwitch = useDashboardStore((s) => s.risk?.kill_switch_active);
  const wallet = useDashboardStore((s) => s.walletStatus);
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

  const hasWarnings = wallet.warnings && wallet.warnings.length > 0;

  return (
    <header data-testid="top-bar" className="h-12 border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-sm flex items-center justify-between px-5 shrink-0">
      <div className="flex items-center gap-4 text-xs">
        <span className="text-zinc-500">Engine</span>
        <span className={`font-medium ${ENGINE_STATUS_COLORS[status]}`}>{status.toUpperCase()}</span>
        <span className="text-zinc-700">|</span>
        <span className="text-zinc-500">Mode</span>
        <span data-testid="mode-indicator" className={`uppercase font-semibold ${MODE_COLORS[mode] || 'text-zinc-300'}`}>
          {mode}
          {mode === 'live' && <span className="ml-1 inline-block h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse" />}
        </span>
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
      <div className="flex items-center gap-3">
        {/* Wallet / Live Status */}
        <div data-testid="wallet-widget" className="flex items-center gap-2 text-xs">
          {wallet.authenticated && wallet.balance_usdc !== null && (
            <span className="flex items-center gap-1 text-zinc-400 font-mono">
              <Wallet size={11} />
              ${wallet.balance_usdc?.toFixed(2) ?? '—'}
            </span>
          )}
          {hasWarnings && (
            <span className="flex items-center gap-1 text-amber-400" title={wallet.warnings.join('; ')}>
              <ShieldAlert size={12} />
            </span>
          )}
        </div>
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
