import { useEffect, useState, useMemo, useCallback } from 'react';
import { useDashboardStore } from '../state/dashboardStore';
import { useApi } from '../hooks/useApi';
import { SectionCard } from '../components/SectionCard';
import { DataTable } from '../components/DataTable';
import { StatCard } from '../components/StatCard';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../components/ui/tabs';
import { formatPrice, formatNumber, formatPnl, formatTimestamp, truncate, pnlColor } from '../utils/formatters';
import { toast } from 'sonner';
import { X } from 'lucide-react';
import axios from 'axios';
import { API_BASE } from '../utils/constants';

export default function Positions() {
  const positions = useDashboardStore((s) => s.positions);
  const trades = useDashboardStore((s) => s.trades);
  const orders = useDashboardStore((s) => s.orders);
  const mode = useDashboardStore((s) => s.mode);
  const { fetchPositions, fetchTrades, fetchOrders } = useApi();
  const [tab, setTab] = useState('positions');
  const [liveOrders, setLiveOrders] = useState([]);
  const [cancelling, setCancelling] = useState(null);

  const fetchLiveOrders = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API_BASE}/execution/orders?limit=50`);
      setLiveOrders(data);
    } catch {}
  }, []);

  useEffect(() => {
    fetchPositions();
    fetchTrades();
    fetchOrders();
    fetchLiveOrders();
    const interval = setInterval(() => {
      fetchPositions();
      fetchTrades();
      fetchOrders();
      fetchLiveOrders();
    }, 8000);
    return () => clearInterval(interval);
  }, [fetchPositions, fetchTrades, fetchOrders, fetchLiveOrders]);

  const handleCancel = async (orderId) => {
    setCancelling(orderId);
    try {
      await axios.post(`${API_BASE}/execution/orders/${orderId}/cancel`);
      toast.success('Order cancelled');
      fetchLiveOrders();
    } catch (e) {
      toast.error(e?.response?.data?.detail || 'Cancel failed');
    } finally {
      setCancelling(null);
    }
  };

  const totalUnrealizedPnl = useMemo(() => positions.reduce((sum, p) => sum + (p.unrealized_pnl || 0), 0), [positions]);
  const totalRealizedPnl = useMemo(() => positions.reduce((sum, p) => sum + (p.realized_pnl || 0), 0), [positions]);
  const totalExposure = useMemo(() => positions.reduce((sum, p) => sum + p.size * p.current_price, 0), [positions]);

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

  const CANCELLABLE = new Set(['submitted', 'open', 'partially_filled']);

  const liveOrderColumns = [
    { key: 'submitted_at', label: 'Submitted', sortable: true, render: (v) => <span className="text-zinc-500">{formatTimestamp(v)}</span> },
    { key: 'market_question', label: 'Market', render: (v) => <span className="text-zinc-300">{truncate(v, 25)}</span> },
    { key: 'side', label: 'Side', render: (v) => (
      <span className={v === 'buy' ? 'text-emerald-400' : 'text-red-400'}>{v?.toUpperCase()}</span>
    )},
    { key: 'price', label: 'Req. Price', align: 'right', render: (v) => formatPrice(v) },
    { key: 'avg_fill_price', label: 'Fill Price', align: 'right', render: (v) => v > 0 ? formatPrice(v) : '—' },
    { key: 'slippage_bps', label: 'Slip', align: 'right', render: (v) => v != null ? (
      <span className={v > 50 ? 'text-red-400' : v > 20 ? 'text-amber-400' : 'text-zinc-400'}>{v.toFixed(0)}bps</span>
    ) : '—' },
    { key: 'requested_size', label: 'Req. Size', align: 'right', render: (v) => formatNumber(v, 2) },
    { key: 'filled_size', label: 'Filled', align: 'right', render: (v) => formatNumber(v, 2) },
    { key: 'remaining_size', label: 'Remain', align: 'right', render: (v) => v > 0 ? formatNumber(v, 2) : '—' },
    { key: 'status', label: 'Status', render: (v) => {
      const colors = {
        submitted: 'bg-blue-500/20 text-blue-400', open: 'bg-amber-500/20 text-amber-400',
        partially_filled: 'bg-violet-500/20 text-violet-400', filled: 'bg-emerald-500/20 text-emerald-400',
        cancelled: 'bg-zinc-500/20 text-zinc-400', rejected: 'bg-red-500/20 text-red-400', expired: 'bg-zinc-500/20 text-zinc-500',
      };
      return <Badge className={`text-[10px] ${colors[v] || ''}`}>{v}</Badge>;
    }},
    { key: 'update_source', label: 'Source', render: (v) => <span className="text-zinc-600 text-[10px]">{v}</span> },
    { key: 'id', label: '', render: (v, row) => CANCELLABLE.has(row.status) ? (
      <Button
        data-testid={`cancel-order-${v}`}
        size="sm" variant="ghost"
        onClick={() => handleCancel(v)}
        disabled={cancelling === v}
        className="h-6 px-2 text-red-400 hover:text-red-300 hover:bg-red-500/10"
      >
        <X size={12} />
      </Button>
    ) : null },
  ];

  const reversedTrades = useMemo(() => [...trades].reverse(), [trades]);
  const reversedOrders = useMemo(() => [...orders].reverse(), [orders]);
  const openLiveCount = useMemo(() => liveOrders.filter((o) => CANCELLABLE.has(o.status)).length, [liveOrders]);

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
          <TabsTrigger
            data-testid="live-orders-tab"
            value="live-orders"
            className="text-xs data-[state=active]:bg-zinc-800"
          >
            Live Orders ({liveOrders.length})
            {openLiveCount > 0 && (
              <span className="ml-1 h-1.5 w-1.5 rounded-full bg-amber-400 inline-block" />
            )}
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

        <TabsContent value="live-orders" className="mt-4">
          <SectionCard testId="section-live-orders">
            {mode !== 'live' && mode !== 'shadow' && (
              <p className="text-xs text-zinc-600 mb-3">Live orders only appear when executing in live or shadow mode</p>
            )}
            <DataTable columns={liveOrderColumns} data={liveOrders} emptyMessage="No live orders" testId="live-orders-table" />
          </SectionCard>
        </TabsContent>
      </Tabs>
    </div>
  );
}
