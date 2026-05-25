import React, { useEffect } from 'react';
import { useArbitrageStore } from '../store';
import { ShieldCheck, RefreshCw, AlertTriangle } from 'lucide-react';

export const ConsistencyTable: React.FC = () => {
  const consistencyData = useArbitrageStore((s) => s.consistencyData);

  const fetchConsistency = () => {
    window.dispatchEvent(
      new CustomEvent('ws-send', { detail: { type: 'get_consistency', limit: 10 } })
    );
  };

  useEffect(() => {
    if (!consistencyData) {
      fetchConsistency();
    }
  }, [consistencyData]);

  return (
    <div className="bg-card/30 rounded-xl border border-border p-6 mt-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2 text-gray-300">
          <ShieldCheck className="w-5 h-5 text-green-400" />
          <h3 className="font-semibold text-lg">Spread Consistency Tracker</h3>
        </div>
        
        <button 
          onClick={fetchConsistency}
          className="flex items-center justify-center p-2 bg-surface hover:bg-card border border-border rounded-lg transition-colors"
        >
          <RefreshCw className="w-4 h-4 text-gray-400" />
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm text-left text-gray-400">
          <thead className="text-xs uppercase bg-surface/50 text-gray-500 border-b border-border/50">
            <tr>
              <th scope="col" className="px-4 py-3">Token</th>
              <th scope="col" className="px-4 py-3">Route</th>
              <th scope="col" className="px-4 py-3 text-right">Max Net</th>
              <th scope="col" className="px-4 py-3 text-right">Duration</th>
              <th scope="col" className="px-4 py-3 text-right">Observations</th>
              <th scope="col" className="px-4 py-3 text-center">Status</th>
            </tr>
          </thead>
          <tbody>
            {!consistencyData || consistencyData.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-500">
                  No sustained spreads ( &gt; 2 seconds ) found in the last 30 minutes.
                </td>
              </tr>
            ) : (
              consistencyData.map((row, idx) => (
                <tr key={`${row.token}-${row.route}-${idx}`} className="border-b border-border/30 hover:bg-surface/30">
                  <td className="px-4 py-3 font-semibold text-gray-200">{row.token}</td>
                  <td className="px-4 py-3">
                    <span className="px-2 py-1 bg-surface border border-border rounded text-xs text-gray-300">
                      {row.route.replace('->', ' → ')}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-green-400">
                    +{row.max_net.toFixed(3)}%
                  </td>
                  <td className="px-4 py-3 text-right font-mono">
                    {row.duration_seconds.toFixed(1)}s
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-gray-500">
                    {row.observations}
                  </td>
                  <td className="px-4 py-3 text-center">
                    {row.duration_seconds > 5 ? (
                      <span className="inline-flex items-center gap-1 text-[10px] uppercase font-bold text-green-400 bg-green-400/10 px-2 py-0.5 rounded">
                        Highly Executable
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-[10px] uppercase font-bold text-yellow-500 bg-yellow-500/10 px-2 py-0.5 rounded">
                        <AlertTriangle className="w-3 h-3" />
                        Fleeting
                      </span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
