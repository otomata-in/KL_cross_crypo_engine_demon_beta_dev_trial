import { create } from 'zustand';
import type { LiveState, ConnectionStatus } from './types';

interface ArbitrageStore {
  // Live data from WebSocket
  liveState: LiveState | null;
  
  // Connection status to the Python backend
  wsStatus: ConnectionStatus;
  lastUpdateAt: number | null;

  // User-adjustable threshold (synced from backend on first connect)
  threshold: number;
  _thresholdInitialized: boolean;
  
  // Actions
  setLiveState: (state: LiveState) => void;
  setWsStatus: (status: ConnectionStatus) => void;
  setThreshold: (threshold: number) => void;
}

export const useArbitrageStore = create<ArbitrageStore>((set, get) => ({
  liveState: null,
  wsStatus: 'connecting',
  lastUpdateAt: null,
  threshold: 1.0,
  _thresholdInitialized: false,

  setLiveState: (liveState) => {
    const state = get();
    // On first data from backend, sync the threshold
    if (!state._thresholdInitialized && liveState.threshold != null) {
      set({
        liveState,
        lastUpdateAt: Date.now(),
        threshold: liveState.threshold,
        _thresholdInitialized: true,
      });
    } else {
      set({ liveState, lastUpdateAt: Date.now() });
    }
  },

  setWsStatus: (wsStatus) =>
    set({ wsStatus }),

  setThreshold: (threshold) =>
    set({ threshold: Math.max(0.1, Math.min(15, threshold)), _thresholdInitialized: true }),
}));
