import { create } from 'zustand';
import type { LiveState, ConnectionStatus, OpportunityRecord, AnalyticsData, TimeseriesData, ConsistencyRow } from './types';

interface ArbitrageStore {
  // Live data from WebSocket
  liveState: LiveState | null;
  
  // Connection status to the Python backend
  wsStatus: ConnectionStatus;
  lastUpdateAt: number | null;

  // User-adjustable threshold (synced from backend on first connect)
  threshold: number;
  _thresholdInitialized: boolean;
  
  // View mode
  viewMode: 'cards' | 'heatmap';
  setViewMode: (mode: 'cards' | 'heatmap') => void;

  activeTab: 'dashboard' | 'logs' | 'analytics';
  setActiveTab: (tab: 'dashboard' | 'logs' | 'analytics') => void;

  opportunities: OpportunityRecord[];
  setOpportunities: (opportunities: OpportunityRecord[]) => void;
  addOpportunity: (opportunity: OpportunityRecord) => void;

  analyticsData: AnalyticsData | null;
  setAnalyticsData: (data: AnalyticsData | null) => void;

  timeseriesData: Record<string, TimeseriesData>;
  setTimeseriesData: (token: string, data: TimeseriesData) => void;

  consistencyData: ConsistencyRow[] | null;
  setConsistencyData: (data: ConsistencyRow[] | null) => void;

  setLiveState: (liveState: LiveState) => void;
  setWsStatus: (wsStatus: ConnectionStatus) => void;
  setThreshold: (threshold: number) => void;
}

export const useArbitrageStore = create<ArbitrageStore>((set, get) => ({
  liveState: null,
  wsStatus: 'connecting',
  lastUpdateAt: null,
  threshold: 1.0,
  _thresholdInitialized: false,
  viewMode: 'cards',
  activeTab: 'dashboard',
  opportunities: [],
  analyticsData: null,
  timeseriesData: {},
  consistencyData: null,

  setActiveTab: (activeTab) => set({ activeTab }),
  setOpportunities: (opportunities) => set({ opportunities }),
  addOpportunity: (opportunity) =>
    set((state) => ({ opportunities: [opportunity, ...state.opportunities] })),
  setAnalyticsData: (analyticsData) => set({ analyticsData }),
  setTimeseriesData: (token, data) => set((state) => ({ 
    timeseriesData: { ...state.timeseriesData, [token]: data } 
  })),
  setConsistencyData: (consistencyData) => set({ consistencyData }),

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
    set({ threshold: Math.max(-2.0, Math.min(15, threshold)), _thresholdInitialized: true }),

  setViewMode: (viewMode) => set({ viewMode }),
}));
