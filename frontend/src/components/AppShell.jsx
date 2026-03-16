import { useEffect, useRef, useCallback } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { TradeTicker } from './TradeTicker';
import { DiagnosticsFooter } from './DiagnosticsFooter';
import { useWebSocket } from '../hooks/useWebSocket';
import { useApi } from '../hooks/useApi';
import { useDashboardStore } from '../state/dashboardStore';
import { Toaster } from './ui/sonner';

export function AppShell() {
  useWebSocket();
  const totalTrades = useDashboardStore((s) => s.stats.total_trades);
  const mode = useDashboardStore((s) => s.mode);
  const demoMode = useDashboardStore((s) => s.demoMode);
  const {
    fetchTickerFeed, fetchWalletStatus, loadDemoSnapshot,
    fetchPositions, fetchTrades, fetchPnlHistory,
    fetchArbOpportunities, fetchArbExecutions, fetchArbHealth,
    fetchSniperSignals, fetchSniperExecutions, fetchSniperHealth,
    fetchWeatherSignals, fetchWeatherExecutions, fetchWeatherHealth, fetchWeatherForecasts,
    fetchConfig, fetchFeedHealth, fetchMarkets,
  } = useApi();
  const prevTrades = useRef(totalTrades);
  const prevMode = useRef(mode);

  // Full data refresh (used when switching to demo mode)
  const refreshAllData = useCallback(() => {
    fetchTickerFeed();
    fetchWalletStatus();
    fetchPositions();
    fetchTrades();
    fetchPnlHistory();
    fetchArbOpportunities();
    fetchArbExecutions();
    fetchArbHealth();
    fetchSniperSignals();
    fetchSniperExecutions();
    fetchSniperHealth();
    fetchWeatherSignals();
    fetchWeatherExecutions();
    fetchWeatherHealth();
    fetchWeatherForecasts();
    fetchConfig();
    fetchFeedHealth();
    fetchMarkets();
  }, [
    fetchTickerFeed, fetchWalletStatus, fetchPositions, fetchTrades, fetchPnlHistory,
    fetchArbOpportunities, fetchArbExecutions, fetchArbHealth,
    fetchSniperSignals, fetchSniperExecutions, fetchSniperHealth,
    fetchWeatherSignals, fetchWeatherExecutions, fetchWeatherHealth, fetchWeatherForecasts,
    fetchConfig, fetchFeedHealth, fetchMarkets,
  ]);

  // On mount
  useEffect(() => {
    fetchTickerFeed();
    fetchWalletStatus();
    // If demo mode was active before refresh, reload demo data
    if (demoMode) {
      loadDemoSnapshot();
      setTimeout(() => refreshAllData(), 50);
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // When demo mode toggles, reload ALL data from the new source
  const prevDemo = useRef(demoMode);
  useEffect(() => {
    if (demoMode !== prevDemo.current) {
      prevDemo.current = demoMode;
      if (demoMode) {
        loadDemoSnapshot();
      }
      setTimeout(() => refreshAllData(), 50);
    }
  }, [demoMode, loadDemoSnapshot, refreshAllData]);

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
        <main className="flex-1 overflow-y-auto p-5 pb-10" data-testid="main-content">
          <Outlet />
        </main>
      </div>
      <Toaster position="bottom-right" theme="dark" />
      <DiagnosticsFooter />
    </div>
  );
}
