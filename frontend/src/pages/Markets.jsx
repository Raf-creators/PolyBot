import { useEffect, useState, useMemo, useCallback } from 'react';
import { useDashboardStore } from '../state/dashboardStore';
import { useApi } from '../hooks/useApi';
import { SectionCard } from '../components/SectionCard';
import { DataTable } from '../components/DataTable';
import { StatCard } from '../components/StatCard';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../components/ui/dialog';
import { formatPrice, formatNumber, formatTimeAgo, truncate } from '../utils/formatters';
import { Search } from 'lucide-react';
import axios from 'axios';

const API_BASE = process.env.REACT_APP_BACKEND_URL;

export default function Markets() {
  const markets = useDashboardStore((s) => s.markets);
  const stats = useDashboardStore((s) => s.stats);
  const { fetchMarkets } = useApi();
  const [search, setSearch] = useState('');
  const [heatmapData, setHeatmapData] = useState(null);
  const [selectedTile, setSelectedTile] = useState(null);

  const fetchHeatmap = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API_BASE}/api/markets/liquidity-heatmap`);
      setHeatmapData(data);
    } catch {}
  }, []);

  useEffect(() => {
    fetchMarkets();
    fetchHeatmap();
    const interval = setInterval(() => {
      fetchMarkets();
      fetchHeatmap();
    }, 12000);
    return () => clearInterval(interval);
  }, [fetchMarkets, fetchHeatmap]);

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
    { key: 'volume_24h', label: '24h Vol', align: 'right', sortable: true, render: (v) => `$${formatNumber(v, 0)}` },
    { key: 'liquidity', label: 'Liquidity', align: 'right', sortable: true, render: (v) => `$${formatNumber(v, 0)}` },
    { key: 'updated_at', label: 'Updated', render: (v) => <span className="text-zinc-500">{formatTimeAgo(v)}</span> },
  ];

  const tiles = heatmapData?.tiles || [];
  const summary = heatmapData?.summary || {};

  return (
    <div data-testid="markets-page" className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-semibold text-zinc-100">Markets</h1>
        <span className="text-xs text-zinc-600 font-mono">{stats.markets_tracked} tracked</span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard testId="stat-total-markets" label="Total Markets" value={markets.length} />
        <StatCard testId="stat-heatmap-tiles" label="Weather Markets" value={tiles.length} />
        <StatCard testId="stat-total-volume" label="Total 24h Volume"
          value={`$${formatNumber(markets.reduce((s, m) => s + (m.volume_24h || 0), 0), 0)}`}
        />
        <StatCard testId="stat-avg-score" label="Avg Liquidity Score"
          value={summary.avg_score ? `${summary.avg_score}/100` : '—'}
        />
      </div>

      <Tabs defaultValue="heatmap">
        <TabsList className="bg-zinc-900 border border-zinc-800">
          <TabsTrigger data-testid="tab-heatmap" value="heatmap" className="text-xs data-[state=active]:bg-zinc-800">
            Liquidity Heatmap ({tiles.length})
          </TabsTrigger>
          <TabsTrigger data-testid="tab-table" value="table" className="text-xs data-[state=active]:bg-zinc-800">
            All Markets ({markets.length})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="heatmap" className="mt-4">
          <LiquidityHeatmap tiles={tiles} summary={summary} onSelectTile={setSelectedTile} />
        </TabsContent>

        <TabsContent value="table" className="mt-4">
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
        </TabsContent>
      </Tabs>

      {selectedTile && (
        <TileDetailDialog tile={selectedTile} onClose={() => setSelectedTile(null)} />
      )}
    </div>
  );
}


// ---- Score → color mapping ----

function scoreColor(score) {
  if (score >= 70) return 'bg-emerald-500/80';
  if (score >= 50) return 'bg-emerald-600/60';
  if (score >= 35) return 'bg-teal-700/50';
  if (score >= 20) return 'bg-cyan-800/40';
  if (score >= 10) return 'bg-zinc-700/40';
  return 'bg-zinc-800/30';
}

function scoreBorder(score) {
  if (score >= 70) return 'border-emerald-400/40';
  if (score >= 50) return 'border-emerald-500/30';
  if (score >= 35) return 'border-teal-500/25';
  if (score >= 20) return 'border-cyan-600/20';
  return 'border-zinc-700/30';
}

function scoreText(score) {
  if (score >= 70) return 'text-emerald-300';
  if (score >= 50) return 'text-emerald-400';
  if (score >= 35) return 'text-teal-400';
  if (score >= 20) return 'text-cyan-400';
  return 'text-zinc-500';
}

function scoreLabel(score) {
  if (score >= 70) return 'DEEP';
  if (score >= 50) return 'GOOD';
  if (score >= 35) return 'MODERATE';
  if (score >= 20) return 'THIN';
  if (score >= 10) return 'SPARSE';
  return 'DRY';
}


// ---- Heatmap Component ----

function LiquidityHeatmap({ tiles, summary, onSelectTile }) {
  if (!tiles.length) {
    return (
      <SectionCard testId="section-heatmap-empty">
        <p className="text-xs text-zinc-600 py-6 text-center">
          No weather market tiles — start the engine to discover and price weather markets
        </p>
      </SectionCard>
    );
  }

  // Group tiles by city
  const byCity = {};
  for (const t of tiles) {
    if (!byCity[t.city]) byCity[t.city] = [];
    byCity[t.city].push(t);
  }
  // Sort dates within each city
  for (const city of Object.keys(byCity)) {
    byCity[city].sort((a, b) => a.target_date.localeCompare(b.target_date));
  }

  return (
    <div data-testid="section-liquidity-heatmap" className="space-y-4">
      {/* Summary bar */}
      <div className="flex items-center gap-5 text-xs text-zinc-500">
        <span>Markets: <span className="text-zinc-300 font-mono">{tiles.length}</span></span>
        <span>Avg Score: <span className={`font-mono ${scoreText(summary.avg_score)}`}>{summary.avg_score}/100</span></span>
        <span>Best: <span className="text-emerald-400 font-mono">{summary.max_score}</span></span>
        <span>Worst: <span className="text-zinc-400 font-mono">{summary.min_score}</span></span>
        <span>Total Liq: <span className="text-zinc-300 font-mono">${formatNumber(summary.total_liquidity, 0)}</span></span>
        {/* Legend */}
        <div className="ml-auto flex items-center gap-1.5">
          <span className="text-[10px] text-zinc-600">DRY</span>
          {[8, 15, 28, 42, 60, 80].map((s) => (
            <div key={s} className={`w-3 h-3 rounded-sm ${scoreColor(s)}`} />
          ))}
          <span className="text-[10px] text-zinc-600">DEEP</span>
        </div>
      </div>

      {/* City groups */}
      {Object.entries(byCity).map(([city, cityTiles]) => (
        <SectionCard key={city} testId={`heatmap-city-${city.toLowerCase().replace(/\s/g, '-')}`}>
          <div className="mb-3 flex items-center gap-3">
            <span className="text-sm font-medium text-zinc-200">{city}</span>
            <span className="text-[10px] text-zinc-600">{cityTiles[0]?.station_id}</span>
            <span className="text-[10px] text-zinc-600">{cityTiles.length} dates</span>
          </div>
          <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(auto-fill, minmax(240px, 1fr))` }}>
            {cityTiles.map((tile) => (
              <HeatmapTile key={tile.condition_id} tile={tile} onClick={() => onSelectTile(tile)} />
            ))}
          </div>
        </SectionCard>
      ))}
    </div>
  );
}


