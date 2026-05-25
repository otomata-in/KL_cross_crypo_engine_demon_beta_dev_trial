import { useEffect, useRef } from 'react';
import { useArbitrageStore } from '../store';
import type { LiveState } from '../types';

const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const WS_URL = import.meta.env.VITE_WS_URL || `${protocol}//${window.location.host}/ws`;
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
        ws.send(JSON.stringify({ type: 'get_recent_opportunities', limit: 100 }));
      };

      ws.onmessage = (event) => {
        if (!isMounted) return;
        try {
          const rawData = JSON.parse(event.data);
          if (rawData.type === 'recent_opportunities') {
            useArbitrageStore.getState().setOpportunities(rawData.data);
          } else if (rawData.type === 'new_opportunity') {
            useArbitrageStore.getState().addOpportunity(rawData.data);
          } else if (rawData.type === 'analytics_data') {
            useArbitrageStore.getState().setAnalyticsData(rawData.data);
          } else if (rawData.type === 'timeseries_data') {
            useArbitrageStore.getState().setTimeseriesData(rawData.data.token, rawData.data);
          } else if (rawData.type === 'consistency_data') {
            useArbitrageStore.getState().setConsistencyData(rawData.data);
          } else if (rawData.type === 'autotrader_status') {
            useArbitrageStore.getState().setAutoTradeEnabled(rawData.enabled);
          } else if (rawData.type === 'pro_mode_status') {
            useArbitrageStore.getState().setIsProMode(rawData.enabled);
          } else if (rawData.type === 'trade_state_data') {
            useArbitrageStore.getState().setTradeState(rawData.data);
          } else if (rawData.type === 'kill_switch_activated') {
            useArbitrageStore.getState().setAutoTradeEnabled(false);
          } else if (rawData.type === 'pnl_analytics_data') {
            useArbitrageStore.getState().setPnlAnalyticsData(rawData.data);
          } else if (rawData.type === 'logs_reset') {
            useArbitrageStore.getState().setOpportunities([]);
            // Request fresh logs and analytics
            ws.send(JSON.stringify({ type: 'get_recent_opportunities', limit: 100 }));
            ws.send(JSON.stringify({ type: 'get_analytics' }));
          } else if (rawData.type === 'mock_wallets_reset') {
            useArbitrageStore.getState().setTradeState({
              active_trades: [],
              history: [],
              rebalances: [],
              balances: rawData.balances
            });
            useArbitrageStore.getState().setAutoTradeEnabled(false);
          } else {
            setLiveState(rawData as LiveState);
            setWsStatus('connected');
            resetStaleTimer();
          }
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

    const handleWsSend = (e: Event) => {
      const customEvent = e as CustomEvent;
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify(customEvent.detail));
      }
    };
    window.addEventListener('ws-send', handleWsSend);

    return () => {
      isMounted = false;
      window.removeEventListener('ws-send', handleWsSend);
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (staleTimerRef.current) clearTimeout(staleTimerRef.current);
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [setLiveState, setWsStatus]);

  // ── Send threshold changes to backend ──────────────────────────
  const threshold = useArbitrageStore((s) => s.threshold);
  const prevThresholdRef = useRef<number | null>(null);

  useEffect(() => {
    // Skip initial sync (backend already has its default)
    if (prevThresholdRef.current === null) {
      prevThresholdRef.current = threshold;
      return;
    }
    prevThresholdRef.current = threshold;

    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'set_threshold', value: threshold }));
    }
  }, [threshold]);
}
