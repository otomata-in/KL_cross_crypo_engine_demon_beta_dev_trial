import React from 'react';
import type { ConnectionStatus } from '../types';
import { useArbitrageStore } from '../store';
import { Activity, Zap, Clock, TrendingUp } from 'lucide-react';

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

  const binConn = liveState?.binance_connected ?? 0;
  const bpConn = liveState?.backpack_connected ?? 0;
  const total = liveState?.total_tokens ?? 0;
  const rate = liveState?.usdt_usdc_rate ?? 1.0;
  const pegDev = (rate - 1.0) * 100;
  const uptime = liveState?.uptime_seconds ?? 0;
  const oppTotal = liveState?.opp_total ?? 0;
  const binTicks = liveState?.update_count?.binance ?? 0;
  const bpTicks = liveState?.update_count?.backpack ?? 0;

  const binStatus = binConn === total ? 'connected' : binConn > 0 ? 'connecting' : 'disconnected';
  const bpStatus = bpConn === total ? 'connected' : bpConn > 0 ? 'connecting' : 'disconnected';

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
          <span className="text-xs text-gray-500 font-mono ml-2">Binance ↔ Backpack</span>
        </div>

        <div className="flex items-center gap-2 text-xs text-gray-400">
          <Clock className="w-3.5 h-3.5" />
          <span className="font-mono">{formatUptime(uptime)}</span>
        </div>
      </div>

      {/* Status strip */}
      <div className="px-4 pb-2.5 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-xs">
        {/* WebSocket to backend */}
        <div className="flex items-center gap-1.5">
          <StatusDot status={wsStatus} />
          <span className="text-gray-400">WS</span>
          <span className={wsStatus === 'connected' ? 'text-green-400' : 'text-red-400'}>
            {wsStatus === 'connected' ? 'Live' : wsStatus}
          </span>
        </div>

        <div className="w-px h-4 bg-border" />

        {/* Binance */}
        <div className="flex items-center gap-1.5">
          <StatusDot status={binStatus} />
          <span className="text-gray-400">BIN</span>
          <span className={`font-mono ${binConn === total ? 'text-green-400' : 'text-yellow-400'}`}>
            {binConn}/{total}
          </span>
        </div>

        {/* Backpack */}
        <div className="flex items-center gap-1.5">
          <StatusDot status={bpStatus} />
          <span className="text-gray-400">BP</span>
          <span className={`font-mono ${bpConn === total ? 'text-green-400' : 'text-yellow-400'}`}>
            {bpConn}/{total}
          </span>
        </div>

        <div className="w-px h-4 bg-border" />

        {/* Ticks */}
        <div className="flex items-center gap-1.5 text-gray-500">
          <Activity className="w-3 h-3" />
          <span className="font-mono">{binTicks.toLocaleString()}</span>
          <span>/</span>
          <span className="font-mono">{bpTicks.toLocaleString()}</span>
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
          <TrendingUp className={`w-3.5 h-3.5 ${oppTotal > 0 ? 'text-green-400' : 'text-gray-600'}`} />
          <span className={`font-mono font-bold ${oppTotal > 0 ? 'text-green-400' : 'text-gray-600'}`}>
            {oppTotal}
          </span>
          <span className="text-gray-500">opps</span>
        </div>
      </div>
    </header>
  );
};
