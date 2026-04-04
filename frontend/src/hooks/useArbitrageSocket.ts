import { useEffect, useRef } from 'react';
import { useArbitrageStore } from '../store';
import type { LiveState } from '../types';

const WS_URL = 'ws://127.0.0.1:8765';
const RECONNECT_DELAY_MS = 2000;
const STALE_TIMEOUT_MS = 3000; // consider connection dead if no data for 3s

export function useArbitrageSocket() {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const staleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const setLiveState = useArbitrageStore((s) => s.setLiveState);
  const setWsStatus = useArbitrageStore((s) => s.setWsStatus);

  useEffect(() => {
    let isMounted = true;

    function resetStaleTimer() {
      if (staleTimerRef.current) clearTimeout(staleTimerRef.current);
      staleTimerRef.current = setTimeout(() => {
        if (isMounted) setWsStatus('error');
      }, STALE_TIMEOUT_MS);
    }

    function connect() {
      if (!isMounted) return;
      
      // Clean up existing connection
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }

      setWsStatus('connecting');
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!isMounted) return;
        setWsStatus('connected');
        resetStaleTimer();
        console.log('[WS] Connected to backend');
      };

      ws.onmessage = (event) => {
        if (!isMounted) return;
        try {
          const data: LiveState = JSON.parse(event.data);
          setLiveState(data);
          setWsStatus('connected');
          resetStaleTimer();
        } catch (e) {
          console.error('[WS] Parse error:', e);
        }
      };

      ws.onclose = () => {
        if (!isMounted) return;
        setWsStatus('disconnected');
        console.log('[WS] Disconnected, reconnecting...');
        scheduleReconnect();
      };

      ws.onerror = () => {
        if (!isMounted) return;
        setWsStatus('error');
        ws.close();
      };
    }

    function scheduleReconnect() {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = setTimeout(() => {
        if (isMounted) connect();
      }, RECONNECT_DELAY_MS);
    }

    connect();

    return () => {
      isMounted = false;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (staleTimerRef.current) clearTimeout(staleTimerRef.current);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [setLiveState, setWsStatus]);
}
