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
  weatherSignals: { tradable: [], rejected: [], total_tradable: 0, total_rejected: 0 },
  weatherExecutions: { active: [], completed: [] },
  weatherHealth: {},
  weatherForecasts: {},
  weatherAlerts: { alerts: [], stats: {} },
  pnlHistory: { points: [], current_pnl: 0, peak_pnl: 0, trough_pnl: 0, max_drawdown: 0, total_trades: 0, latest_close_at: null, server_time: null },
  tickerFeed: [],
  walletStatus: { mode: 'paper', authenticated: false, balance_usdc: null, live_ready: false, warnings: [] },

  // Diagnostics info (fetched from /api/diagnostics)
  diagnostics: null,

  // Arb diagnostics (fetched from /api/strategies/arb/diagnostics)
  arbDiagnostics: {},

  // Signal quality (fetched from /api/analytics/signal-quality)
  signalQuality: {},

  // Watchdog (fetched from /api/analytics/watchdog)
  watchdog: {},

  // Strategy tracker (fetched from /api/analytics/strategy-tracker)
  strategyTracker: {},

  // Strategy attribution (fetched from /api/analytics/strategy-attribution)
  strategyAttribution: {},

  // Controls (fetched from /api/controls)
  controls: {},

  // Strategy positions (fetched from /api/positions/by-strategy)
  strategyPositions: { positions: { weather: [], crypto: [], arb: [], other: [] }, summaries: {}, total_unrealized_pnl: 0, total_open: 0 },

  // Connection state
  wsConnected: false,
  lastWsUpdate: null,

  // Demo mode — hydrated from localStorage on init
  demoMode: localStorage.getItem('edgeos_demo_mode') === 'true',
  setDemoMode: (enabled) => {
    localStorage.setItem('edgeos_demo_mode', enabled ? 'true' : 'false');
    set({ demoMode: enabled });
  },

  // Actions
  setWsSnapshot: (snapshot) => {
    // Don't overwrite state when in demo mode
    if (get().demoMode) return;
    set({
      status: snapshot.status,
      mode: snapshot.mode,
      uptime: snapshot.uptime_seconds,
      components: snapshot.components || [],
      strategies: snapshot.strategies || [],
      risk: snapshot.risk || {},
      stats: snapshot.stats || get().stats,
      lastWsUpdate: Date.now(),
    });
  },

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
  setWeatherSignals: (data) => set({ weatherSignals: data }),
  setWeatherExecutions: (data) => set({ weatherExecutions: data }),
  setWeatherHealth: (data) => set({ weatherHealth: data }),
  setWeatherForecasts: (data) => set({ weatherForecasts: data }),
  setWeatherAlerts: (data) => set({ weatherAlerts: data }),
  setPnlHistory: (data) => set({ pnlHistory: data }),
  setTickerFeed: (data) => set({ tickerFeed: data }),
  setWalletStatus: (data) => set({ walletStatus: data }),
  setDiagnostics: (data) => set({ diagnostics: data }),
  setArbDiagnostics: (data) => set({ arbDiagnostics: data }),
  setSignalQuality: (data) => set({ signalQuality: data }),
  setWatchdog: (data) => set({ watchdog: data }),
  setStrategyTracker: (data) => set({ strategyTracker: data }),
  setStrategyAttribution: (data) => set({ strategyAttribution: data }),
  setControls: (data) => set({ controls: data }),
  setStrategyPositions: (data) => set({ strategyPositions: data }),

  // Apply a full demo snapshot to all state slices
  applyDemoSnapshot: (demoStatus) => set({
    status: demoStatus.status || 'running',
    mode: demoStatus.mode || 'paper',
    uptime: demoStatus.uptime_seconds || 0,
    components: demoStatus.components || [],
    strategies: demoStatus.strategies || [],
    risk: demoStatus.risk || {},
    stats: demoStatus.stats || {},
  }),
}));
