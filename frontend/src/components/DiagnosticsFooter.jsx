import { useEffect } from 'react';
import { useDashboardStore } from '../state/dashboardStore';
import { useApi } from '../hooks/useApi';
import { Database, GitCommit, Server } from 'lucide-react';

const ENV_COLORS = {
  railway: 'text-purple-400',
  emergent_preview: 'text-blue-400',
  local: 'text-zinc-400',
};

export function DiagnosticsFooter() {
  const diag = useDashboardStore((s) => s.diagnostics);
  const { fetchDiagnostics } = useApi();

  useEffect(() => {
    fetchDiagnostics();
    // Refresh every 60s
    const id = setInterval(fetchDiagnostics, 60_000);
    return () => clearInterval(id);
  }, [fetchDiagnostics]);

  if (!diag) return null;

  const envColor = ENV_COLORS[diag.environment] || 'text-zinc-500';

  return (
    <footer data-testid="diagnostics-footer" className="fixed bottom-0 left-0 right-0 h-6 bg-zinc-950 border-t border-zinc-800/50 flex items-center px-4 gap-4 text-[10px] font-mono text-zinc-600 z-40">
      <span className="flex items-center gap-1">
        <Server size={9} />
        <span className={envColor}>{diag.environment}</span>
      </span>
      <span className="flex items-center gap-1">
        <GitCommit size={9} />
        {diag.git_commit || '?'}
      </span>
      <span className="flex items-center gap-1">
        <Database size={9} />
        {diag.database?.name}@{diag.database?.host}
      </span>
      <span>boot: {diag.server_start_time?.slice(0, 19)?.replace('T', ' ')}Z</span>
      <span>loaded: {diag.state?.trades_loaded_from_db ?? 0} trades</span>
      {diag.has_persistence_reload && (
        <span className="text-emerald-600">db-reload:on</span>
      )}
      {!diag.has_persistence_reload && (
        <span className="text-red-500">db-reload:OFF</span>
      )}
    </footer>
  );
}
