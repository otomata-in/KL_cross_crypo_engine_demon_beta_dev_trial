import React from 'react';
import type { TokenData } from '../types';
import { TokenSpreadBar } from './TokenSpreadBar';

interface TokenCardProps {
  token: string;
  data: TokenData;
  threshold: number;  // This is the user's desired NET profit threshold
  totalFeesPct: number;
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

export const TokenCard: React.FC<TokenCardProps> = ({ token, data, threshold, totalFeesPct }) => {
  // Use NET spread (after all costs) for all highlighting decisions
  const bestNetSpread = Math.max(data.net_spread_buy_bin ?? -Infinity, data.net_spread_buy_bp ?? -Infinity);
  const bestGrossSpread = Math.max(data.spread_buy_bin ?? -Infinity, data.spread_buy_bp ?? -Infinity);
  
  // An opportunity is "hot" when net profit >= user's threshold
  const isHot = bestNetSpread >= threshold;

  // The spread bar shows NET spread (what you actually take home)
  const displaySpread = bestNetSpread > -Infinity ? bestNetSpread : null;

  return (
    <div className={`rounded-xl border p-3 transition-all duration-300 ${
      isHot
        ? 'bg-green-950/20 border-green-500/30 shadow-lg shadow-green-500/5'
        : 'bg-card border-border hover:border-border-subtle hover:bg-card-hover'
    }`}>
      {/* Spread bar — shows NET spread */}
      <div className="space-y-1.5 mb-3">
        <TokenSpreadBar
          token={token}
          spread={displaySpread}
          threshold={threshold}
        />
      </div>

      {/* Gross vs Net breakdown */}
      {bestGrossSpread > -Infinity && (
        <div className="mb-2.5 px-1 flex items-center justify-between text-[10px] font-mono">
          <div className="flex items-center gap-2">
            <span className="text-gray-600">gross:</span>
            <span className={bestGrossSpread > 0 ? 'text-yellow-400/70' : 'text-red-400/70'}>
              {bestGrossSpread > 0 ? '+' : ''}{bestGrossSpread.toFixed(3)}%
            </span>
          </div>
          <div className="flex items-center gap-1">
            <span className="text-gray-700">−{totalFeesPct.toFixed(2)}%</span>
            <span className="text-gray-700">=</span>
            <span className={`font-semibold ${
              bestNetSpread >= threshold ? 'text-green-400' :
              bestNetSpread > 0 ? 'text-yellow-400' : 'text-red-400'
            }`}>
              net: {bestNetSpread > 0 ? '+' : ''}{bestNetSpread.toFixed(3)}%
            </span>
          </div>
        </div>
      )}

      {/* Price grid */}
      <div className="grid grid-cols-2 gap-2 text-xs">
        {/* Binance */}
        <div className="space-y-1">
          <div className="flex items-center gap-1 text-gray-500">
            <AgeIndicator ageMs={data.binance.age_ms} />
            <span>Binance</span>
          </div>
          <div className="font-mono text-gray-300 space-y-0.5">
            <div className="flex justify-between">
              <span className="text-gray-600">Bid</span>
              <span className="text-green-400/80">{formatPrice(data.binance.bid)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Ask</span>
              <span className="text-red-400/80">{formatPrice(data.binance.ask)}</span>
            </div>
          </div>
        </div>

        {/* Backpack */}
        <div className="space-y-1">
          <div className="flex items-center gap-1 text-gray-500">
            <AgeIndicator ageMs={data.backpack.age_ms} />
            <span>Backpack</span>
          </div>
          <div className="font-mono text-gray-300 space-y-0.5">
            <div className="flex justify-between">
              <span className="text-gray-600">Bid</span>
              <span className="text-green-400/80">{formatPrice(data.backpack.bid)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">Ask</span>
              <span className="text-red-400/80">{formatPrice(data.backpack.ask)}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Footer stats */}
      <div className="mt-2.5 pt-2 border-t border-border flex items-center justify-between text-[10px]">
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
            net hi: {data.session_high_net > 0 ? '+' : ''}{data.session_high_net.toFixed(3)}%
          </span>
        )}
      </div>
    </div>
  );
};
