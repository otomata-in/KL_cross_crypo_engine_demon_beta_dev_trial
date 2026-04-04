import React from 'react';
import { useArbitrageStore } from '../store';

export const MarketHeatmap: React.FC = () => {
  const liveState = useArbitrageStore((s) => s.liveState);
  const threshold = useArbitrageStore((s) => s.threshold);

  if (!liveState) return null;

  const { tokens, token_data } = liveState;

  // We want to extract a stable list of all directional pairs.
  // For each exchange pair (e.g. binance, backpack), there are two directions.
  // We can collect them by scanning the first valid token.
  const allPairs: { buy: string; sell: string; label: string }[] = [];
  
  if (tokens.length > 0 && token_data[tokens[0]]) {
    const sample = token_data[tokens[0]].spread_pairs;
    sample.forEach(sp => {
      allPairs.push({ buy: sp.ex_buy, sell: sp.ex_sell, label: sp.label });
    });
  }

  // Get color for a spread cell
  const getCellColor = (spread: number | null) => {
    if (spread === null) return 'bg-gray-900/20 text-gray-700'; // No data
    if (spread >= threshold) return 'bg-green-500/80 text-white shadow-[0_0_12px_rgba(34,197,94,0.3)] animate-pulse-glow'; // Live opportunity!
    if (spread > 0) return 'bg-yellow-900/30 text-yellow-400'; // Profitable but below threshold
    if (spread > -1.0) return 'bg-red-950/20 text-red-400/60'; // Slight loss
    return 'bg-red-950/40 text-red-500/40'; // Deep loss
  };

  return (
    <div className="w-full overflow-x-auto rounded-xl border border-border bg-card">
      <table className="w-full text-sm font-mono text-left border-collapse">
        <thead className="bg-surface/90 backdrop-blur sticky top-0 z-10 text-xs text-gray-400 uppercase tracking-wider">
          <tr>
            <th className="px-4 py-3 border-b border-border font-medium bg-surface/90 sticky left-0 z-20 w-24">
              Token
            </th>
            {allPairs.map((pair, idx) => (
              <th key={idx} className="px-3 py-3 border-b border-border font-medium whitespace-nowrap text-center">
                {pair.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {tokens.map(token => {
            const data = token_data[token];
            if (!data) return null;

            return (
              <tr key={token} className="hover:bg-card-hover transition-colors">
                <td className="px-4 py-2 border-r border-border font-bold text-gray-200 sticky left-0 bg-card z-10 w-24">
                  {token}
                </td>
                {allPairs.map((pair, idx) => {
                  const sp = data.spread_pairs.find(
                    s => s.ex_buy === pair.buy && s.ex_sell === pair.sell
                  );
                  const net = sp?.net ?? null;
                  
                  return (
                    <td key={idx} className="p-1">
                      <div className={`w-full h-full min-h-[2.5rem] rounded md:px-2 flex items-center justify-center font-semibold text-xs transition-all duration-300 ${getCellColor(net)}`}>
                        {net !== null ? `${net > 0 ? '+' : ''}${net.toFixed(2)}%` : '—'}
                      </div>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};
