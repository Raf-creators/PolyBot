import { useCallback } from 'react';
import axios from 'axios';
import { API_BASE } from '../utils/constants';
import { useDashboardStore } from '../state/dashboardStore';

const api = axios.create({ baseURL: API_BASE });

export function useApi() {
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
  const setPnlHistory = useDashboardStore((s) => s.setPnlHistory);
  const setTickerFeed = useDashboardStore((s) => s.setTickerFeed);
  const setWalletStatus = useDashboardStore((s) => s.setWalletStatus);

  const fetchPositions = useCallback(async () => {
    try {
      const { data } = await api.get('/positions');
      setPositions(data);
    } catch {}
  }, [setPositions]);

  const fetchTrades = useCallback(async () => {
    try {
      const { data } = await api.get('/trades');
      setTrades(data);
    } catch {}
  }, [setTrades]);

  const fetchOrders = useCallback(async () => {
    try {
      const { data } = await api.get('/orders');
      setOrders(data);
    } catch {}
  }, [setOrders]);

  const fetchMarkets = useCallback(async () => {
    try {
      const { data } = await api.get('/markets');
      setMarkets(data);
    } catch {}
  }, [setMarkets]);

  const fetchArbOpportunities = useCallback(async () => {
    try {
      const { data } = await api.get('/strategies/arb/opportunities');
      setArbOpportunities(data);
    } catch {}
  }, [setArbOpportunities]);

  const fetchArbExecutions = useCallback(async () => {
    try {
      const { data } = await api.get('/strategies/arb/executions');
      setArbExecutions(data);
    } catch {}
  }, [setArbExecutions]);

  const fetchArbHealth = useCallback(async () => {
    try {
      const { data } = await api.get('/strategies/arb/health');
      setArbHealth(data);
    } catch {}
  }, [setArbHealth]);

  const fetchFeedHealth = useCallback(async () => {
    try {
      const { data } = await api.get('/health/feeds');
      setFeedHealth(data);
    } catch {}
  }, [setFeedHealth]);

  const fetchConfig = useCallback(async () => {
    try {
      const { data } = await api.get('/config');
      setConfig(data);
    } catch {}
  }, [setConfig]);

  const fetchSniperSignals = useCallback(async () => {
    try {
      const { data } = await api.get('/strategies/sniper/signals');
      setSniperSignals(data);
    } catch {}
  }, [setSniperSignals]);

  const fetchSniperExecutions = useCallback(async () => {
    try {
      const { data } = await api.get('/strategies/sniper/executions');
      setSniperExecutions(data);
    } catch {}
  }, [setSniperExecutions]);

  const fetchSniperHealth = useCallback(async () => {
    try {
      const { data } = await api.get('/strategies/sniper/health');
      setSniperHealth(data);
    } catch {}
  }, [setSniperHealth]);

  const fetchPnlHistory = useCallback(async () => {
    try {
      const { data } = await api.get('/analytics/pnl-history');
      setPnlHistory(data);
    } catch {}
  }, [setPnlHistory]);

  const fetchTickerFeed = useCallback(async () => {
    try {
      const { data } = await api.get('/ticker/feed');
      setTickerFeed(data);
    } catch {}
  }, [setTickerFeed]);

  const fetchWalletStatus = useCallback(async () => {
    try {
      const { data } = await api.get('/execution/wallet');
      setWalletStatus(data);
    } catch {}
  }, [setWalletStatus]);

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
    fetchPositions, fetchTrades, fetchOrders, fetchMarkets,
    fetchArbOpportunities, fetchArbExecutions, fetchArbHealth,
    fetchFeedHealth, fetchConfig,
    fetchSniperSignals, fetchSniperExecutions, fetchSniperHealth, fetchPnlHistory, fetchTickerFeed, fetchWalletStatus,
    startEngine, stopEngine,
    activateKillSwitch, deactivateKillSwitch,
    updateConfig,
  };
}
