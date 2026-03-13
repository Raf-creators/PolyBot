import { useMemo, useRef, useEffect, useState } from 'react';
import { useDashboardStore } from '../state/dashboardStore';

function TickerItem({ trade }) {
  const isBuy = trade.side === 'BUY';
  const edgePositive = trade.edge_bps > 0;

  return (
    <span data-testid="ticker-item" className="inline-flex items-center gap-2 px-4 whitespace-nowrap text-xs font-mono">
      <span className="text-zinc-500 font-semibold">{trade.strategy}</span>
      <span className="text-zinc-300">{trade.asset}</span>
      <span className={isBuy ? 'text-emerald-400' : 'text-red-400'}>{trade.side}</span>
      <span className="text-zinc-400">
        {trade.size.toFixed(1)} @ {trade.price.toFixed(2)}
      </span>
      <span className={edgePositive ? 'text-emerald-400' : 'text-red-400'}>
        EDGE {edgePositive ? '+' : ''}{trade.edge_bps.toFixed(0)}bps
      </span>
      <span className="text-zinc-700 ml-1">|</span>
    </span>
  );
}

export function TradeTicker({ testId }) {
  const tickerFeed = useDashboardStore((s) => s.tickerFeed);
  const [paused, setPaused] = useState(false);
  const scrollRef = useRef(null);

  const items = useMemo(() => {
    if (!tickerFeed.length) return [];
    // Duplicate for seamless loop
    return [...tickerFeed, ...tickerFeed];
  }, [tickerFeed]);

  // Calculate animation duration based on item count
  const duration = useMemo(() => {
    return Math.max(tickerFeed.length * 3, 20);
  }, [tickerFeed]);

  // Reset animation when feed changes
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.style.animation = 'none';
      // Force reflow
      void scrollRef.current.offsetHeight;
      scrollRef.current.style.animation = '';
    }
  }, [tickerFeed.length]);

  if (!tickerFeed.length) {
    return (
      <div
        data-testid={testId}
        className="h-8 bg-zinc-950 border-b border-zinc-800/50 flex items-center px-4 shrink-0"
      >
        <span className="text-[10px] text-zinc-600 font-mono tracking-wider">TAPE</span>
        <span className="text-[10px] text-zinc-700 ml-3">Waiting for executions...</span>
      </div>
    );
  }

  return (
    <div
      data-testid={testId}
      className="h-8 bg-zinc-950 border-b border-zinc-800/50 flex items-center overflow-hidden shrink-0"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      <div className="flex items-center h-full px-3 border-r border-zinc-800/50 shrink-0">
        <span className="text-[10px] text-zinc-600 font-mono tracking-wider">TAPE</span>
        <span className="ml-2 h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
      </div>
      <div className="overflow-hidden flex-1 relative">
        <div
          ref={scrollRef}
          className="inline-flex items-center"
          style={{
            animation: `ticker-scroll ${duration}s linear infinite`,
            animationPlayState: paused ? 'paused' : 'running',
          }}
        >
          {items.map((t, i) => (
            <TickerItem key={`${t.id}-${i}`} trade={t} />
          ))}
        </div>
      </div>
    </div>
  );
}