// ---- Single Heatmap Tile ----

function HeatmapTile({ tile, onClick }) {
  const score = tile.avg_liquidity_score;
  return (
    <button
      data-testid={`heatmap-tile-${tile.condition_id}`}
      onClick={onClick}
      className={`text-left border ${scoreBorder(score)} ${scoreColor(score)} rounded-lg px-3 py-2.5 transition-all hover:brightness-125 hover:scale-[1.02] cursor-pointer`}
    >
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs text-zinc-300 font-medium">{tile.target_date}</span>
        <Badge variant="outline" className={`text-[9px] ${scoreText(score)} border-current/30`}>
          {scoreLabel(score)} {score}
        </Badge>
      </div>
      <div className="flex gap-3 text-[10px] text-zinc-400">
        <span>Liq: <span className="text-zinc-300 font-mono">${formatNumber(tile.total_liquidity, 0)}</span></span>
        <span>Sprd: <span className="text-zinc-300 font-mono">{tile.avg_spread != null ? formatPrice(tile.avg_spread) : '—'}</span></span>
        <span>Bkts: <span className="text-zinc-300 font-mono">{tile.priced_buckets}/{tile.bucket_count}</span></span>
      </div>
      {/* Mini bucket bar */}
      <div className="flex gap-0.5 mt-2">
        {tile.buckets.map((b) => (
          <div
            key={b.token_id || b.label}
            title={`${b.label}: score ${b.liquidity_score}`}
            className={`h-1.5 flex-1 rounded-full ${scoreColor(b.liquidity_score)}`}
          />
        ))}
      </div>
    </button>
  );
}


// ---- Tile Detail Dialog ----

function TileDetailDialog({ tile, onClose }) {
  const buckets = tile.buckets || [];

  return (
    <Dialog open={true} onOpenChange={() => onClose()}>
      <DialogContent data-testid="tile-detail-dialog" className="max-w-lg bg-zinc-950 border-zinc-800">
        <DialogHeader>
          <DialogTitle className="text-zinc-100">
            {tile.city} — {tile.target_date}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-zinc-500">
            <span>Station: <span className="text-cyan-400 font-mono">{tile.station_id}</span></span>
            <span>Score: <span className={`font-mono ${scoreText(tile.avg_liquidity_score)}`}>{tile.avg_liquidity_score}/100 ({scoreLabel(tile.avg_liquidity_score)})</span></span>
            <span>Total Liq: <span className="text-zinc-300 font-mono">${formatNumber(tile.total_liquidity, 0)}</span></span>
            <span>Avg Spread: <span className="text-zinc-300 font-mono">{tile.avg_spread != null ? formatPrice(tile.avg_spread) : '—'}</span></span>
          </div>

          <div className="space-y-1 max-h-[400px] overflow-y-auto">
            {buckets.map((b) => {
              const s = b.liquidity_score;
              return (
                <div
                  key={b.token_id || b.label}
                  data-testid={`bucket-detail-${b.label}`}
                  className={`flex items-center gap-3 border ${scoreBorder(s)} rounded-md px-3 py-1.5 text-xs`}
                >
                  <div className={`w-2 h-2 rounded-full ${scoreColor(s)}`} />
                  <span className="text-zinc-300 font-mono w-16">{b.label}</span>
                  <span className="text-zinc-500 flex-1">
                    Mid: <span className="text-zinc-300">{b.mid_price != null ? formatPrice(b.mid_price) : '—'}</span>
                  </span>
                  <span className="text-zinc-500">
                    Sprd: <span className="text-zinc-300">{b.spread != null ? formatPrice(b.spread) : '—'}</span>
                  </span>
                  <span className="text-zinc-500">
                    Liq: <span className="text-zinc-300">${formatNumber(b.liquidity, 0)}</span>
                  </span>
                  <span className={`font-mono ${scoreText(s)}`}>{s}</span>
                </div>
              );
            })}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
