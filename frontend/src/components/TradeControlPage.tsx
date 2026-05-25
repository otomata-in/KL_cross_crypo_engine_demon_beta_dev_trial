import React, { useEffect, useState } from 'react';
import { useArbitrageStore } from '../store';
import { 
  Play, 
  Square, 
  AlertOctagon, 
  ShieldAlert, 
  Activity,
  ArrowRightLeft,
  CheckCircle,
  RefreshCw,
  Trash2
} from 'lucide-react';

const formatPnl = (pnl: number | null | undefined): { text: string; className: string } => {
  if (pnl === null || pnl === undefined) {
    return { text: '$0.0000', className: 'text-gray-500 font-bold font-mono' };
  }
  // Use 6 decimals for very small values, 4 for larger
  const decimals = Math.abs(pnl) < 0.001 && Math.abs(pnl) > 0 ? 6 : 4;
  if (pnl > 0) {
    return { text: `+$${pnl.toFixed(decimals)}`, className: 'text-green-400 font-bold font-mono' };
  } else if (pnl < 0) {
    return { text: `-$${Math.abs(pnl).toFixed(decimals)}`, className: 'text-red-400 font-bold font-mono' };
  }
  return { text: '$0.0000', className: 'text-gray-500 font-bold font-mono' };
};

export const TradeControlPage: React.FC = () => {
  const autoTradeEnabled = useArbitrageStore((s) => s.autoTradeEnabled);
  const isProMode = useArbitrageStore((s) => s.isProMode);
  const tradeState = useArbitrageStore((s) => s.tradeState);
  const pnlAnalyticsData = useArbitrageStore((s) => s.pnlAnalyticsData);

  const [timeframe, setTimeframe] = useState<'session' | 'day' | 'week' | 'month' | 'all'>('session');
  const [exchangeFilter, setExchangeFilter] = useState<string>('all');

  useEffect(() => {
    // Fetch initial state
    window.dispatchEvent(
      new CustomEvent('ws-send', { detail: { type: 'get_trade_state' } })
    );
    window.dispatchEvent(
      new CustomEvent('ws-send', { detail: { type: 'get_pnl_analytics', timeframe, exchange: exchangeFilter } })
    );
    
    // Poll every 5s
    const interval = setInterval(() => {
      window.dispatchEvent(
        new CustomEvent('ws-send', { detail: { type: 'get_trade_state' } })
      );
      window.dispatchEvent(
        new CustomEvent('ws-send', { detail: { type: 'get_pnl_analytics', timeframe, exchange: exchangeFilter } })
      );
    }, 5000);
    return () => clearInterval(interval);
  }, [timeframe, exchangeFilter]);

  const toggleAutoTrade = () => {
    window.dispatchEvent(
      new CustomEvent('ws-send', { 
        detail: { type: 'toggle_autotrader', enabled: !autoTradeEnabled } 
      })
    );
  };

  const toggleProMode = () => {
    window.dispatchEvent(
      new CustomEvent('ws-send', { 
        detail: { type: 'toggle_pro_mode', enabled: !isProMode } 
      })
    );
  };

  const killSwitch = () => {
    window.dispatchEvent(
      new CustomEvent('ws-send', { detail: { type: 'kill_switch' } })
    );
  };

  const resetMockWallets = () => {
    if (window.confirm('⚠️ This will DELETE all mock trade history and reset all wallets to $250. Continue?')) {
      window.dispatchEvent(
        new CustomEvent('ws-send', { detail: { type: 'reset_mock_wallets' } })
      );
    }
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6 pb-20">
      
      {/* HEADER & TOGGLES */}
      <div className="flex flex-col md:flex-row items-center justify-between bg-card/30 rounded-xl border border-border p-6">
        <div>
          <h2 className="text-2xl font-bold text-gray-100 flex items-center gap-3">
            <Activity className="w-6 h-6 text-accent-light" />
            Trade Control Center
          </h2>
          <p className="text-sm text-gray-500 mt-1">Manage simultaneous split-wallet executions</p>
        </div>

        <div className="flex items-center gap-4 mt-4 md:mt-0">
          <div className="flex bg-surface rounded-lg p-1 border border-border">
            <button
              onClick={() => isProMode && toggleProMode()}
              className={`px-4 py-1.5 rounded-md text-sm font-semibold transition-colors ${
                !isProMode ? 'bg-accent text-white' : 'text-gray-400 hover:text-white'
              }`}
            >
              Mock Mode
            </button>
            <button
              onClick={() => !isProMode && toggleProMode()}
              className={`px-4 py-1.5 rounded-md text-sm font-semibold transition-colors flex items-center gap-2 ${
                isProMode ? 'bg-red-500/20 text-red-500 border border-red-500/50' : 'text-gray-400 hover:text-white'
              }`}
            >
              {isProMode && <AlertOctagon className="w-4 h-4" />}
              PRO Mode
            </button>
          </div>
        </div>
      </div>

      {/* COMMAND CENTER */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-card/30 rounded-xl border border-border p-6 flex flex-col justify-center items-center gap-6">
          <div className="text-center">
            <h3 className="text-lg font-semibold text-gray-300">Auto-Trader Engine</h3>
            <p className="text-xs text-gray-500">Automatically executes 5% split-wallet trades</p>
          </div>
          
          <button
            onClick={toggleAutoTrade}
            className={`flex items-center gap-3 px-8 py-4 rounded-full text-lg font-bold uppercase tracking-wider transition-all shadow-lg ${
              autoTradeEnabled 
                ? 'bg-red-500/10 text-red-500 border border-red-500/50 hover:bg-red-500/20 shadow-red-500/20'
                : 'bg-green-500/10 text-green-500 border border-green-500/50 hover:bg-green-500/20 shadow-green-500/20'
            }`}
          >
            {autoTradeEnabled ? (
              <><Square className="w-6 h-6 fill-current" /> Stop Auto-Trade</>
            ) : (
              <><Play className="w-6 h-6 fill-current" /> Start Auto-Trade</>
            )}
          </button>
        </div>

        <div className="bg-red-500/5 rounded-xl border border-red-500/20 p-6 flex flex-col justify-center items-center gap-6">
          <div className="text-center">
            <h3 className="text-lg font-semibold text-red-400">Emergency Override</h3>
            <p className="text-xs text-red-500/70">Instantly halt operations & revert exposed legs</p>
          </div>
          
          <div className="flex gap-3">
            <button
              onClick={killSwitch}
              className="flex items-center gap-2 px-6 py-3 bg-red-600 hover:bg-red-500 text-white rounded-lg font-bold uppercase transition-colors shadow-lg shadow-red-600/20"
            >
              <ShieldAlert className="w-5 h-5" />
              Kill Switch
            </button>
            <button
              onClick={resetMockWallets}
              className="flex items-center gap-2 px-5 py-3 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg font-bold uppercase text-sm transition-colors border border-gray-600"
            >
              <Trash2 className="w-4 h-4" />
              Reset Mock
            </button>
          </div>
        </div>
      </div>

      {/* PNL ANALYTICS DASHBOARD */}
      <div className="bg-card/30 rounded-xl border border-border overflow-hidden">
        <div className="px-6 py-4 border-b border-border bg-surface/30 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <h3 className="font-semibold text-gray-200 flex items-center gap-2">
            <Activity className="w-4 h-4 text-accent-light" />
            Net PnL Analytics
          </h3>
          
          <div className="flex flex-wrap items-center gap-3">
            {/* Exchange Filter */}
            <select
              value={exchangeFilter}
              onChange={(e) => setExchangeFilter(e.target.value)}
              className="bg-surface border border-border rounded-lg px-3 py-1.5 text-sm text-gray-300 focus:outline-none focus:border-accent"
            >
              <option value="all">All Exchanges</option>
              <option value="binance">Binance</option>
              <option value="backpack">Backpack</option>
              <option value="bybit">Bybit</option>
              <option value="dextrade">Dex-Trade</option>
            </select>

            {/* Timeframe Tabs */}
            <div className="flex bg-surface rounded-lg p-1 border border-border text-xs font-semibold">
              {(['session', 'day', 'week', 'month', 'all'] as const).map((tf) => (
                <button
                  key={tf}
                  onClick={() => setTimeframe(tf)}
                  className={`px-3 py-1 rounded-md transition-colors ${
                    timeframe === tf ? 'bg-accent text-white' : 'text-gray-400 hover:text-white'
                  }`}
                >
                  {tf === 'session' ? 'Session' : tf === 'day' ? '24H' : tf === 'week' ? '7D' : tf === 'month' ? '30D' : 'All-Time'}
                </button>
              ))}
            </div>
          </div>
        </div>
        
        <div className="p-0 overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs uppercase bg-surface/50 text-gray-500">
              <tr>
                <th className="px-6 py-3">Asset</th>
                <th className="px-6 py-3 text-center">Trade Count</th>
                <th className="px-6 py-3 text-right">Net Profit / Loss</th>
              </tr>
            </thead>
            <tbody>
              {!pnlAnalyticsData || pnlAnalyticsData.length === 0 ? (
                <tr>
                  <td colSpan={3} className="px-6 py-8 text-center text-gray-500">
                    No profitable trades found for this timeframe/filter.
                  </td>
                </tr>
              ) : (
                pnlAnalyticsData.map((row) => {
                  const pnl = formatPnl(row.total_pnl);
                  return (
                    <tr key={row.token} className="border-b border-border/50 hover:bg-surface/30 transition-colors">
                      <td className="px-6 py-4 font-bold text-gray-200">{row.token}</td>
                      <td className="px-6 py-4 text-center font-mono text-gray-400">{row.trade_count}</td>
                      <td className="px-6 py-4 text-right">
                        <span className={`${pnl.className} flex items-center justify-end gap-1 text-base`}>
                          {row.total_pnl > 0 && <CheckCircle className="w-4 h-4" />}
                          {pnl.text}
                        </span>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* LIVE WALLET BALANCES */}
      {tradeState?.balances && (
        <div className="bg-card/30 rounded-xl border border-border overflow-hidden">
          <div className="px-6 py-4 border-b border-border bg-surface/30">
            <h3 className="font-semibold text-gray-200 flex items-center gap-2">
              <RefreshCw className="w-4 h-4 text-blue-400" />
              Live Wallet Balances (Mock)
            </h3>
          </div>
          <div className="p-4 grid grid-cols-1 md:grid-cols-3 gap-4">
            {Object.entries(tradeState.balances).map(([exchange, assets]) => (
              <div key={exchange} className="bg-surface/40 rounded-lg p-4 border border-border/50">
                <h4 className="text-sm font-bold text-gray-300 uppercase mb-3">{exchange}</h4>
                <div className="space-y-1.5">
                  {Object.entries(assets as Record<string, number>)
                    .filter(([, val]) => Math.abs(val) > 0.001)
                    .sort(([a], [b]) => a === 'USDT' ? -1 : b === 'USDT' ? 1 : a.localeCompare(b))
                    .map(([asset, value]) => (
                      <div key={asset} className="flex justify-between text-xs font-mono">
                        <span className="text-gray-400">{asset}</span>
                        <span className={asset === 'USDT' ? 'text-green-400' : 'text-blue-300'}>
                          {asset === 'USDT' ? `$${(value as number).toFixed(2)}` : `${(value as number).toFixed(4)}`}
                        </span>
                      </div>
                    ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ACTIVE TRADES */}
      <div className="bg-card/30 rounded-xl border border-border overflow-hidden">
        <div className="px-6 py-4 border-b border-border bg-surface/30">
          <h3 className="font-semibold text-gray-200">Active Executions</h3>
        </div>
        <div className="p-0 overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs uppercase bg-surface/50 text-gray-500">
              <tr>
                <th className="px-6 py-3">Trade ID</th>
                <th className="px-6 py-3">Route</th>
                <th className="px-6 py-3">Target Spread</th>
                <th className="px-6 py-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {!tradeState?.active_trades || tradeState.active_trades.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-6 py-8 text-center text-gray-500">
                    No active trades executing right now.
                  </td>
                </tr>
              ) : (
                tradeState.active_trades.map(t => (
                  <tr key={t.trade_id} className="border-b border-border/50">
                    <td className="px-6 py-4 font-mono text-xs">{t.trade_id}</td>
                    <td className="px-6 py-4">
                      <span className="font-bold text-gray-300">{t.token}</span>{' '}
                      <span className="text-gray-500 text-xs">{t.route}</span>
                    </td>
                    <td className="px-6 py-4 text-accent-light">+{t.target_spread.toFixed(3)}%</td>
                    <td className="px-6 py-4">
                      <span className="animate-pulse text-yellow-500 text-xs font-bold uppercase">
                        {t.status}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* REBALANCE TRACKER */}
      <div className="bg-card/30 rounded-xl border border-border overflow-hidden">
        <div className="px-6 py-4 border-b border-border bg-surface/30">
          <h3 className="font-semibold text-gray-200">Solana Rebalance Transfers</h3>
        </div>
        <div className="p-0 overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs uppercase bg-surface/50 text-gray-500">
              <tr>
                <th className="px-6 py-3">Route</th>
                <th className="px-6 py-3">Asset</th>
                <th className="px-6 py-3 text-right">Amount</th>
                <th className="px-6 py-3 text-center">Status</th>
              </tr>
            </thead>
            <tbody>
              {!tradeState?.rebalances || tradeState.rebalances.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-6 py-6 text-center text-gray-500">
                    No active on-chain rebalances.
                  </td>
                </tr>
              ) : (
                tradeState.rebalances.map(r => (
                  <tr key={r.transfer_id} className="border-b border-border/50">
                    <td className="px-6 py-3 text-xs text-gray-400">
                      {r.source_ex} <ArrowRightLeft className="w-3 h-3 inline mx-1" /> {r.dest_ex}
                    </td>
                    <td className="px-6 py-3 font-bold text-gray-300">{r.asset}</td>
                    <td className="px-6 py-3 text-right font-mono">{r.amount.toFixed(2)}</td>
                    <td className="px-6 py-3 text-center">
                      <span className="text-xs font-bold uppercase text-blue-400">
                        {r.status}
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* TRADE HISTORY */}
      <div className="bg-card/30 rounded-xl border border-border overflow-hidden">
        <div className="px-6 py-4 border-b border-border bg-surface/30">
          <h3 className="font-semibold text-gray-200">Trade Ledger (Completed)</h3>
        </div>
        <div className="p-0 overflow-x-auto">
          <table className="w-full text-sm text-left">
            <thead className="text-xs uppercase bg-surface/50 text-gray-500">
              <tr>
                <th className="px-6 py-3">Time</th>
                <th className="px-6 py-3">Route & Status</th>
                <th className="px-6 py-3">Leg Values</th>
                <th className="px-6 py-3">Wallet Deltas</th>
                <th className="px-6 py-3 text-right">Fees</th>
                <th className="px-6 py-3 text-right">Net PnL</th>
              </tr>
            </thead>
            <tbody>
              {!tradeState?.history || tradeState.history.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-gray-500">
                    No completed trades yet.
                  </td>
                </tr>
              ) : (
                tradeState.history.map((t: any, idx: number) => {
                  const isRebalance = t.is_rebalance === true;
                  const pnl = formatPnl(t.net_pnl);
                  const fees = formatPnl(t.total_fees ? -Math.abs(t.total_fees) : 0);

                  return (
                    <tr key={idx} className={`border-b border-border/50 hover:bg-surface/30 transition-colors ${
                      isRebalance ? 'bg-blue-500/5 border-l-2 border-l-blue-500' : ''
                    }`}>
                      <td className="px-6 py-3 text-xs text-gray-400">
                        <div className="flex flex-col gap-1">
                          <span>{new Date(t.trade_time).toLocaleTimeString()}</span>
                          {isRebalance ? (
                            <span className="text-[9px] uppercase font-bold text-blue-400 bg-blue-400/10 px-1.5 py-0.5 rounded border border-blue-500/30 w-fit flex items-center gap-1">
                              <RefreshCw className="w-2.5 h-2.5" />
                              Rebalance
                            </span>
                          ) : t.is_mock ? (
                            <span className="text-[9px] uppercase font-bold text-gray-500 bg-gray-500/10 px-1 py-0.5 rounded w-fit">Mock</span>
                          ) : (
                            <span className="text-[9px] uppercase font-bold text-red-400 bg-red-400/10 px-1 py-0.5 rounded border border-red-500/30 w-fit">Pro</span>
                          )}
                        </div>
                      </td>
                      <td className="px-6 py-3">
                        <div className="flex flex-col gap-1">
                          {isRebalance ? (
                            <>
                              <span className="font-bold text-blue-300 text-xs flex items-center gap-1">
                                <RefreshCw className="w-3 h-3" />
                                {t.ex_sell} ➡️ {t.ex_buy}
                              </span>
                              <span className="text-[10px] font-mono text-blue-400">
                                {t.buy_qty?.toFixed(4)} {t.token || 'USDT'} transferred
                              </span>
                            </>
                          ) : (
                            <>
                              <span className="font-bold text-gray-300 text-xs">
                                {t.ex_buy} ➡️ {t.ex_sell}
                              </span>
                              <div className="flex gap-2 text-[10px] font-mono">
                                 <span className={t.buy_status === 'filled' ? 'text-green-400' : 'text-yellow-500'}>
                                   BUY: {t.buy_status || 'N/A'}
                                 </span>
                                 <span className={t.sell_status === 'filled' ? 'text-green-400' : 'text-yellow-500'}>
                                   SELL: {t.sell_status || 'N/A'}
                                 </span>
                              </div>
                            </>
                          )}
                        </div>
                      </td>
                      <td className="px-6 py-3">
                        {isRebalance ? (
                          <div className="text-xs font-mono text-blue-300">
                            {t.buy_value?.toFixed(4)} {t.token}
                          </div>
                        ) : (
                          <div className="flex flex-col gap-1 text-xs font-mono">
                            <span className="text-gray-400">Buy: ${t.buy_value?.toFixed(4)}</span>
                            <span className="text-gray-400">Sell: ${t.sell_value?.toFixed(4)}</span>
                          </div>
                        )}
                      </td>
                      <td className="px-6 py-3">
                        {isRebalance ? (
                          <div className="flex flex-col gap-1 text-[10px] font-mono">
                            <span className="text-red-400">-{t.buy_qty?.toFixed(4)} {t.token} ({t.ex_sell})</span>
                            <span className="text-green-400">+{t.buy_qty?.toFixed(4)} {t.token} ({t.ex_buy})</span>
                          </div>
                        ) : (
                          <div className="flex flex-col gap-1 text-[10px] font-mono">
                            <span className="text-gray-400">
                              <span className="text-red-400">-${t.buy_value?.toFixed(4)} USDT</span> | <span className="text-green-400">+{t.buy_qty?.toFixed(4)} {t.token || 'TKN'}</span> ({t.ex_buy})
                            </span>
                            <span className="text-gray-400">
                              <span className="text-green-400">+${t.sell_value?.toFixed(4)} USDT</span> | <span className="text-red-400">-{t.sell_qty?.toFixed(4)} {t.token || 'TKN'}</span> ({t.ex_sell})
                            </span>
                          </div>
                        )}
                      </td>
                      <td className="px-6 py-3 text-right">
                        {isRebalance ? (
                          <span className="text-gray-500 font-mono text-xs">—</span>
                        ) : (
                          <span className={fees.className}>{fees.text}</span>
                        )}
                      </td>
                      <td className="px-6 py-3 text-right">
                        {isRebalance ? (
                          <span className="text-blue-400 font-mono text-xs">↻ balanced</span>
                        ) : (
                          <span className={`${pnl.className} flex items-center justify-end gap-1`}>
                            {t.net_pnl > 0 && <CheckCircle className="w-3 h-3" />}
                            {pnl.text}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

    </div>
  );
};
