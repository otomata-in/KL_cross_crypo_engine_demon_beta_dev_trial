import React from 'react';
import { useArbitrageStore } from '../store';
import { Clock, ArrowRight, TrendingUp } from 'lucide-react';

export const OpportunitiesPage: React.FC = () => {
  const opportunities = useArbitrageStore((s) => s.opportunities);

  return (
    <div className="h-full flex flex-col bg-card/30 rounded-xl border border-border overflow-hidden">
      <div className="px-6 py-4 border-b border-border bg-card/50">
        <h2 className="text-lg font-semibold text-gray-200 flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-accent-light" />
          Live Opportunities Log
        </h2>
        <p className="text-sm text-gray-500 mt-1">
          Streaming directly from the backend CSV log in real-time.
        </p>
      </div>

      <div className="flex-1 overflow-auto">
        <table className="w-full text-left text-sm whitespace-nowrap">
          <thead className="sticky top-0 bg-surface/95 backdrop-blur z-10 text-gray-400 text-xs uppercase tracking-wider shadow-sm">
            <tr>
              <th className="px-6 py-3 font-medium">Time (UTC)</th>
              <th className="px-6 py-3 font-medium">Token</th>
              <th className="px-6 py-3 font-medium">Path</th>
              <th className="px-6 py-3 font-medium text-right">Gross Spread</th>
              <th className="px-6 py-3 font-medium text-right">Fees</th>
              <th className="px-6 py-3 font-medium text-right">Net Spread</th>
              <th className="px-6 py-3 font-medium text-right">Prices (Buy → Sell)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {opportunities.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-6 py-8 text-center text-gray-500">
                  <div className="flex flex-col items-center justify-center space-y-2">
                    <Clock className="w-6 h-6 text-gray-600 animate-pulse" />
                    <p>Waiting for opportunities to appear...</p>
                  </div>
                </td>
              </tr>
            ) : (
              opportunities.map((opp, idx) => {
                const date = new Date(opp.timestamp_utc);
                const timeString = date.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute:'2-digit', second:'2-digit' }) + '.' + date.getMilliseconds().toString().padStart(3, '0');
                
                const net = parseFloat(String(opp.net_spread_pct));
                const isProfitable = net > 0;

                return (
                  <tr key={idx} className="hover:bg-card/40 transition-colors">
                    <td className="px-6 py-3 text-gray-400 font-mono text-xs">{timeString}</td>
                    <td className="px-6 py-3 font-semibold text-gray-200">{opp.token}</td>
                    <td className="px-6 py-3">
                      <div className="flex items-center gap-1.5 text-xs">
                        <span className="px-2 py-0.5 rounded-full bg-gray-800 text-gray-300 border border-gray-700">
                          {opp.ex_buy}
                        </span>
                        <ArrowRight className="w-3 h-3 text-gray-500" />
                        <span className="px-2 py-0.5 rounded-full bg-gray-800 text-gray-300 border border-gray-700">
                          {opp.ex_sell}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-3 text-right text-gray-400 font-mono">
                      {parseFloat(String(opp.gross_spread_pct)).toFixed(3)}%
                    </td>
                    <td className="px-6 py-3 text-right text-gray-500 font-mono">
                      -{parseFloat(String(opp.pair_fees_pct)).toFixed(3)}%
                    </td>
                    <td className={`px-6 py-3 text-right font-mono font-bold ${
                      isProfitable ? 'text-green-400' : 'text-red-400'
                    }`}>
                      {net > 0 ? '+' : ''}{net.toFixed(3)}%
                    </td>
                    <td className="px-6 py-3 text-right font-mono text-xs text-gray-400">
                      ${parseFloat(String(opp.buy_ask)).toFixed(4)} → ${parseFloat(String(opp.sell_bid)).toFixed(4)}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
