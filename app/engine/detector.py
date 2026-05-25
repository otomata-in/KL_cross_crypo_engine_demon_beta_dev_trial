"""
app/engine/detector.py — Opportunity Detector
===============================================
Runs continuously, scanning live orderbooks for profitable spreads.
Decoupled from WebSocket transport and legacy ws_server.py.
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Optional, Callable

from app.config import get_config
from app.db import opportunity_repo
from app.engine.state import get_state
from app.engine.spread import precompute_pair_fees, compute_spreads, normalize_to_usdt
from app.models.opportunity import Opportunity


class OpportunityDetector:
    """
    Scans LiveState orderbooks across all exchange pairs.
    Detects, logs, and broadcasts arbitrage opportunities.
    """

    def __init__(self, broadcast_callback: Optional[Callable[[str], None]] = None):
        """
        Args:
            broadcast_callback: Function to call to broadcast new opportunities
                                via WebSocket to clients.
        """
        self.cfg = get_config()
        self.state = get_state()
        self.pair_fees = precompute_pair_fees()
        self.broadcast_callback = broadcast_callback
        self.running = False
        
        # Debounce: don't log the same token+pair twice within 1 second
        self.last_logged = {}  # (token, ex_a, ex_b) -> monotonic time

        # Threshold can be dynamically updated by transport layer
        self.current_threshold = self.cfg.DEFAULT_THRESHOLD

    def set_threshold(self, value: float) -> None:
        """Update the minimum net profit threshold."""
        self.current_threshold = max(-2.0, min(15.0, value))

    async def run(self) -> None:
        """Main detection loop. Runs at ~20 checks/sec."""
        self.running = True
        print("[detector] Starting opportunity detector...")
        await asyncio.sleep(5)  # Let feeds warm up

        from app.exchanges.registry import ExchangeRegistry
        registry = ExchangeRegistry()
        registry.load_from_config()
        exchange_pairs = registry.get_pairs()

        while self.running:
            usdt_usdc = self.state.usdt_usdc_rate

            for ex_a, ex_b in exchange_pairs:
                fees = self.pair_fees[(ex_a, ex_b)]

                for token in self.state.tokens:
                    ob_a = self.state.exchanges[ex_a].get(token, {})
                    ob_b = self.state.exchanges[ex_b].get(token, {})

                    a_bid = ob_a.get("bid")
                    a_ask = ob_a.get("ask")
                    b_bid = ob_b.get("bid")
                    b_ask = ob_b.get("ask")

                    if not all([a_bid, a_ask, b_bid, b_ask]):
                        continue

                    # Compute spreads
                    spread_a2b, spread_b2a = compute_spreads(
                        a_bid, a_ask, b_bid, b_ask, ex_a, ex_b, usdt_usdc
                    )

                    label_a = self.cfg.exchanges[ex_a].label
                    label_b = self.cfg.exchanges[ex_b].label

                    # Evaluate both directions
                    directions = [
                        (spread_a2b, f"Buy{label_a}→Sell{label_b}", ex_a, ex_b, a_ask, b_bid),
                        (spread_b2a, f"Buy{label_b}→Sell{label_a}", ex_b, ex_a, b_ask, a_bid),
                    ]

                    for spread, direction, buy_ex, sell_ex, buy_ask, sell_bid in directions:
                        if spread <= self.cfg.OPP_MIN_SPREAD:
                            continue

                        # Debounce check
                        now = time.monotonic()
                        debounce_key = (token, buy_ex, sell_ex)
                        if now - self.last_logged.get(debounce_key, 0) < 1.0:
                            continue

                        net_spread = spread - fees

                        # Threshold check
                        if net_spread < self.current_threshold:
                            continue

                        self.last_logged[debounce_key] = now
                        await self._record_opportunity(
                            token, buy_ex, sell_ex, direction,
                            spread, net_spread, fees, buy_ask, sell_bid, usdt_usdc
                        )

            await asyncio.sleep(0.05)  # 20 checks/second

    async def _record_opportunity(
        self, token: str, buy_ex: str, sell_ex: str, direction: str,
        spread: float, net_spread: float, fees: float,
        buy_ask: float, sell_bid: float, usdt_usdc: float
    ) -> None:
        """Update state counters, store in DB, and broadcast."""
        # Update counters
        self.state.opp_count[token] += 1
        self.state.opp_total += 1

        # Track best (net)
        prev_best = self.state.opp_best.get(token, -999)
        if net_spread > prev_best:
            self.state.opp_best[token] = net_spread

        # Update session high
        if net_spread > self.state.spread_history[token]["max_net"]:
            self.state.spread_history[token]["max_net"] = net_spread

        # Store last opportunity info
        self.state.opp_last[token] = {
            "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "spread": round(spread, 4),
            "net": round(net_spread, 4),
            "direction": direction,
            "pair": f"{buy_ex}→{sell_ex}",
        }

        # Build DB model
        opp = Opportunity(
            token=token,
            ex_buy=buy_ex,
            ex_sell=sell_ex,
            direction=direction,
            gross_spread_pct=round(spread, 4),
            net_spread_pct=round(net_spread, 4),
            pair_fees_pct=round(fees, 4),
            buy_ask=normalize_to_usdt(buy_ask, buy_ex, usdt_usdc),
            sell_bid=normalize_to_usdt(sell_bid, sell_ex, usdt_usdc),
            usdt_usdc_rate=usdt_usdc,
        )

        record_dict = opp.to_dict()

        # Log to DB
        try:
            await opportunity_repo.insert(record_dict)
        except Exception as e:
            print(f"[detector] DB write error: {e}")

        # Broadcast
        if self.broadcast_callback:
            try:
                payload = json.dumps({"type": "new_opportunity", "data": record_dict})
                self.broadcast_callback(payload)
            except Exception as e:
                print(f"[detector] Broadcast error: {e}")

    def stop(self) -> None:
        self.running = False
