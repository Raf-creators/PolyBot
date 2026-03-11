import { useEffect, useState, useMemo } from 'react';
import { useDashboardStore } from '../state/dashboardStore';
import { useApi } from '../hooks/useApi';
import { SectionCard } from '../components/SectionCard';
import { DataTable } from '../components/DataTable';
import { StatCard } from '../components/StatCard';
import { Input } from '../components/ui/input';
import { formatPrice, formatNumber, formatTimeAgo, truncate } from '../utils/formatters';
import { Search } from 'lucide-react';

export default function Markets() {
  const markets = useDashboardStore((s) => s.markets);
  const stats = useDashboardStore((s) => s.stats);
  const { fetchMarkets } = useApi();
  const [search, setSearch] = useState('');

  useEffect(() => {
    fetchMarkets();
    const interval = setInterval(fetchMarkets, 15000);
    return () => clearInterval(interval);
  }, [fetchMarkets]);

  const filtered = useMemo(() => {
    if (!search.trim()) return markets;
    const q = search.toLowerCase();
    return markets.filter((m) =>
      m.question?.toLowerCase().includes(q) ||
      m.outcome?.toLowerCase().includes(q) ||
      m.token_id?.toLowerCase().includes(q)
    );
  }, [markets, search]);

  const columns = [
    { key: 'question', label: 'Market', render: (v) => <span className="text-zinc-300">{truncate(v, 45)}</span> },
    { key: 'outcome', label: 'Outcome', render: (v) => (
      <span className={v === 'Yes' ? 'text-emerald-400' : v === 'No' ? 'text-red-400' : 'text-zinc-400'}>{v}</span>
    )},
    { key: 'mid_price', label: 'Mid', align: 'right', sortable: true, render: (v) => formatPrice(v) },
    { key: 'best_bid', label: 'Bid', align: 'right', render: (v) => v != null ? formatPrice(v) : '—' },
    { key: 'best_ask', label: 'Ask', align: 'right', render: (v) => v != null ? formatPrice(v) : '—' },
    { key: 'spread', label: 'Spread', align: 'right', sortable: true, render: (v) => v != null ? formatPrice(v) : '—' },
    { key: 'volume_24h', label: '24h Volume', align: 'right', sortable: true, render: (v) => `$${formatNumber(v, 0)}` },
    { key: 'liquidity', label: 'Liquidity', align: 'right', sortable: true, render: (v) => `$${formatNumber(v, 0)}` },
    { key: 'updated_at', label: 'Updated', render: (v) => <span className="text-zinc-500">{formatTimeAgo(v)}</span> },
  ];

  return (
    <div data-testid="markets-page" className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-zinc-100">Markets</h1>
        <span className="text-xs text-zinc-600 font-mono">{stats.markets_tracked} tracked</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard testId="stat-total-markets" label="Total Markets" value={markets.length} />
        <StatCard testId="stat-displayed" label="Displayed" value={filtered.length} />
        <StatCard testId="stat-total-volume" label="Total 24h Volume"
          value={`$${formatNumber(markets.reduce((s, m) => s + (m.volume_24h || 0), 0), 0)}`}
        />
        <StatCard testId="stat-avg-liquidity" label="Avg Liquidity"
          value={markets.length ? `$${formatNumber(markets.reduce((s, m) => s + (m.liquidity || 0), 0) / markets.length, 0)}` : '—'}
        />
      </div>

      <SectionCard testId="section-markets-table">
        <div className="mb-4 relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
          <Input
            data-testid="market-search-input"
            placeholder="Search markets by question, outcome, or token..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9 bg-zinc-900 border-zinc-800 text-sm h-9"
          />
        </div>
        <DataTable columns={columns} data={filtered} emptyMessage="No markets loaded — start the engine to fetch market data" testId="markets-table" />
      </SectionCard>
    </div>
  );
}
