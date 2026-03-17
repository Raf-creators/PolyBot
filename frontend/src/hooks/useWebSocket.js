import { useEffect, useRef } from 'react';
import { useDashboardStore } from '../state/dashboardStore';
import { WS_URL } from '../utils/constants';

export function useWebSocket() {
  const wsRef = useRef(null);
  const reconnectTimer = useRef(null);
  const setWsSnapshot = useDashboardStore((s) => s.setWsSnapshot);
  const setWsConnected = useDashboardStore((s) => s.setWsConnected);

  useEffect(() => {
    let attempts = 0;
    let mounted = true;

    function connect() {
      if (!mounted) return;
      try {
        const ws = new WebSocket(WS_URL);
        wsRef.current = ws;

        ws.onopen = () => {
          attempts = 0;
          setWsConnected(true);
        };

        ws.onmessage = (e) => {
          try {
            const data = JSON.parse(e.data);
            setWsSnapshot(data);
            // If a trade just closed, fire event so Overview re-fetches pnl-history immediately
            if (data._event === "trade_closed") {
              window.dispatchEvent(new CustomEvent("trade_closed"));
            }
          } catch {}
        };

        ws.onclose = () => {
          setWsConnected(false);
          if (mounted) {
            const delay = Math.min(1000 * Math.pow(2, attempts), 10000);
            attempts++;
            reconnectTimer.current = setTimeout(connect, delay);
          }
        };

        ws.onerror = () => {
          ws.close();
        };
      } catch {
        if (mounted) {
          reconnectTimer.current = setTimeout(connect, 3000);
        }
      }
    }

    connect();

    return () => {
      mounted = false;
      clearTimeout(reconnectTimer.current);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [setWsSnapshot, setWsConnected]);
}
