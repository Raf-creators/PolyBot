import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { useWebSocket } from '../hooks/useWebSocket';
import { Toaster } from './ui/sonner';

export function AppShell() {
  useWebSocket();

  return (
    <div className="dark flex h-screen bg-zinc-950 text-zinc-100 overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-y-auto p-5" data-testid="main-content">
          <Outlet />
        </main>
      </div>
      <Toaster position="bottom-right" theme="dark" />
    </div>
  );
}
