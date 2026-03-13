import { useEffect, useRef } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { TradeTicker } from './TradeTicker';
import { useWebSocket } from '../hooks/useWebSocket';
import { useApi } from '../hooks/useApi';
import { useDashboardStore } from '../state/dashboardStore';
import { Toaster } from './ui/sonner';

export function AppShell() {
  useWebSocket();
  const totalTrades = useDashboardStore((s) => s.stats.total_trades);
  const mode = useDashboardStore((s) => s.mode);
  const { fetchTickerFeed, fetchWalletStatus } = useApi();
  const prevTrades = useRef(totalTrades);
  const prevMode = useRef(mode);

  // Fetch ticker on mount and when WebSocket reports new trades
  useEffect(() => {
    fetchTickerFeed();
    fetchWalletStatus();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (totalTrades !== prevTrades.current) {
      prevTrades.current = totalTrades;
      fetchTickerFeed();
    }
  }, [totalTrades, fetchTickerFeed]);

  // Refetch wallet when mode changes
  useEffect(() => {
    if (mode !== prevMode.current) {
      prevMode.current = mode;
      fetchWalletStatus();
    }
  }, [mode, fetchWalletStatus]);

  return (
    <div className="dark flex h-screen bg-zinc-950 text-zinc-100 overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <TopBar />
        <TradeTicker testId="trade-ticker" />
        <main className="flex-1 overflow-y-auto p-5" data-testid="main-content">
          <Outlet />
        </main>
      </div>
      <Toaster position="bottom-right" theme="dark" />
    </div>
  );
}
