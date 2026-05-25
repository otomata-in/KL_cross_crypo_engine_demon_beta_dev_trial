"""
app/engine/state.py — Global Live State
=========================================
Shared state for all exchange feeds and opportunity detector.
Extracted from ws_server.py to avoid circular dependencies.
"""

import time
from typing import Dict, Any, Set

from app.config import get_config

# Initial capital per exchange per asset
INITIAL_USDT = 250.0
INITIAL_TOKEN_VALUE_USD = 250.0  # $250 worth of each token


class LiveState:
    """Shared state for all exchange feeds."""

    def __init__(self):
        cfg = get_config()
        self.enabled_exchanges = list(cfg.exchanges.keys())
        self.tokens = cfg.get_tokens()

        # Generic: {exchange_name: {token: {bid, ask, bid_depth, ask_depth, updated}}}
        self.exchanges: Dict[str, Dict[str, Any]] = {ex: {} for ex in self.enabled_exchanges}
        self.ws_status: Dict[str, Dict[str, str]] = {ex: {} for ex in self.enabled_exchanges}
        self.update_count: Dict[str, int]         = {ex: 0  for ex in self.enabled_exchanges}

        self.usdt_usdc_rate = 1.0
        self.errors = []
        self.started_at = time.monotonic()

        # Per-exchange: which tokens are available on that exchange
        self.supported_tokens: Dict[str, Set[str]] = {ex: set(self.tokens) for ex in self.enabled_exchanges}

        # Opportunity tracking
        self.opp_count: Dict[str, int]      = {t: 0 for t in self.tokens}
        self.opp_total: int                 = 0
        self.opp_last: Dict[str, dict]      = {}   # token -> last opp dict
        self.opp_best: Dict[str, float]     = {}   # token -> best net spread ever

        # Spread tracking (session highs) — keyed by token
        self.spread_history: Dict[str, dict] = {t: {"max_net": -999.0} for t in self.tokens}
        
        # Trading Control
        self.auto_trade_enabled: bool = False
        self.is_pro_mode: bool = False
        
        # Initialize wallets: $250 USDT only.
        # Token balances are initialized lazily on first trade using current market price.
        self.balances: Dict[str, Dict[str, float]] = {}
        self._reset_balances_to_initial()
                
        self.active_trades: Dict[str, dict] = {}
        self._balances_restored: bool = False
        # Track which token balances have been initialized with market price
        self._token_initialized: Dict[str, Dict[str, bool]] = {
            ex: {} for ex in self.enabled_exchanges
        }

    def _reset_balances_to_initial(self) -> None:
        """Reset all wallets to initial $250 USDT state. Token balances start at 0."""
        for ex in self.enabled_exchanges:
            self.balances[ex] = {"USDT": INITIAL_USDT}
            # Tokens start at 0 — will be initialized lazily with market price
            for t in self.tokens:
                self.balances[ex][t] = 0.0
        self._token_initialized = {
            ex: {} for ex in self.enabled_exchanges
        }

    def ensure_token_balance(self, exchange: str, token: str, current_price: float) -> None:
        """
        Lazy-initialize a token balance to $250 worth at current market price.
        Called before the first trade of each token on each exchange.
        """
        if exchange not in self._token_initialized:
            self._token_initialized[exchange] = {}
        
        if not self._token_initialized[exchange].get(token, False):
            # Initialize to $250 worth of tokens at current price
            if current_price > 0:
                token_qty = INITIAL_TOKEN_VALUE_USD / current_price
                self.balances[exchange][token] = token_qty
                self._token_initialized[exchange][token] = True

    async def restore_balances_from_db(self) -> None:
        """
        Reconstruct wallet balances from DB trade history.
        Applies all filled mock order deltas on top of initial $250/$250 values.
        Called once during startup after DB pool is ready.
        """
        if self._balances_restored:
            return

        from app.db.order_repo import get_wallet_deltas, get_rebalance_deltas
        import structlog
        logger = structlog.get_logger("state")

        # Reset to clean initial state
        self._reset_balances_to_initial()

        # 1. Apply trade deltas (buy/sell orders)
        deltas = await get_wallet_deltas()
        for d in deltas:
            ex = d["exchange"]
            symbol = d["symbol"]  # e.g. "CLOUD/USDT"
            token = symbol.split("/")[0] if "/" in symbol else symbol
            
            if ex in self.balances:
                # USDT delta: negative on buy side, positive on sell side
                self.balances[ex]["USDT"] = self.balances[ex].get("USDT", INITIAL_USDT) + float(d["usdt_delta"])
                # Token delta: positive on buy side, negative on sell side
                # Note: tokens start at 0, so delta IS the balance from trading
                current = self.balances[ex].get(token, 0.0)
                self.balances[ex][token] = current + float(d["token_delta"])

        # 2. Apply rebalance transfer deltas
        reb_deltas = await get_rebalance_deltas()
        for rd in reb_deltas:
            source = rd["source_ex"]
            dest = rd["dest_ex"]
            asset = rd["asset"]
            amount = float(rd["total_amount"])
            
            if source in self.balances:
                self.balances[source][asset] = self.balances[source].get(asset, 0.0) - amount
            if dest in self.balances:
                self.balances[dest][asset] = self.balances[dest].get(asset, 0.0) + amount

        self._balances_restored = True

        # Log restored balances
        for ex in self.enabled_exchanges:
            usdt = self.balances[ex].get("USDT", 0)
            logger.info(f"[state] Restored {ex} wallet: USDT=${usdt:.2f}", exchange=ex, usdt=usdt)

    async def reset_mock_wallets(self) -> None:
        """
        Full reset: clear all mock trade data from DB and reset in-memory wallets.
        """
        from app.db.pool import get_pool
        import structlog
        logger = structlog.get_logger("state")

        pool = get_pool()
        if pool:
            await pool.execute("DELETE FROM orders WHERE is_mock = true")
            await pool.execute("DELETE FROM trade_groups WHERE is_mock = true")
            await pool.execute("DELETE FROM rebalance_transfers WHERE is_mock = true")
            logger.info("[state] Cleared all mock trade data from DB")

        self._reset_balances_to_initial()
        self._balances_restored = True  # Don't try to restore from now-empty DB
        self.active_trades.clear()
        logger.info("[state] Mock wallets reset to initial $250 USDT per exchange")


_state = None

def get_state() -> LiveState:
    global _state
    if _state is None:
        _state = LiveState()
    return _state
