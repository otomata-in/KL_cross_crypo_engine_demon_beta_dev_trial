import React from 'react';
import type { TokenData } from '../types';
import { TokenSpreadBar } from './TokenSpreadBar';

interface TokenCardProps {
  token: string;
  data: TokenData;
  threshold: number;
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

export const TokenCard: React.FC<TokenCardProps> = ({ token, data, threshold }) => {
  const bestSpread = Math.max(data.spread_buy_bin ?? -Infinity, data.spread_buy_bp ?? -Infinity);
  const isHot = bestSpread >= threshold;

  return (
    <div className={`rounded-xl border p-3 transition-all duration-300 ${
      isHot
        ? 'bg-green-950/20 border-green-500/30 shadow-lg shadow-green-500/5'
        : 'bg-card border-border hover:border-border-subtle hover:bg-card-hover'
    }`}>
      {/* Spread bars */}
      <div className="space-y-1.5 mb-3">
        <TokenSpreadBar
          token={`${token}`}
          spread={bestSpread > -Infinity ? bestSpread : null}
          threshold={threshold}
        />
      </div>

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
        {data.session_high !== null && (
          <span className={`font-mono ${
            data.session_high >= threshold ? 'text-green-400' :
            data.session_high > 0 ? 'text-yellow-500/70' : 'text-gray-700'
          }`}>
            hi: {data.session_high > 0 ? '+' : ''}{data.session_high.toFixed(3)}%
          </span>
        )}
      </div>
    </div>
  );
};
