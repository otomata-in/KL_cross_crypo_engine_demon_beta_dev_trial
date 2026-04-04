import React from 'react';

interface TokenSpreadBarProps {
  token: string;
  spread: number | null;
  threshold: number;
  pairLabel?: string;  // e.g. "BIN→BP"
}

export const TokenSpreadBar: React.FC<TokenSpreadBarProps> = ({ token, spread, threshold, pairLabel }) => {
  if (spread === null) {
    return (
      <div className="flex items-center w-full h-10 px-4 bg-gray-900/50 rounded-lg border border-border">
        <span className="text-gray-500 font-mono font-bold w-16">{token}</span>
        <span className="text-gray-700 italic ml-auto text-xs">Waiting...</span>
      </div>
    );
  }

  const maxVisualSpread = 2.0;
  const isPositive = spread > 0;
  const isOpportunity = spread >= threshold;
  const fillPercentage = Math.min((Math.abs(spread) / maxVisualSpread) * 100, 100);

  return (
    <div className={`relative flex items-center w-full h-10 bg-gray-900/50 rounded-lg border overflow-hidden transition-all duration-200 ${
      isOpportunity ? 'border-green-500/40 animate-pulse-glow' : 'border-border'
    }`}>
      {/* Center zero-line */}
      <div className="absolute left-1/2 top-0 bottom-0 w-px bg-gray-600/40 z-10" />

      {/* Negative bar (left) */}
      {!isPositive && spread !== 0 && (
        <div
          className="absolute right-1/2 top-1 bottom-1 bg-red-900/60 border border-red-800/30 rounded-l transition-all duration-100 ease-linear"
          style={{ width: `${fillPercentage / 2}%` }}
        />
      )}

      {/* Positive bar (right) */}
      {isPositive && (
        <div
          className={`absolute left-1/2 top-1 bottom-1 rounded-r transition-all duration-100 ease-linear ${
            isOpportunity
              ? 'bg-green-500/80 shadow-[0_0_12px_var(--color-spread-glow)]'
              : 'bg-green-900/60 border border-green-800/30'
          }`}
          style={{ width: `${fillPercentage / 2}%` }}
        />
      )}

      {/* Text overlay */}
      <div className="relative z-20 flex justify-between items-center w-full px-4 pointer-events-none">
        <div className="flex items-center gap-2">
          <span className="text-white font-mono font-bold w-16 text-sm drop-shadow-md">
            {token}
          </span>
          {pairLabel && (
            <span className="text-purple-400/60 text-[9px] font-mono drop-shadow-md">
              {pairLabel}
            </span>
          )}
        </div>
        <span className={`font-mono text-xs font-bold drop-shadow-md ${
          isOpportunity ? 'text-white' :
          isPositive ? 'text-green-400' : 'text-red-400'
        }`}>
          {spread > 0 ? '+' : ''}{spread.toFixed(3)}%
        </span>
      </div>
    </div>
  );
};
