import React from 'react';
import type { ConnectionStatus } from '../types';
import { useArbitrageStore } from '../store';
import { Activity, Zap, Clock, TrendingUp, SlidersHorizontal, LayoutGrid, Table } from 'lucide-react';

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return `${h}h${String(m).padStart(2, '0')}m${String(s).padStart(2, '0')}s`;
}

function StatusDot({ status }: { status: ConnectionStatus | string }) {
  const isConnected = status === 'connected';
  const isConnecting = status === 'connecting';
  return (
    <span className="relative flex h-2.5 w-2.5">
      {isConnected && (
        <span className="absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75 animate-ping" />
      )}
      <span
        className={`relative inline-flex rounded-full h-2.5 w-2.5 ${
          isConnected ? 'bg-green-500' : isConnecting ? 'bg-yellow-500 animate-pulse' : 'bg-red-500'
        }`}
      />
    </span>
  );
}

export const HeaderHUD: React.FC = () => {
  const liveState = useArbitrageStore((s) => s.liveState);
  const wsStatus = useArbitrageStore((s) => s.wsStatus);
  const threshold = useArbitrageStore((s) => s.threshold);
  const setThreshold = useArbitrageStore((s) => s.setThreshold);
  const viewMode = useArbitrageStore((s) => s.viewMode);
  const setViewMode = useArbitrageStore((s) => s.setViewMode);
  const activeTab = useArbitrageStore((s) => s.activeTab);

  const rate = liveState?.usdt_usdc_rate ?? 1.0;
  const pegDev = (rate - 1.0) * 100;
  const uptime = liveState?.uptime_seconds ?? 0;
  const oppTotal = liveState?.opp_total ?? 0;

  // Dynamic exchange list from backend
  const exchangesList = liveState?.exchanges_list ?? [];
  const exchangeMeta = liveState?.exchange_meta ?? {};
  const updateCount = liveState?.update_count ?? {};

  // Build exchange subtitle: "Binance ↔ Backpack ↔ Bybit ↔ Dex-Trade"
  const exchangeLabels = exchangesList.map(ex => exchangeMeta[ex]?.label ?? ex.toUpperCase());
  const subtitle = exchangeLabels.join(' ↔ ');

  // Count tokens where best net spread RIGHT NOW meets the threshold
  const activeOpps = liveState ? Object.values(liveState.token_data).filter((td) => {
    return (td.best_net ?? -Infinity) >= threshold;
  }).length : 0;

  // Total ticks across all exchanges
  const totalTicks = exchangesList.reduce((sum, ex) => sum + (updateCount[ex] ?? 0), 0);

  return (
    <header className="border-b border-border bg-card/80 backdrop-blur-sm sticky top-0 z-50">
      {/* Top bar */}
      <div className="px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Zap className="w-5 h-5 text-accent-light" />
            <h1 className="text-lg font-bold bg-gradient-to-r from-accent-light to-purple-400 bg-clip-text text-transparent">
              Arbitrage Dashboard
            </h1>
          </div>
          <span className="text-xs text-gray-500 font-mono ml-2">{subtitle}</span>
        </div>

        {/* Threshold control + Uptime */}
        <div className="flex items-center gap-5">
          {/* Threshold slider */}
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="w-3.5 h-3.5 text-gray-500" />
            <span className="text-xs text-gray-400">Min Net Profit</span>
            <input
              type="range"
              min="-2.0"
              max="15"
              step="0.001"
              value={threshold}
              onChange={(e) => setThreshold(parseFloat(e.target.value))}
              className="w-24 h-1.5 appearance-none bg-border rounded-full cursor-pointer
                [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5
                [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-accent-light [&::-webkit-slider-thumb]:cursor-pointer
                [&::-webkit-slider-thumb]:shadow-[0_0_6px_rgba(99,102,241,0.5)]
                [&::-moz-range-thumb]:w-3.5 [&::-moz-range-thumb]:h-3.5 [&::-moz-range-thumb]:rounded-full
                [&::-moz-range-thumb]:bg-accent-light [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:cursor-pointer"
            />
            <input
              type="number"
              min="-2.0"
              max="15"
              step="0.001"
              value={threshold}
              onChange={(e) => setThreshold(parseFloat(e.target.value) || 0.001)}
              className="w-16 text-xs font-mono font-bold text-accent-light bg-surface border border-border rounded px-1.5 py-0.5 text-center
                focus:outline-none focus:border-accent/50"
            />
            <span className="text-[10px] text-gray-600">%</span>
          </div>

          {/* Page/Tab Toggle */}
          <div className="flex items-center bg-gray-900/50 rounded-lg p-0.5 border border-border mr-2">
            <button
              onClick={() => useArbitrageStore.getState().setActiveTab('dashboard')}
              className={`px-3 py-1 text-xs rounded-md font-medium transition-colors ${activeTab === 'dashboard' ? 'bg-accent/20 text-accent-light' : 'text-gray-500 hover:text-gray-300'}`}
            >
              Dashboard
            </button>
            <button
              onClick={() => useArbitrageStore.getState().setActiveTab('logs')}
              className={`px-3 py-1 text-xs rounded-md font-medium transition-colors ${activeTab === 'logs' ? 'bg-accent/20 text-accent-light' : 'text-gray-500 hover:text-gray-300'}`}
            >
              Logs
            </button>
            <button
              onClick={() => useArbitrageStore.getState().setActiveTab('analytics')}
              className={`px-3 py-1 text-xs rounded-md font-medium transition-colors ${activeTab === 'analytics' ? 'bg-accent/20 text-accent-light' : 'text-gray-500 hover:text-gray-300'}`}
            >
              Analytics
            </button>
          </div>

          {/* View Mode Toggle (only show on dashboard) */}
          {activeTab === 'dashboard' && (
            <div className="flex items-center bg-gray-900/50 rounded-lg p-0.5 border border-border">
              <button
                onClick={() => setViewMode('cards')}
                className={`p-1.5 rounded-md transition-colors ${viewMode === 'cards' ? 'bg-accent/20 text-accent-light' : 'text-gray-500 hover:text-gray-300'}`}
                title="Card Grid View"
              >
                 <LayoutGrid className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => setViewMode('heatmap')}
                className={`p-1.5 rounded-md transition-colors ${viewMode === 'heatmap' ? 'bg-accent/20 text-accent-light' : 'text-gray-500 hover:text-gray-300'}`}
                title="Heatmap View"
              >
                 <Table className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          {/* Uptime */}
          <div className="flex items-center gap-2 text-xs text-gray-400">
            <Clock className="w-3.5 h-3.5" />
            <span className="font-mono">{formatUptime(uptime)}</span>
          </div>
        </div>
      </div>

      {/* Status strip */}
      <div className="px-4 pb-2.5 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs">
        {/* WebSocket to backend */}
        <div className="flex items-center gap-1.5">
          <StatusDot status={wsStatus} />
          <span className="text-gray-400">WS</span>
          <span className={wsStatus === 'connected' ? 'text-green-400' : 'text-red-400'}>
            {wsStatus === 'connected' ? 'Live' : wsStatus}
          </span>
        </div>

        <div className="w-px h-4 bg-border" />

        {/* Dynamic exchange status — one dot per exchange */}
        {exchangesList.map((ex) => {
          const meta = exchangeMeta[ex];
          if (!meta) return null;
          const conn = meta.connected;
          const tot = meta.total;
          const exStatus: ConnectionStatus = conn === tot && tot > 0
            ? 'connected'
            : conn > 0 ? 'connecting' : 'disconnected';
          return (
            <div key={ex} className="flex items-center gap-1.5">
              <StatusDot status={exStatus} />
              <span className="text-gray-400">{meta.label}</span>
              <span className={`font-mono ${conn === tot && tot > 0 ? 'text-green-400' : conn > 0 ? 'text-yellow-400' : 'text-red-400'}`}>
                {conn}/{tot}
              </span>
            </div>
          );
        })}

        <div className="w-px h-4 bg-border" />

        {/* Total ticks */}
        <div className="flex items-center gap-1.5 text-gray-500">
          <Activity className="w-3 h-3" />
          <span className="font-mono">{totalTicks.toLocaleString()}</span>
          <span className="text-[10px] text-gray-700">ticks</span>
        </div>

        <div className="w-px h-4 bg-border" />

        {/* USDT/USDC rate */}
        <div className="flex items-center gap-1.5">
          <span className="text-gray-400">USDT/USDC</span>
          <span className={`font-mono font-semibold ${
            Math.abs(pegDev) < 0.05 ? 'text-green-400' :
            Math.abs(pegDev) < 0.1  ? 'text-yellow-400' : 'text-red-400'
          }`}>
            {rate.toFixed(6)}
            <span className="text-[10px] ml-1">({pegDev >= 0 ? '+' : ''}{pegDev.toFixed(4)}%)</span>
          </span>
        </div>

        <div className="flex-1" />

        {/* Opportunities counter */}
        <div className="flex items-center gap-1.5">
          <TrendingUp className={`w-3.5 h-3.5 ${activeOpps > 0 ? 'text-green-400' : 'text-gray-600'}`} />
          <span className={`font-mono font-bold ${activeOpps > 0 ? 'text-green-400' : 'text-gray-600'}`}>
            {activeOpps}
          </span>
          <span className="text-gray-500">active</span>
          <span className="text-gray-700 font-mono text-[10px]">({oppTotal} total)</span>
        </div>
      </div>
    </header>
  );
};
