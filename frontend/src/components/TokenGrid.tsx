import React from 'react';
import { useArbitrageStore } from '../store';
import { TokenCard } from './TokenCard';

export const TokenGrid: React.FC = () => {
  const liveState = useArbitrageStore((s) => s.liveState);

  if (!liveState) return null;

  const { categories, token_data, threshold } = liveState;

  return (
    <div className="space-y-6">
      {Object.entries(categories).map(([categoryName, tokens]) => (
        <section key={categoryName}>
          {/* Category header */}
          <div className="flex items-center gap-2 mb-3 px-1">
            <h2 className="text-sm font-semibold text-gray-300">{categoryName}</h2>
            <div className="flex-1 h-px bg-gradient-to-r from-border to-transparent" />
            <span className="text-[10px] text-gray-600 font-mono">{tokens.length} tokens</span>
          </div>

          {/* Token cards grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {tokens.map((token) => {
              const data = token_data[token];
              if (!data) return null;
              return (
                <TokenCard
                  key={token}
                  token={token}
                  data={data}
                  threshold={threshold}
                />
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
};
