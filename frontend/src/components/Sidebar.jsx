import { NavLink, useLocation } from 'react-router-dom';
import { useDashboardStore } from '../state/dashboardStore';
import { NAV_ITEMS, ENGINE_STATUS_COLORS } from '../utils/constants';
import {
  LayoutDashboard, ArrowLeftRight, Layers,
  ShieldAlert, BarChart3, Settings, Crosshair, Wifi, WifiOff, TrendingUp, CloudSun, Globe, FlaskConical
} from 'lucide-react';

const ICONS = { LayoutDashboard, ArrowLeftRight, Layers, ShieldAlert, BarChart3, Settings, Crosshair, TrendingUp, CloudSun, Globe, FlaskConical };

export function Sidebar() {
  const location = useLocation();
  const status = useDashboardStore((s) => s.status);
  const mode = useDashboardStore((s) => s.mode);
  const wsConnected = useDashboardStore((s) => s.wsConnected);

  return (
    <aside data-testid="sidebar" className="w-56 shrink-0 border-r border-zinc-800 bg-zinc-950 flex flex-col h-screen sticky top-0">
      <div className="px-4 py-4 border-b border-zinc-800">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-sm font-semibold tracking-tight text-zinc-100">Edge OS</span>
        </div>
        <div className="mt-2 flex items-center gap-2 text-xs text-zinc-500">
          <span className={ENGINE_STATUS_COLORS[status] || 'text-zinc-500'}>{status}</span>
          <span className="text-zinc-700">|</span>
          <span className="text-zinc-400 uppercase">{mode}</span>
        </div>
      </div>

      <nav className="flex-1 py-2 px-2 space-y-0.5 overflow-y-auto">
        {NAV_ITEMS.map((item) => {
          const Icon = ICONS[item.icon];
          const isActive = location.pathname === item.path;
          return (
            <NavLink
              key={item.path}
              to={item.path}
              data-testid={`nav-${item.label.toLowerCase()}`}
              className={`flex items-center gap-3 px-3 py-2 rounded text-sm transition-colors ${
                isActive
                  ? 'bg-zinc-800 text-zinc-100'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900'
              }`}
            >
              {Icon && <Icon size={16} />}
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </nav>

      <div className="px-4 py-3 border-t border-zinc-800 text-xs text-zinc-600 flex items-center gap-2">
        {wsConnected ? (
          <><Wifi size={12} className="text-emerald-500" /><span>Live</span></>
        ) : (
          <><WifiOff size={12} className="text-red-400" /><span>Disconnected</span></>
        )}
      </div>
    </aside>
  );
}
