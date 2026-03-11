import { useCallback } from 'react';
import axios from 'axios';
import { API_BASE } from '../utils/constants';
import { useDashboardStore } from '../state/dashboardStore';

const api = axios.create({ baseURL: API_BASE });

export function useApi() {
  const store = useDashboardStore();

  const fetchPositions = useCallback(async () => {
    try {
      const { data } = await api.get('/positions');
      store.setPositions(data);
    } catch {}
  }, [store]);

  const fetchTrades = useCallback(async () => {
    try {
      const { data } = await api.get('/trades');
      store.setTrades(data);
    } catch {}
  }, [store]);

  const fetchOrders = useCallback(async () => {
    try {
      const { data } = await api.get('/orders');
      store.setOrders(data);
    } catch {}
  }, [store]);

  const fetchMarkets = useCallback(async () => {
    try {
      const { data } = await api.get('/markets');
      store.setMarkets(data);
    } catch {}
  }, [store]);

  const fetchArbOpportunities = useCallback(async () => {
    try {
      const { data } = await api.get('/strategies/arb/opportunities');
      store.setArbOpportunities(data);
    } catch {}
  }, [store]);

  const fetchArbExecutions = useCallback(async () => {
    try {
      const { data } = await api.get('/strategies/arb/executions');
      store.setArbExecutions(data);
    } catch {}
  }, [store]);

  const fetchArbHealth = useCallback(async () => {
    try {
      const { data } = await api.get('/strategies/arb/health');
      store.setArbHealth(data);
    } catch {}
  }, [store]);

  const fetchFeedHealth = useCallback(async () => {
    try {
      const { data } = await api.get('/health/feeds');
      store.setFeedHealth(data);
    } catch {}
  }, [store]);

  const fetchConfig = useCallback(async () => {
    try {
      const { data } = await api.get('/config');
      store.setConfig(data);
    } catch {}
  }, [store]);

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
    startEngine, stopEngine,
    activateKillSwitch, deactivateKillSwitch,
    updateConfig,
  };
}
