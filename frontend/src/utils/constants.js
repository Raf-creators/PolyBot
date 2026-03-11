const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;
export const WS_URL = BACKEND_URL.replace(/^http/, 'ws') + '/api/ws';

export const NAV_ITEMS = [
  { path: '/', label: 'Overview', icon: 'LayoutDashboard' },
  { path: '/arbitrage', label: 'Arbitrage', icon: 'ArrowLeftRight' },
  { path: '/positions', label: 'Positions', icon: 'Layers' },
  { path: '/risk', label: 'Risk', icon: 'ShieldAlert' },
  { path: '/markets', label: 'Markets', icon: 'BarChart3' },
  { path: '/settings', label: 'Settings', icon: 'Settings' },
];

export const ENGINE_STATUS_COLORS = {
  running: 'text-emerald-400',
  stopped: 'text-zinc-500',
  starting: 'text-amber-400',
  stopping: 'text-amber-400',
  error: 'text-red-400',
};

export const ARB_STATUS_COLORS = {
  submitted: 'text-blue-400',
  partially_filled: 'text-amber-400',
  completed: 'text-emerald-400',
  invalidated: 'text-red-400',
  closed: 'text-zinc-500',
  rejected: 'text-red-400',
  detected: 'text-zinc-400',
  eligible: 'text-blue-300',
};
