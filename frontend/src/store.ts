import { create } from 'zustand';
import type { LiveState, ConnectionStatus } from './types';

interface ArbitrageStore {
  // Live data from WebSocket
  liveState: LiveState | null;
  
  // Connection status to the Python backend
  wsStatus: ConnectionStatus;
  lastUpdateAt: number | null;
  
  // Actions
  setLiveState: (state: LiveState) => void;
  setWsStatus: (status: ConnectionStatus) => void;
}

export const useArbitrageStore = create<ArbitrageStore>((set) => ({
  liveState: null,
  wsStatus: 'connecting',
  lastUpdateAt: null,

  setLiveState: (liveState) =>
    set({ liveState, lastUpdateAt: Date.now() }),

  setWsStatus: (wsStatus) =>
    set({ wsStatus }),
}));
