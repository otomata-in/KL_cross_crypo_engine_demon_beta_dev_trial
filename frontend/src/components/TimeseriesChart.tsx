import React, { useEffect, useState } from 'react';
import { useArbitrageStore } from '../store';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';
import { RefreshCw, Activity } from 'lucide-react';

export const TimeseriesChart: React.FC = () => {
  const [selectedToken, setSelectedToken] = useState<string>('SOL');
  const tokens = useArbitrageStore((s) => s.liveState?.tokens || []);
  const timeseriesData = useArbitrageStore((s) => s.timeseriesData);
  const data = timeseriesData[selectedToken];

  const fetchTimeseries = (token: string) => {
    window.dispatchEvent(
      new CustomEvent('ws-send', { 
        detail: { type: 'get_timeseries', token, interval: '5 minutes', limit: 100 } 
      })
    );
  };

  useEffect(() => {
    if (tokens.length > 0 && !data) {
      fetchTimeseries(selectedToken);
    }
  }, [tokens, selectedToken]);

  const handleTokenChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newToken = e.target.value;
    setSelectedToken(newToken);
    fetchTimeseries(newToken);
  };

  return (
    <div className="bg-card/30 rounded-xl border border-border p-6 mt-6">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2 text-gray-300">
          <Activity className="w-5 h-5 text-accent-light" />
          <h3 className="font-semibold text-lg">Opportunity Time-Series</h3>
        </div>
        
        <div className="flex gap-4">
          <select 
            value={selectedToken}
            onChange={handleTokenChange}
            className="px-3 py-1.5 bg-surface border border-border rounded-lg text-sm text-gray-300 focus:outline-none focus:border-accent-light"
          >
            {tokens.map(t => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <button 
            onClick={() => fetchTimeseries(selectedToken)}
            className="flex items-center justify-center p-2 bg-surface hover:bg-card border border-border rounded-lg transition-colors"
          >
            <RefreshCw className="w-4 h-4 text-gray-400" />
          </button>
        </div>
      </div>

      <div className="h-72 w-full">
        {!data || !data.series || data.series.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-500">
            No spread data available for {selectedToken} in the recent timeframe.
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart
              data={[...data.series].reverse()} // Reverse so oldest is on left
              margin={{ top: 5, right: 30, left: -20, bottom: 5 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#2D3748" vertical={false} />
              <XAxis 
                dataKey="bucket" 
                tickFormatter={(val) => {
                  const d = new Date(val);
                  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`;
                }}
                stroke="#4A5568"
                fontSize={12}
                tickMargin={10}
              />
              <YAxis 
                stroke="#4A5568" 
                fontSize={12}
                tickFormatter={(val) => `${val.toFixed(2)}%`}
              />
              <Tooltip 
                contentStyle={{ backgroundColor: '#1A202C', borderColor: '#2D3748', borderRadius: '8px' }}
                itemStyle={{ color: '#E2E8F0' }}
                labelFormatter={(val) => new Date(val).toLocaleTimeString()}
                formatter={(val: any) => [`${Number(val).toFixed(3)}%`, 'Spread']}
              />
              <Legend wrapperStyle={{ paddingTop: '20px' }} />
              <Line 
                type="monotone" 
                dataKey="max_net" 
                name="Max Net Spread" 
                stroke="#00D2FF" 
                strokeWidth={2}
                dot={{ r: 3, fill: '#00D2FF', strokeWidth: 0 }}
                activeDot={{ r: 6 }}
              />
              <Line 
                type="monotone" 
                dataKey="avg_net" 
                name="Average Net Spread" 
                stroke="#3A6D8C" 
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
};
