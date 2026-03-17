import { useCallback } from 'react';
import axios from 'axios';
import { API_BASE } from '../utils/constants';
import { useDashboardStore } from '../state/dashboardStore';

const api = axios.create({ baseURL: API_BASE });

/** Returns the correct endpoint prefix based on demo mode state. */
function usePrefix() {
  return useDashboardStore((s) => s.demoMode) ? '/demo' : '';
}

export function useApi() {
  const prefix = usePrefix();

  // Extract ONLY setter functions via selectors — these are stable refs
  // that never change, so useCallback deps stay stable across WS updates.
  const setPositions = useDashboardStore((s) => s.setPositions);
  const setTrades = useDashboardStore((s) => s.setTrades);
  const setOrders = useDashboardStore((s) => s.setOrders);
  const setMarkets = useDashboardStore((s) => s.setMarkets);
  const setArbOpportunities = useDashboardStore((s) => s.setArbOpportunities);
  const setArbExecutions = useDashboardStore((s) => s.setArbExecutions);
  const setArbHealth = useDashboardStore((s) => s.setArbHealth);
  const setFeedHealth = useDashboardStore((s) => s.setFeedHealth);
  const setConfig = useDashboardStore((s) => s.setConfig);
  const setSniperSignals = useDashboardStore((s) => s.setSniperSignals);
  const setSniperExecutions = useDashboardStore((s) => s.setSniperExecutions);
  const setSniperHealth = useDashboardStore((s) => s.setSniperHealth);
  const setWeatherSignals = useDashboardStore((s) => s.setWeatherSignals);
  const setWeatherExecutions = useDashboardStore((s) => s.setWeatherExecutions);
  const setWeatherHealth = useDashboardStore((s) => s.setWeatherHealth);
  const setWeatherForecasts = useDashboardStore((s) => s.setWeatherForecasts);
  const setWeatherAlerts = useDashboardStore((s) => s.setWeatherAlerts);
  const setPnlHistory = useDashboardStore((s) => s.setPnlHistory);
  const setTickerFeed = useDashboardStore((s) => s.setTickerFeed);
  const setWalletStatus = useDashboardStore((s) => s.setWalletStatus);
  const setDiagnostics = useDashboardStore((s) => s.setDiagnostics);
  const applyDemoSnapshot = useDashboardStore((s) => s.applyDemoSnapshot);
  const setWsSnapshot = useDashboardStore((s) => s.setWsSnapshot);
  const setArbDiagnostics = useDashboardStore((s) => s.setArbDiagnostics);
  const setSignalQuality = useDashboardStore((s) => s.setSignalQuality);
  const setWatchdog = useDashboardStore((s) => s.setWatchdog);
  const setStrategyTracker = useDashboardStore((s) => s.setStrategyTracker);

  // Polling fallback for stats — works even when WebSocket is down
  const fetchStatus = useCallback(async () => {
    try {
      const { data } = await api.get(`${prefix}/status`);
      setWsSnapshot(data);
    } catch {}
  }, [prefix, setWsSnapshot]);

  const fetchPositions = useCallback(async () => {
    try {
      const { data } = await api.get(`${prefix}/positions`);
      setPositions(data);
    } catch {}
  }, [prefix, setPositions]);

  const fetchTrades = useCallback(async () => {
    try {
      const { data } = await api.get(`${prefix}/trades`);
      setTrades(data);
    } catch {}
  }, [prefix, setTrades]);

  const fetchOrders = useCallback(async () => {
    try {
      const { data } = await api.get(`${prefix}/orders`);
      setOrders(data);
    } catch {}
  }, [prefix, setOrders]);

  const fetchMarkets = useCallback(async () => {
    try {
      const { data } = await api.get(`${prefix}/markets`);
      setMarkets(data);
    } catch {}
  }, [prefix, setMarkets]);

  const fetchArbOpportunities = useCallback(async () => {
    try {
      const { data } = await api.get(`${prefix}/strategies/arb/opportunities`);
      setArbOpportunities(data);
    } catch {}
  }, [prefix, setArbOpportunities]);

  const fetchArbExecutions = useCallback(async () => {
    try {
      const { data } = await api.get(`${prefix}/strategies/arb/executions`);
      setArbExecutions(data);
    } catch {}
  }, [prefix, setArbExecutions]);

  const fetchArbHealth = useCallback(async () => {
    try {
      const { data } = await api.get(`${prefix}/strategies/arb/health`);
      setArbHealth(data);
    } catch {}
  }, [prefix, setArbHealth]);

  const fetchFeedHealth = useCallback(async () => {
    try {
      const { data } = await api.get(`${prefix}/health/feeds`);
      setFeedHealth(data);
    } catch {}
  }, [prefix, setFeedHealth]);

  const fetchConfig = useCallback(async () => {
    try {
      const { data } = await api.get(`${prefix}/config`);
      setConfig(data);
    } catch {}
  }, [prefix, setConfig]);

  const fetchSniperSignals = useCallback(async () => {
    try {
      const { data } = await api.get(`${prefix}/strategies/sniper/signals`);
      setSniperSignals(data);
    } catch {}
  }, [prefix, setSniperSignals]);

  const fetchSniperExecutions = useCallback(async () => {
    try {
      const { data } = await api.get(`${prefix}/strategies/sniper/executions`);
      setSniperExecutions(data);
    } catch {}
  }, [prefix, setSniperExecutions]);

  const fetchSniperHealth = useCallback(async () => {
    try {
      const { data } = await api.get(`${prefix}/strategies/sniper/health`);
      setSniperHealth(data);
    } catch {}
  }, [prefix, setSniperHealth]);

  const fetchWeatherSignals = useCallback(async () => {
    try {
      const { data } = await api.get(`${prefix}/strategies/weather/signals`);
      setWeatherSignals(data);
    } catch {}
  }, [prefix, setWeatherSignals]);

  const fetchWeatherExecutions = useCallback(async () => {
    try {
      const { data } = await api.get(`${prefix}/strategies/weather/executions`);
      setWeatherExecutions(data);
    } catch {}
  }, [prefix, setWeatherExecutions]);

  const fetchWeatherHealth = useCallback(async () => {
    try {
      const { data } = await api.get(`${prefix}/strategies/weather/health`);
      setWeatherHealth(data);
    } catch {}
  }, [prefix, setWeatherHealth]);

  const fetchWeatherForecasts = useCallback(async () => {
    try {
      const { data } = await api.get(`${prefix}/strategies/weather/forecasts`);
      setWeatherForecasts(data);
    } catch {}
  }, [prefix, setWeatherForecasts]);

  const fetchWeatherAlerts = useCallback(async () => {
    try {
      const { data } = await api.get(`${prefix}/strategies/weather/alerts`);
      setWeatherAlerts(data);
    } catch {}
  }, [prefix, setWeatherAlerts]);

  const fetchPnlHistory = useCallback(async () => {
    try {
      const { data } = await api.get(`${prefix}/analytics/pnl-history`);
      setPnlHistory(data);
    } catch {}
  }, [prefix, setPnlHistory]);

  const fetchTickerFeed = useCallback(async () => {
    try {
      const { data } = await api.get(`${prefix}/ticker/feed`);
      setTickerFeed(data);
    } catch {}
  }, [prefix, setTickerFeed]);

  const fetchWalletStatus = useCallback(async () => {
    try {
      const { data } = await api.get(`${prefix}/execution/wallet`);
      setWalletStatus(data);
    } catch {}
  }, [prefix, setWalletStatus]);

  const fetchDiagnostics = useCallback(async () => {
    try {
      const { data } = await api.get('/diagnostics');
      setDiagnostics(data);
    } catch {}
  }, [setDiagnostics]);

  const fetchArbDiagnostics = useCallback(async () => {
    try {
      const { data } = await api.get(`${prefix}/strategies/arb/diagnostics`);
      setArbDiagnostics(data);
    } catch {}
  }, [prefix, setArbDiagnostics]);

  const fetchSignalQuality = useCallback(async () => {
    try {
      const { data } = await api.get(`${prefix}/analytics/signal-quality`);
      setSignalQuality(data);
    } catch {}
  }, [prefix, setSignalQuality]);

  const fetchWatchdog = useCallback(async () => {
    try {
      const { data } = await api.get(`${prefix}/analytics/watchdog`);
      setWatchdog(data);
    } catch {}
  }, [prefix, setWatchdog]);

  const fetchStrategyTracker = useCallback(async () => {
    try {
      const { data } = await api.get(`${prefix}/analytics/strategy-tracker`);
      setStrategyTracker(data);
    } catch {}
  }, [prefix, setStrategyTracker]);

  // Load the demo status snapshot (overrides WS-driven top-level state)
  const loadDemoSnapshot = useCallback(async () => {
    try {
      const { data } = await api.get('/demo/status-snapshot');
      applyDemoSnapshot(data);
    } catch {}
  }, [applyDemoSnapshot]);

  const startEngine = useCallback(async () => {
    const { data } = await api.post('/engine/start');
    return data;
  }, []);

  const stopEngine = useCallback(async () => {
    const { data } = await api.post('/engine/stop');
    return data;
  }, []);

  const activateKillSwitch = useCallback(async () => {
    const { data } = await api.post('/risk/kill-switch/activate');
    return data;
  }, []);

  const deactivateKillSwitch = useCallback(async () => {
    const { data } = await api.post('/risk/kill-switch/deactivate');
    return data;
  }, []);

  const updateConfig = useCallback(async (body) => {
    const { data } = await api.put('/config', body);
    return data;
  }, []);

  return {
    fetchStatus,
    fetchPositions, fetchTrades, fetchOrders, fetchMarkets,
    fetchArbOpportunities, fetchArbExecutions, fetchArbHealth,
    fetchFeedHealth, fetchConfig,
    fetchSniperSignals, fetchSniperExecutions, fetchSniperHealth,
    fetchWeatherSignals, fetchWeatherExecutions, fetchWeatherHealth, fetchWeatherForecasts, fetchWeatherAlerts,
    fetchPnlHistory, fetchTickerFeed, fetchWalletStatus,
    fetchDiagnostics,
    fetchArbDiagnostics,
    fetchSignalQuality,
    fetchWatchdog,
    fetchStrategyTracker,
    loadDemoSnapshot,
    startEngine, stopEngine,
    activateKillSwitch, deactivateKillSwitch,
    updateConfig,
  };
}
