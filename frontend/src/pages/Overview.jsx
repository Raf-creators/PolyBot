import { useEffect, useMemo } from 'react';
import { useDashboardStore } from '../state/dashboardStore';
import { useApi } from '../hooks/useApi';
import { StatCard } from '../components/StatCard';
import { SectionCard } from '../components/SectionCard';
import { HealthBadge } from '../components/HealthBadge';
import { DataTable } from '../components/DataTable';
import { formatPnl, formatPercent, formatNumber, formatUptime, formatTimestamp, formatPrice, truncate, pnlColor } from '../utils/formatters';

export default function Overview() {
  const status = useDashboardStore((s) => s.status);
  const mode = useDashboardStore((s) => s.mode);
  const uptime = useDashboardStore((s) => s.uptime);
  const stats = useDashboardStore((s) => s.stats);
  const components = useDashboardStore((s) => s.components);
  const strategies = useDashboardStore((s) => s.strategies);
  const risk = useDashboardStore((s) => s.risk);
  const positions = useDashboardStore((s) => s.positions);
  const trades = useDashboardStore((s) => s.trades);
  const { fetchPositions, fetchTrades } = useApi();

  useEffect(() => {
    fetchPositions();
    fetchTrades();
    const interval = setInterval(() => {
      fetchPositions();
      fetchTrades();
    }, 10000);
    return () => clearInterval(interval);
  }, [fetchPositions, fetchTrades]);

  const health = stats.health || {};
  const spotPrices = stats.spot_prices || {};

  const paperBalance = useMemo(() => {
    const totalCost = positions.reduce((sum, p) => sum + p.size * p.avg_cost, 0);
    return 1000 - totalCost + stats.daily_pnl;
  }, [positions, stats.daily_pnl]);

  const recentTrades = useMemo(() => trades.slice(-5).reverse(), [trades]);

  const tradeColumns = [
    { key: 'timestamp', label: 'Time', render: (v) => formatTimestamp(v) },
    { key: 'market_question', label: 'Market', render: (v) => <span className="text-zinc-300">{truncate(v, 35)}</span> },
    { key: 'outcome', label: 'Side', render: (_, r) => (
      <span className={r.side === 'buy' ? 'text-emerald-400' : 'text-red-400'}>
        {r.side?.toUpperCase()} {r.outcome}
      </span>
    )},
    { key: 'price', label: 'Price', align: 'right', render: (v) => formatPrice(v) },
    { key: 'size', label: 'Size', align: 'right', render: (v) => formatNumber(v, 2) },
  ];

  return (
    <div data-testid="overview-page" className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-zinc-100">Dashboard</h1>
        <span className="text-xs text-zinc-600 font-mono">
          {status === 'running' ? `Running ${formatUptime(uptime)}` : status.toUpperCase()}
        </span>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
        <StatCard testId="stat-daily-pnl" label="Daily P&L" value={formatPnl(stats.daily_pnl)} format="pnl" />
        <StatCard testId="stat-balance" label="Paper Balance" value={`$${paperBalance.toFixed(2)}`} />
        <StatCard testId="stat-win-rate" label="Win Rate" value={formatPercent(stats.win_rate)} sub={`${stats.win_count}W / ${stats.loss_count}L`} />
        <StatCard testId="stat-total-trades" label="Total Trades" value={formatNumber(stats.total_trades)} />
        <StatCard testId="stat-open-positions" label="Open Positions" value={formatNumber(stats.open_positions)} sub={`of ${risk.max_concurrent_positions || 10} max`} />
        <StatCard testId="stat-markets" label="Markets Tracked" value={formatNumber(stats.markets_tracked)} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* System Status */}
        <SectionCard title="System Status" testId="section-system-status">
          <div className="space-y-3">
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-500">Engine</span>
              <HealthBadge status={status} label={status} />
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-500">Trading Mode</span>
              <span className="text-zinc-300 uppercase font-medium">{mode}</span>
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-500">Kill Switch</span>
              <span className={risk.kill_switch_active ? 'text-red-400 font-medium' : 'text-zinc-500'}>
                {risk.kill_switch_active ? 'ACTIVE' : 'Inactive'}
              </span>
            </div>
            {components.length > 0 && (
              <div className="pt-2 border-t border-zinc-800 space-y-2">
                {components.map((c) => (
                  <div key={c.name} className="flex items-center justify-between text-xs">
                    <span className="text-zinc-500">{c.name}</span>
                    <HealthBadge status={c.status} />
                  </div>
                ))}
              </div>
            )}
          </div>
        </SectionCard>

        {/* Strategy Summary */}
        <SectionCard title="Active Strategies" testId="section-strategies">
          <div className="space-y-3">
            {strategies.length === 0 ? (
              <p className="text-xs text-zinc-600">No strategies registered</p>
            ) : (
              strategies.map((s) => (
                <div key={s.strategy_id} className="flex items-center justify-between text-xs">
                  <div>
                    <span className="text-zinc-300">{s.name}</span>
                    <span className="ml-2 text-zinc-600">{s.strategy_id}</span>
                  </div>
                  <HealthBadge status={s.enabled ? s.status : 'stopped'} label={s.enabled ? s.status : 'disabled'} />
                </div>
              ))
            )}
          </div>
        </SectionCard>

        {/* Feed Health */}
        <SectionCard title="Feed Health" testId="section-feed-health">
          <div className="space-y-3">
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-500">Polymarket</span>
              <HealthBadge status={health.polymarket_connected ? 'running' : 'stopped'} label={health.polymarket_connected ? 'Connected' : 'Disconnected'} />
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-500">Binance WS</span>
              <HealthBadge status={health.binance_connected ? 'running' : 'stopped'} label={health.binance_connected ? 'Connected' : 'Disconnected'} />
            </div>
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-500">Market Data</span>
              <span className={health.market_data_stale ? 'text-amber-400' : 'text-emerald-400'}>
                {health.market_data_stale ? 'Stale' : 'Fresh'}
              </span>
            </div>
            {spotPrices.BTCUSDT && (
              <div className="flex items-center justify-between text-xs pt-2 border-t border-zinc-800">
                <span className="text-zinc-500">BTC/USDT</span>
                <span className="text-zinc-200 font-mono">${formatNumber(spotPrices.BTCUSDT, 2)}</span>
              </div>
            )}
            {spotPrices.ETHUSDT && (
              <div className="flex items-center justify-between text-xs">
                <span className="text-zinc-500">ETH/USDT</span>
                <span className="text-zinc-200 font-mono">${formatNumber(spotPrices.ETHUSDT, 2)}</span>
              </div>
            )}
            {health.last_order_latency_ms && (
              <div className="flex items-center justify-between text-xs">
                <span className="text-zinc-500">Last Latency</span>
                <span className="text-zinc-300 font-mono">{health.last_order_latency_ms.toFixed(1)}ms</span>
              </div>
            )}
          </div>
        </SectionCard>
      </div>

      {/* Recent Activity */}
      <SectionCard title="Recent Trades" testId="section-recent-trades">
        <DataTable columns={tradeColumns} data={recentTrades} emptyMessage="No trades yet — start the engine to begin" testId="recent-trades-table" />
      </SectionCard>
    </div>
  );
}
