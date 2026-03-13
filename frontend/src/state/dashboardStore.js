import { create } from 'zustand';

export const useDashboardStore = create((set, get) => ({
  // WebSocket state snapshot (updated every 2s)
  status: 'stopped',
  mode: 'paper',
  uptime: 0,
  components: [],
  strategies: [],
  risk: {},
  stats: {
    daily_pnl: 0,
    total_trades: 0,
    win_count: 0,
    loss_count: 0,
    win_rate: 0,
    open_positions: 0,
    open_orders: 0,
    markets_tracked: 0,
    spot_prices: {},
    health: {},
  },

  // REST-hydrated detailed data
  positions: [],
  trades: [],
  orders: [],
  markets: [],
  arbOpportunities: { tradable: [], rejected: [], total_tradable: 0, total_rejected: 0 },
  arbExecutions: { active: [], completed: [] },
  arbHealth: {},
  feedHealth: {},
  config: {},
  sniperSignals: { tradable: [], rejected: [], total_tradable: 0, total_rejected: 0 },
  sniperExecutions: { active: [], completed: [] },
  sniperHealth: {},
  pnlHistory: { points: [], current_pnl: 0, peak_pnl: 0, trough_pnl: 0, max_drawdown: 0, total_trades: 0 },

  // Connection state
  wsConnected: false,
  lastWsUpdate: null,

  // Actions
  setWsSnapshot: (snapshot) => set({
    status: snapshot.status,
    mode: snapshot.mode,
    uptime: snapshot.uptime_seconds,
    components: snapshot.components || [],
    strategies: snapshot.strategies || [],
    risk: snapshot.risk || {},
    stats: snapshot.stats || get().stats,
    lastWsUpdate: Date.now(),
  }),

  setWsConnected: (connected) => set({ wsConnected: connected }),

  setPositions: (positions) => set({ positions }),
  setTrades: (trades) => set({ trades }),
  setOrders: (orders) => set({ orders }),
  setMarkets: (markets) => set({ markets }),
  setArbOpportunities: (data) => set({ arbOpportunities: data }),
  setArbExecutions: (data) => set({ arbExecutions: data }),
  setArbHealth: (data) => set({ arbHealth: data }),
  setFeedHealth: (data) => set({ feedHealth: data }),
  setConfig: (data) => set({ config: data }),
  setSniperSignals: (data) => set({ sniperSignals: data }),
  setSniperExecutions: (data) => set({ sniperExecutions: data }),
  setSniperHealth: (data) => set({ sniperHealth: data }),
  setPnlHistory: (data) => set({ pnlHistory: data }),
}));
