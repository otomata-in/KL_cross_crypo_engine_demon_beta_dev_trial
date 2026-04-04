import React, { useEffect, useRef, useState } from 'react';
import { useArbitrageStore } from '../store';
import type { OppLast } from '../types';
import { ArrowRightLeft } from 'lucide-react';

interface FeedEntry {
  id: number;
  token: string;
  opp: OppLast;
  isNew: boolean;
}

let entryId = 0;

export const ActionFeed: React.FC = () => {
  const liveState = useArbitrageStore((s) => s.liveState);
  const threshold = useArbitrageStore((s) => s.threshold);
  const [entries, setEntries] = useState<FeedEntry[]>([]);
  const prevOppLastRef = useRef<Record<string, string>>({});
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!liveState) return;

    const newEntries: FeedEntry[] = [];

    for (const [token, opp] of Object.entries(liveState.token_data)) {
      const oppLast = opp.opp_last;
      if (!oppLast) continue;

      // Only show opportunities where net profit meets the threshold
      if (oppLast.net < threshold) continue;

      // Check if this is a new opportunity (different time from last seen)
      const key = `${token}-${oppLast.time}-${oppLast.direction}`;
      if (prevOppLastRef.current[token] === key) continue;
      prevOppLastRef.current[token] = key;

      newEntries.push({
        id: ++entryId,
        token,
        opp: oppLast,
        isNew: true,
      });
    }

    if (newEntries.length > 0) {
      setEntries((prev) => [...newEntries, ...prev].slice(0, 50)); // keep last 50
    }
  }, [liveState, threshold]);

  // Auto-scroll to top for newest entries
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = 0;
    }
  }, [entries.length]);

  // Filter existing entries by current threshold at render time
  // (so raising the slider hides old entries that no longer qualify)
  const filteredEntries = entries.filter((e) => e.opp.net >= threshold);

  if (filteredEntries.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-gray-700 text-sm italic">
        <div className="text-center">
          <ArrowRightLeft className="w-8 h-8 mx-auto mb-2 text-gray-800" />
          <p>No opportunities above {threshold.toFixed(1)}% net</p>
        </div>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="h-full overflow-y-auto space-y-1 pr-1">
      {filteredEntries.map((entry) => {
        const isProfit = entry.opp.net > 0;
        return (
          <div
            key={entry.id}
            className={`px-3 py-2 rounded-lg border text-xs font-mono transition-all duration-500 ${
              isProfit
                ? 'bg-green-950/20 border-green-900/30'
                : 'bg-card border-border'
            }`}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-bold text-white">{entry.token}</span>
                <span className="text-gray-600">{entry.opp.direction}</span>
              </div>
              <span className="text-gray-600">{entry.opp.time}</span>
            </div>
            <div className="flex items-center gap-3 mt-0.5">
              <span className={`font-semibold ${
                entry.opp.spread >= 1.0 ? 'text-green-400' : 'text-yellow-400'
              }`}>
                gross: +{entry.opp.spread.toFixed(3)}%
              </span>
              <span className={isProfit ? 'text-green-500' : 'text-red-400'}>
                net: {entry.opp.net >= 0 ? '+' : ''}{entry.opp.net.toFixed(3)}%
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
};
