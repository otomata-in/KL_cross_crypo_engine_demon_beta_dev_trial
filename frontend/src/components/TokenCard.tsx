import React from 'react';
import type { TokenData } from '../types';
import { TokenSpreadBar } from './TokenSpreadBar';

interface TokenCardProps {
  token: string;
  data: TokenData;
  threshold: number;
  exchangesList: string[];
  exchangeLabels: Record<string, string>; // "binance" -> "BIN"
}

function formatPrice(price: number | null): string {
  if (price === null) return '—';
  if (price > 10000) return price.toFixed(2);
  if (price > 100) return price.toFixed(2);
  if (price > 1) return price.toFixed(4);
  return price.toFixed(6);
}

function AgeIndicator({ ageMs }: { ageMs: number | null }) {
  if (ageMs === null) return <span className="w-1.5 h-1.5 rounded-full bg-red-500 inline-block" />;
  if (ageMs < 2000) return <span className="w-1.5 h-1.5 rounded-full bg-green-500 inline-block" />;
  if (ageMs < 5000) return <span className="w-1.5 h-1.5 rounded-full bg-yellow-500 inline-block" />;
  return <span className="w-1.5 h-1.5 rounded-full bg-red-500 inline-block" />;
}

export const TokenCard: React.FC<TokenCardProps> = ({ token, data, threshold, exchangesList, exchangeLabels }) => {
  const bestNet = data.best_net ?? -Infinity;
  const bestGross = data.best_gross ?? -Infinity;
  const bestFees = data.best_fees ?? 0;
  const bestLabel = data.best_net_label ?? '';

  // An opportunity is "hot" when best net profit >= user's threshold
  const isHot = bestNet >= threshold && bestNet > -Infinity;

  const displaySpread = bestNet > -Infinity ? bestNet : null;

  // Only show exchanges that have data for this token
  const activeExchanges = exchangesList.filter(ex => {
    const exData = data.exchanges[ex];
    return exData && exData.status !== 'disconnected' && (exData.bid !== null || exData.ask !== null);
  });

  // Get the top spread pairs (sorted by net, descending) — show top 4
  const validPairs = data.spread_pairs
    .filter(sp => sp.net !== null)
    .sort((a, b) => (b.net ?? -Infinity) - (a.net ?? -Infinity))
    .slice(0, 4);

  return (
    <div className={`rounded-xl border p-3 transition-all duration-300 ${
      isHot
        ? 'bg-green-950/20 border-green-500/30 shadow-lg shadow-green-500/5'
        : 'bg-card border-border hover:border-border-subtle hover:bg-card-hover'
    }`}>
      {/* Spread bar — shows BEST NET spread */}
      <div className="space-y-1.5 mb-3">
        <TokenSpreadBar
          token={token}
          spread={displaySpread}
          threshold={threshold}
          pairLabel={bestLabel}
        />
      </div>

      {/* Best pair gross vs net breakdown */}
      {bestGross > -Infinity && (
        <div className="mb-2.5 px-1 flex items-center justify-between text-[10px] font-mono">
          <div className="flex items-center gap-2">
            <span className="text-gray-600">best:</span>
            <span className="text-purple-400/80 font-semibold">{bestLabel}</span>
          </div>
          <div className="flex items-center gap-1">
            <span className={bestGross > 0 ? 'text-yellow-400/70' : 'text-red-400/70'}>
              {bestGross > 0 ? '+' : ''}{bestGross.toFixed(3)}%
            </span>
            <span className="text-gray-700">−{bestFees.toFixed(2)}%</span>
            <span className="text-gray-700">=</span>
            <span className={`font-semibold ${
              bestNet >= threshold ? 'text-green-400' :
              bestNet > 0 ? 'text-yellow-400' : 'text-red-400'
            }`}>
              {bestNet > 0 ? '+' : ''}{bestNet.toFixed(3)}%
            </span>
          </div>
        </div>
      )}

      {/* Multi-exchange price table */}
      <div className="overflow-x-auto mb-2">
        <table className="w-full text-[10px] font-mono">
          <thead>
            <tr className="text-gray-600">
              <th className="text-left pr-2 font-normal"></th>
              {activeExchanges.map(ex => (
                <th key={ex} className="text-right px-1 font-normal">
                  <div className="flex items-center justify-end gap-1">
                    <AgeIndicator ageMs={data.exchanges[ex]?.age_ms ?? null} />
                    <span>{exchangeLabels[ex] ?? ex}</span>
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="text-gray-600 pr-2">Bid</td>
              {activeExchanges.map(ex => (
                <td key={ex} className="text-right px-1 text-green-400/80">
                  {formatPrice(data.exchanges[ex]?.bid ?? null)}
                </td>
              ))}
            </tr>
            <tr>
              <td className="text-gray-600 pr-2">Ask</td>
              {activeExchanges.map(ex => (
                <td key={ex} className="text-right px-1 text-red-400/80">
                  {formatPrice(data.exchanges[ex]?.ask ?? null)}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      {/* Top spread pairs */}
      {validPairs.length > 0 && (
        <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px] font-mono mb-2 px-1">
          {validPairs.map((sp, i) => (
            <div key={i} className="flex items-center justify-between">
              <span className="text-gray-600 truncate">{sp.label}</span>
              <span className={`ml-1 ${
                (sp.net ?? 0) >= threshold ? 'text-green-400 font-semibold' :
                (sp.net ?? 0) > 0 ? 'text-yellow-400/70' : 'text-red-400/60'
              }`}>
                {(sp.net ?? 0) > 0 ? '+' : ''}{(sp.net ?? 0).toFixed(3)}%
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Footer stats */}
      <div className="mt-1.5 pt-2 border-t border-border flex items-center justify-between text-[10px]">
        <div className="flex items-center gap-2">
          {data.opp_count > 0 ? (
            <span className="text-green-400 font-mono font-semibold">
              {data.opp_count} opps
            </span>
          ) : (
            <span className="text-gray-700 font-mono">0 opps</span>
          )}
          {data.opp_best !== null && data.opp_best > 0 && (
            <span className="text-green-500/70 font-mono">
              best: +{data.opp_best.toFixed(3)}%
            </span>
          )}
        </div>
        {data.session_high_net !== null && (
          <span className={`font-mono ${
            data.session_high_net >= threshold ? 'text-green-400' :
            data.session_high_net > 0 ? 'text-yellow-500/70' : 'text-gray-700'
          }`}>
            hi: {data.session_high_net > 0 ? '+' : ''}{data.session_high_net.toFixed(3)}%
          </span>
        )}
      </div>
    </div>
  );
};
