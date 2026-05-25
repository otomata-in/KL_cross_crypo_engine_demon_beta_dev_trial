"""
app/engine/state.py — Global Live State
=========================================
Shared state for all exchange feeds and opportunity detector.
Extracted from ws_server.py to avoid circular dependencies.
"""

import time
from typing import Dict, Any, Set

from app.config import get_config


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
        
        self.balances: Dict[str, Dict[str, float]] = {}
        for ex in self.enabled_exchanges:
            self.balances[ex] = {"USDT": 250.0}
            for t in self.tokens:
                # We initialize with a nominal token amount. 
                # In split_wallet, it will be accurately pegged to $250 value.
                self.balances[ex][t] = 250.0 
                
        self.active_trades: Dict[str, dict] = {}


_state = None

def get_state() -> LiveState:
    global _state
    if _state is None:
        _state = LiveState()
    return _state
