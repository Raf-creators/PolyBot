import { useEffect, useState, useMemo } from 'react';
import { useDashboardStore } from '../state/dashboardStore';
import { useApi } from '../hooks/useApi';
import { SectionCard } from '../components/SectionCard';
import { DataTable } from '../components/DataTable';
import { StatCard } from '../components/StatCard';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { formatPrice, formatNumber, formatPnl, formatTimestamp, truncate, pnlColor } from '../utils/formatters';

export default function Positions() {
  const positions = useDashboardStore((s) => s.positions);
  const trades = useDashboardStore((s) => s.trades);
  const orders = useDashboardStore((s) => s.orders);
  const stats = useDashboardStore((s) => s.stats);
  const { fetchPositions, fetchTrades, fetchOrders } = useApi();
  const [tab, setTab] = useState('positions');

  useEffect(() => {
    fetchPositions();
    fetchTrades();
    fetchOrders();
    const interval = setInterval(() => {
      fetchPositions();
      fetchTrades();
      fetchOrders();
    }, 8000);
    return () => clearInterval(interval);
  }, [fetchPositions, fetchTrades, fetchOrders]);

  const totalUnrealizedPnl = useMemo(
    () => positions.reduce((sum, p) => sum + (p.unrealized_pnl || 0), 0),
    [positions]
  );
  const totalRealizedPnl = useMemo(
    () => positions.reduce((sum, p) => sum + (p.realized_pnl || 0), 0),
    [positions]
  );
  const totalExposure = useMemo(
    () => positions.reduce((sum, p) => sum + p.size * p.current_price, 0),
    [positions]
  );

  const positionColumns = [
    { key: 'market_question', label: 'Market', render: (v) => <span className="text-zinc-300">{truncate(v, 35)}</span> },
    { key: 'outcome', label: 'Outcome', render: (v) => (
      <span className={v === 'Yes' ? 'text-emerald-400' : v === 'No' ? 'text-red-400' : 'text-zinc-400'}>{v || '—'}</span>
    )},
    { key: 'size', label: 'Size', align: 'right', sortable: true, render: (v) => formatNumber(v, 4) },
    { key: 'avg_cost', label: 'Avg Cost', align: 'right', sortable: true, render: (v) => formatPrice(v) },
    { key: 'current_price', label: 'Current', align: 'right', render: (v) => formatPrice(v) },
    { key: 'unrealized_pnl', label: 'Unreal. P&L', align: 'right', sortable: true, render: (v) => (
      <span className={pnlColor(v)}>{formatPnl(v)}</span>
    )},
    { key: 'realized_pnl', label: 'Real. P&L', align: 'right', sortable: true, render: (v) => (
      <span className={pnlColor(v)}>{formatPnl(v)}</span>
    )},
  ];

  const tradeColumns = [
    { key: 'timestamp', label: 'Time', sortable: true, render: (v) => <span className="text-zinc-500">{formatTimestamp(v)}</span> },
    { key: 'market_question', label: 'Market', render: (v) => <span className="text-zinc-300">{truncate(v, 30)}</span> },
    { key: 'outcome', label: 'Outcome' },
    { key: 'side', label: 'Side', render: (v) => (
      <span className={v === 'buy' ? 'text-emerald-400' : 'text-red-400'}>{v?.toUpperCase()}</span>
    )},
    { key: 'price', label: 'Price', align: 'right', sortable: true, render: (v) => formatPrice(v) },
    { key: 'size', label: 'Size', align: 'right', render: (v) => formatNumber(v, 2) },
    { key: 'fees', label: 'Fees', align: 'right', render: (v) => `$${formatNumber(v, 4)}` },
    { key: 'pnl', label: 'P&L', align: 'right', sortable: true, render: (v) => (
      <span className={pnlColor(v)}>{formatPnl(v)}</span>
    )},
    { key: 'strategy_id', label: 'Strategy', render: (v) => <span className="text-zinc-500">{v || '—'}</span> },
  ];

  const orderColumns = [
    { key: 'created_at', label: 'Created', sortable: true, render: (v) => <span className="text-zinc-500">{formatTimestamp(v)}</span> },
    { key: 'token_id', label: 'Token', render: (v) => <span className="text-zinc-400 font-mono">{truncate(v, 16)}</span> },
    { key: 'side', label: 'Side', render: (v) => (
      <span className={v === 'buy' ? 'text-emerald-400' : 'text-red-400'}>{v?.toUpperCase()}</span>
    )},
    { key: 'price', label: 'Price', align: 'right', render: (v) => formatPrice(v) },
    { key: 'size', label: 'Size', align: 'right', render: (v) => formatNumber(v, 2) },
    { key: 'filled_size', label: 'Filled', align: 'right', render: (v) => formatNumber(v, 2) },
    { key: 'status', label: 'Status', render: (v) => {
      const colors = { filled: 'text-emerald-400', pending: 'text-amber-400', rejected: 'text-red-400', cancelled: 'text-zinc-500' };
      return <span className={colors[v] || 'text-zinc-400'}>{v}</span>;
    }},
    { key: 'fill_price', label: 'Fill Price', align: 'right', render: (v) => v != null ? formatPrice(v) : '—' },
    { key: 'latency_ms', label: 'Latency', align: 'right', render: (v) => v != null ? `${v}ms` : '—' },
  ];

  const reversedTrades = useMemo(() => [...trades].reverse(), [trades]);
  const reversedOrders = useMemo(() => [...orders].reverse(), [orders]);

  return (
    <div data-testid="positions-page" className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-zinc-100">Positions & Trades</h1>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard testId="stat-positions-count" label="Open Positions" value={positions.length} />
        <StatCard testId="stat-exposure" label="Total Exposure" value={`$${totalExposure.toFixed(2)}`} />
        <StatCard testId="stat-unrealized" label="Unrealized P&L" value={formatPnl(totalUnrealizedPnl)} format="pnl" />
        <StatCard testId="stat-realized" label="Realized P&L" value={formatPnl(totalRealizedPnl)} format="pnl" />
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-zinc-900 border border-zinc-800">
          <TabsTrigger value="positions" className="text-xs data-[state=active]:bg-zinc-800">
            Positions ({positions.length})
          </TabsTrigger>
          <TabsTrigger value="trades" className="text-xs data-[state=active]:bg-zinc-800">
            Trades ({trades.length})
          </TabsTrigger>
          <TabsTrigger value="orders" className="text-xs data-[state=active]:bg-zinc-800">
            Orders ({orders.length})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="positions" className="mt-4">
          <SectionCard testId="section-positions">
            <DataTable columns={positionColumns} data={positions} emptyMessage="No open positions" testId="positions-table" />
          </SectionCard>
        </TabsContent>

        <TabsContent value="trades" className="mt-4">
          <SectionCard testId="section-trades">
            <DataTable columns={tradeColumns} data={reversedTrades} emptyMessage="No trade history" testId="trades-table" />
          </SectionCard>
        </TabsContent>

        <TabsContent value="orders" className="mt-4">
          <SectionCard testId="section-orders">
            <DataTable columns={orderColumns} data={reversedOrders} emptyMessage="No orders" testId="orders-table" />
          </SectionCard>
        </TabsContent>
      </Tabs>
    </div>
  );
}
