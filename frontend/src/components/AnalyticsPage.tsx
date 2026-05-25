import React, { useEffect, useState } from 'react';
import { useArbitrageStore } from '../store';
import { Clock, Calendar, AlertTriangle, RefreshCw, Trash2, Trophy } from 'lucide-react';

export const AnalyticsPage: React.FC = () => {
  const analyticsData = useArbitrageStore((s) => s.analyticsData);
  const [isClearing, setIsClearing] = useState(false);

  // Auto-fetch on mount if null
  useEffect(() => {
    if (!analyticsData) {
      refreshAnalytics();
    }
  }, [analyticsData]);

  const refreshAnalytics = () => {
    // Send message via WebSocket
    const store = useArbitrageStore.getState();
    if (store.wsStatus === 'connected') {
      // Find the existing socket or send an event. 
      // Actually, since ws isn't globally exported easily, we can dispatch a custom event.
      // But for simplicity, we know window.ws is sometimes attached or we can just use a global
      window.dispatchEvent(new CustomEvent('ws-send', { detail: { type: 'get_analytics' } }));
    }
  };

  const clearLogs = () => {
    if (confirm("Are you sure you want to completely clear the historical logs? This cannot be undone.")) {
      setIsClearing(true);
      window.dispatchEvent(new CustomEvent('ws-send', { detail: { type: 'reset_logs' } }));
      setTimeout(() => setIsClearing(false), 1000);
    }
  };

  if (!analyticsData) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-gray-500 space-y-4">
        <RefreshCw className="w-8 h-8 animate-spin" />
        <p>Crunching historical data...</p>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-gray-200">Historical Analytics</h2>
          <p className="text-sm text-gray-500 mt-1">
            Analyzing {analyticsData.total_opps.toLocaleString()} total logged opportunities.
          </p>
        </div>
        <div className="flex gap-3">
          <button 
            onClick={refreshAnalytics}
            className="flex items-center gap-2 px-4 py-2 bg-card/50 hover:bg-card border border-border rounded-lg text-sm transition-colors"
          >
            <RefreshCw className="w-4 h-4 text-accent-light" />
            Refresh
          </button>
          <button 
            onClick={clearLogs}
            disabled={isClearing}
            className="flex items-center gap-2 px-4 py-2 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/20 rounded-lg text-sm transition-colors"
          >
            <Trash2 className="w-4 h-4" />
            {isClearing ? 'Clearing...' : 'Clear Logs'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        
        {/* Top 5 Coins */}
        <div className="bg-card/30 rounded-xl border border-border p-6">
          <div className="flex items-center gap-2 mb-6 text-gray-300">
            <Trophy className="w-5 h-5 text-yellow-400" />
            <h3 className="font-semibold text-lg">Top 5 Profitable Coins</h3>
          </div>
          <div className="space-y-4">
            {analyticsData.top_coins.length === 0 ? (
              <p className="text-gray-500 text-sm italic">No data available yet.</p>
            ) : (
              analyticsData.top_coins.map((coin, idx) => (
                <div key={coin.token} className="flex items-center justify-between p-3 rounded-lg bg-surface/50 border border-border/50">
                  <div className="flex items-center gap-4">
                    <span className="text-xl font-bold text-gray-600 w-6">#{idx + 1}</span>
                    <div>
                      <h4 className="font-bold text-gray-200">{coin.token}</h4>
                      <p className="text-xs text-gray-500 mt-0.5">Best Route: <span className="text-gray-400">{coin.best_route ?? 'Unknown'}</span></p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="block font-mono text-lg text-accent-light">{coin.count.toLocaleString()}</span>
                    <span className="text-[10px] text-gray-500 uppercase">opps</span>
                  </div>
                  <div className="text-right ml-4">
                    <span className="block font-mono text-lg text-green-400">+{coin.max_net.toFixed(3)}%</span>
                    <span className="text-[10px] text-gray-500 uppercase">Max Net Spread</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="space-y-6">
          {/* Peak Time */}
          <div className="bg-card/30 rounded-xl border border-border p-6 flex items-start gap-4">
            <div className="p-3 bg-blue-500/10 rounded-lg">
              <Clock className="w-6 h-6 text-blue-400" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-300">Peak Trading Hour (IST)</h3>
              <p className="text-3xl font-bold text-gray-100 mt-2 font-mono">
                {analyticsData.peak_hour ? analyticsData.peak_hour[0] : '--:--'}
              </p>
              <p className="text-sm text-gray-500 mt-1">
                {analyticsData.peak_hour ? `${analyticsData.peak_hour[1].toLocaleString()} occurrences` : 'Waiting for data'}
              </p>
            </div>
          </div>

          {/* Peak Day */}
          <div className="bg-card/30 rounded-xl border border-border p-6 flex items-start gap-4">
            <div className="p-3 bg-purple-500/10 rounded-lg">
              <Calendar className="w-6 h-6 text-purple-400" />
            </div>
            <div>
              <h3 className="font-semibold text-gray-300">Most Active Day</h3>
              <p className="text-3xl font-bold text-gray-100 mt-2">
                {analyticsData.peak_day ? analyticsData.peak_day[0] : '----'}
              </p>
              <p className="text-sm text-gray-500 mt-1">
                {analyticsData.peak_day ? `${analyticsData.peak_day[1].toLocaleString()} occurrences` : 'Waiting for data'}
              </p>
            </div>
          </div>
          
          <div className="p-4 bg-yellow-500/10 border border-yellow-500/20 rounded-xl flex items-start gap-3">
             <AlertTriangle className="w-5 h-5 text-yellow-500 shrink-0 mt-0.5" />
             <div>
               <h4 className="text-sm font-semibold text-yellow-500">Historical Context</h4>
               <p className="text-xs text-yellow-500/80 mt-1">
                 These statistics are derived from your TimescaleDB opportunity history. Changing your minimum net profit threshold affects what gets logged, which naturally shifts these analytics over time.
               </p>
             </div>
          </div>

        </div>
      </div>
    </div>
  );
};
