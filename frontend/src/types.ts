// ── TypeScript types matching the ws_server.py JSON payload ──
// Multi-exchange version: supports N exchanges, M pairs

export interface ExchangeData {
  bid: number | null;
  ask: number | null;
  bid_depth: number;
  ask_depth: number;
  age_ms: number | null;
  status: string; // "connected" | "disconnected" | "error:..."
}

export interface SpreadPair {
  ex_buy:  string;    // "binance"
  ex_sell: string;    // "bybit"
  label:   string;    // "BIN→BYBIT"
  gross:   number | null;
  net:     number | null;
  fees:    number;    // pair-specific total fees (%)
}

export interface OppLast {
  time: string;       // "14:23:05"
  spread: number;
  net: number;
  direction: string;  // "BuyBIN→SellBP"
  pair: string;       // "binance→backpack"
}

export interface OpportunityRecord {
  timestamp_utc: string;
  token: string;
  ex_buy: string;
  ex_sell: string;
  direction: string;
  gross_spread_pct: string | number;
  net_spread_pct: string | number;
  pair_fees_pct: string | number;
  buy_ask: string | number;
  sell_bid: string | number;
  usdt_usdc_rate: string | number;
}

export interface AnalyticsData {
  top_coins: {
    token: string;
    count: number;
    best_route: string | null;
    max_net: number;
  }[];
  peak_hour: [string, number] | null;
  peak_day: [string, number] | null;
  total_opps: number;
}

export interface TokenData {
  category: string;
  exchanges: Record<string, ExchangeData>;  // keyed by exchange name
  spread_pairs: SpreadPair[];               // all pair×direction spreads
  best_net: number | null;                  // best net spread across all pairs
  best_net_label: string | null;            // "BIN→BP"
  best_gross: number | null;                // gross of the best net pair
  best_fees: number | null;                 // fees of the best net pair
  session_high_net: number | null;
  opp_count: number;
  opp_best: number | null;
  opp_last: OppLast | null;
}

export interface ExchangeMeta {
  label: string;
  quote: string;
  connected: number;
  total: number;
}

export interface PairFees {
  ex_a: string;
  ex_b: string;
  label: string;     // "BIN↔BP"
  total: number;
}

export interface LiveState {
  timestamp: string;
  uptime_seconds: number;
  threshold: number;

  // Multi-exchange info
  exchanges_list: string[];                       // ["binance","backpack","bybit","dextrade"]
  exchange_meta: Record<string, ExchangeMeta>;    // per-exchange status
  pair_fees: Record<string, PairFees>;            // pair fee details

  total_tokens: number;
  update_count: Record<string, number>;           // {binance: 1234, bybit: 567, ...}

  // Peg
  usdt_usdc_rate: number;

  // Opportunities
  opp_total: number;

  // Structure
  categories: Record<string, string[]>;
  tokens: string[];

  // Per-token data
  token_data: Record<string, TokenData>;
}

export interface TimeseriesPoint {
  bucket: string;
  max_net: number;
  avg_net: number;
}

export interface TimeseriesData {
  token: string;
  interval: string;
  series: TimeseriesPoint[];
}

export interface ConsistencyRow {
  token: string;
  route: string;
  first_seen: string;
  last_seen: string;
  duration_seconds: number;
  max_net: number;
  observations: number;
}

export interface TradeGroup {
  trade_id: string;
  token: string;
  route: string;
  target_spread: number;
  status: string;
  realized_pnl: number | null;
  is_mock: boolean;
  created_at: string;
}

export interface RebalanceTransfer {
  transfer_id: string;
  asset: string;
  amount: number;
  source_ex: string;
  dest_ex: string;
  status: string;
  tx_hash: string | null;
  is_mock: boolean;
  created_at: string;
  updated_at: string;
}

export interface TradeStateData {
  active_trades: TradeGroup[];
  history: any[]; // Using any for simplicity right now
  rebalances: RebalanceTransfer[];
}

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error';
