import { useEffect, useMemo } from 'react';
import { useDashboardStore } from '../state/dashboardStore';
import { useApi } from '../hooks/useApi';
import { SectionCard } from '../components/SectionCard';
import { HealthBadge } from '../components/HealthBadge';
import { Button } from '../components/ui/button';
import { formatPnl, formatTimeAgo } from '../utils/formatters';
import { ShieldCheck, Zap, ZapOff, AlertTriangle } from 'lucide-react';
import { toast } from 'sonner';

export default function Risk() {
  const risk = useDashboardStore((s) => s.risk);
  const stats = useDashboardStore((s) => s.stats);
  const positions = useDashboardStore((s) => s.positions);
  const components = useDashboardStore((s) => s.components);
  const strategies = useDashboardStore((s) => s.strategies);
  const status = useDashboardStore((s) => s.status);
  const { activateKillSwitch, deactivateKillSwitch, fetchPositions } = useApi();

  useEffect(() => {
    fetchPositions();
    const interval = setInterval(fetchPositions, 8000);
    return () => clearInterval(interval);
  }, [fetchPositions]);

  const totalExposure = useMemo(
    () => positions.reduce((sum, p) => sum + p.size * p.current_price, 0),
    [positions]
  );

  const exposurePct = risk.max_market_exposure ? (totalExposure / risk.max_market_exposure) * 100 : 0;
  const positionPct = risk.max_concurrent_positions ? (stats.open_positions / risk.max_concurrent_positions) * 100 : 0;
  const lossUsed = risk.max_daily_loss ? (Math.abs(Math.min(stats.daily_pnl, 0)) / risk.max_daily_loss) * 100 : 0;
  const health = stats.health || {};

  const handleKillSwitch = async () => {
    try {
      if (risk.kill_switch_active) {
        await deactivateKillSwitch();
        toast.success('Kill switch deactivated');
      } else {
        await activateKillSwitch();
        toast.warning('Kill switch ACTIVATED — all orders blocked');
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Kill switch action failed');
    }
  };

  const alerts = useMemo(() => {
    const a = [];
    if (risk.kill_switch_active) a.push({ level: 'critical', msg: 'Kill switch is ACTIVE — all trading halted' });
    if (exposurePct > 80) a.push({ level: 'warning', msg: `Exposure at ${exposurePct.toFixed(0)}% of limit` });
    if (lossUsed > 80) a.push({ level: 'warning', msg: `Daily loss at ${lossUsed.toFixed(0)}% of limit` });
    if (positionPct > 80) a.push({ level: 'warning', msg: `Position slots at ${positionPct.toFixed(0)}% capacity` });
    if (health.market_data_stale) a.push({ level: 'info', msg: 'Market data feed is stale' });
    if (health.spot_btc_stale) a.push({ level: 'info', msg: 'BTC spot feed is stale' });
    if (health.spot_eth_stale) a.push({ level: 'info', msg: 'ETH spot feed is stale' });
    return a;
  }, [risk, exposurePct, lossUsed, positionPct, health]);

  const barColor = (pct) => pct > 80 ? 'bg-red-500' : pct > 50 ? 'bg-amber-500' : 'bg-emerald-500';

  return (
    <div data-testid="risk-page" className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-zinc-100">Risk Monitor</h1>
        <Button
          data-testid="kill-switch-btn"
          size="sm"
          variant={risk.kill_switch_active ? 'default' : 'destructive'}
          onClick={handleKillSwitch}
          className="h-8 text-xs px-4"
        >
          {risk.kill_switch_active ? (
            <><ZapOff size={14} className="mr-1.5" /> Deactivate Kill Switch</>
          ) : (
            <><Zap size={14} className="mr-1.5" /> Activate Kill Switch</>
          )}
        </Button>
      </div>

      {/* Kill Switch Banner */}
      {risk.kill_switch_active && (
        <div data-testid="kill-switch-banner" className="bg-red-950/50 border border-red-900 rounded-lg px-4 py-3 flex items-center gap-3">
          <Zap size={20} className="text-red-400 shrink-0" />
          <div>
            <p className="text-sm font-medium text-red-300">Kill Switch Active</p>
            <p className="text-xs text-red-400/80">All order submissions are blocked. Trading is halted until deactivated.</p>
          </div>
        </div>
      )}

      {/* Risk Gauges */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <SectionCard title="Exposure" testId="section-exposure">
          <div className="space-y-3">
            <div className="flex justify-between text-xs">
              <span className="text-zinc-500">Total Exposure</span>
              <span className="text-zinc-300 font-mono">${totalExposure.toFixed(2)} / ${risk.max_market_exposure}</span>
            </div>
            <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
              <div className={`h-full rounded-full transition-all ${barColor(exposurePct)}`} style={{ width: `${Math.min(exposurePct, 100)}%` }} />
            </div>
            <div className="text-right text-xs text-zinc-500">{exposurePct.toFixed(1)}%</div>
          </div>
        </SectionCard>

        <SectionCard title="Position Slots" testId="section-position-slots">
          <div className="space-y-3">
            <div className="flex justify-between text-xs">
              <span className="text-zinc-500">Open Positions</span>
              <span className="text-zinc-300 font-mono">{stats.open_positions} / {risk.max_concurrent_positions}</span>
            </div>
            <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
              <div className={`h-full rounded-full transition-all ${barColor(positionPct)}`} style={{ width: `${Math.min(positionPct, 100)}%` }} />
            </div>
            <div className="text-right text-xs text-zinc-500">{positionPct.toFixed(1)}%</div>
          </div>
        </SectionCard>

        <SectionCard title="Daily Loss Limit" testId="section-daily-loss">
          <div className="space-y-3">
            <div className="flex justify-between text-xs">
              <span className="text-zinc-500">Daily P&L</span>
              <span className="text-zinc-300 font-mono">{formatPnl(stats.daily_pnl)} / -${risk.max_daily_loss}</span>
            </div>
            <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
              <div className={`h-full rounded-full transition-all ${barColor(lossUsed)}`} style={{ width: `${Math.min(lossUsed, 100)}%` }} />
            </div>
            <div className="text-right text-xs text-zinc-500">{lossUsed.toFixed(1)}% used</div>
          </div>
        </SectionCard>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {/* Alerts */}
        <SectionCard title="Risk Alerts" testId="section-risk-alerts">
          {alerts.length === 0 ? (
            <div className="flex items-center gap-2 text-xs text-emerald-400 py-2">
              <ShieldCheck size={16} />
              <span>All risk parameters within normal bounds</span>
            </div>
          ) : (
            <div className="space-y-2">
              {alerts.map((a, i) => (
                <div key={i} className={`flex items-center gap-2 text-xs py-1 ${
                  a.level === 'critical' ? 'text-red-400' : a.level === 'warning' ? 'text-amber-400' : 'text-zinc-400'
                }`}>
                  <AlertTriangle size={14} className="shrink-0" />
                  <span>{a.msg}</span>
                </div>
              ))}
            </div>
          )}
        </SectionCard>

        {/* Risk Limits */}
        <SectionCard title="Risk Configuration" testId="section-risk-config">
          <div className="space-y-2 text-xs">
            {[
              ['Max Daily Loss', `$${risk.max_daily_loss}`],
              ['Max Loss Per Strategy', `$${risk.max_loss_per_strategy}`],
              ['Max Position Size', risk.max_position_size],
              ['Max Market Exposure', `$${risk.max_market_exposure}`],
              ['Max Concurrent Positions', risk.max_concurrent_positions],
              ['Max Order Size', risk.max_order_size],
            ].map(([label, val]) => (
              <div key={label} className="flex justify-between">
                <span className="text-zinc-500">{label}</span>
                <span className="text-zinc-300 font-mono">{val ?? '—'}</span>
              </div>
            ))}
          </div>
        </SectionCard>

        {/* Component Health */}
        <SectionCard title="Component Health" testId="section-component-health">
          <div className="space-y-2">
            {components.length === 0 ? (
              <p className="text-xs text-zinc-600">Engine not started — no component data</p>
            ) : (
              components.map((c) => (
                <div key={c.name} className="flex items-center justify-between text-xs">
                  <span className="text-zinc-400">{c.name}</span>
                  <div className="flex items-center gap-3">
                    <HealthBadge status={c.status} />
                    {c.last_heartbeat && (
                      <span className="text-zinc-600">{formatTimeAgo(c.last_heartbeat)}</span>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </SectionCard>

        {/* Strategy Health */}
        <SectionCard title="Strategy Health" testId="section-strategy-health">
          <div className="space-y-2">
            {strategies.length === 0 ? (
              <p className="text-xs text-zinc-600">No strategies registered</p>
            ) : (
              strategies.map((s) => (
                <div key={s.strategy_id} className="flex items-center justify-between text-xs">
                  <span className="text-zinc-400">{s.name}</span>
                  <HealthBadge status={s.enabled ? s.status : 'stopped'} label={s.enabled ? s.status : 'disabled'} />
                </div>
              ))
            )}
          </div>
        </SectionCard>
      </div>
    </div>
  );
}
