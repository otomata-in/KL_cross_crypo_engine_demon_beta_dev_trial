// ── TypeScript types matching the ws_server.py JSON payload ──

export interface ExchangeData {
  bid: number | null;
  ask: number | null;
  bid_depth: number;
  ask_depth: number;
  age_ms: number | null;
  status: string; // "connected" | "disconnected" | "error:..."
}

export interface OppLast {
  time: string;       // "14:23:05"
  spread: number;
  net: number;
  direction: string;  // "BuyBIN→SellBP" | "BuyBP→SellBIN"
}

export interface TokenData {
  category: string;
  binance: ExchangeData;
  backpack: ExchangeData;
  spread_buy_bin: number | null;  // Buy on Binance → Sell on Backpack
  spread_buy_bp: number | null;   // Buy on Backpack → Sell on Binance
  session_high: number | null;
  opp_count: number;
  opp_best: number | null;
  opp_last: OppLast | null;
}

export interface LiveState {
  timestamp: string;
  uptime_seconds: number;
  threshold: number;

  // Exchange connectivity
  binance_connected: number;
  backpack_connected: number;
  total_tokens: number;
  update_count: { binance: number; backpack: number };

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

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error';
