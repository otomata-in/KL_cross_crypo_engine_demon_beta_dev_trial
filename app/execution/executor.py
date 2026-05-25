"""
app/execution/executor.py — Multi-Exchange Executor
=====================================================
Receives a trade signal and executes buy/sell orders simultaneously.
Scaffolded version: logs the intent but doesn't trade real funds yet.
"""

import asyncio
import time
import uuid
from typing import Optional

from app.config import get_config
from app.exchanges.registry import ExchangeRegistry
from app.execution.order_tracker import OrderTracker
from app.execution.mock_exchange import MockExchange


class MultiExchangeExecutor:
    """
    Executes cross-exchange arbitrage trades.
    """

    def __init__(self, registry: ExchangeRegistry):
        self.registry = registry
        self.cfg = get_config()
        self.mock = MockExchange(
            "sim",
            fill_rate=self.cfg.MOCK_FILL_RATE,
            slippage_pct=self.cfg.MOCK_SLIPPAGE_PCT,
            latency_ms=self.cfg.MOCK_LATENCY_MS
        )

    async def execute_trade(
        self, token: str, buy_ex_name: str, sell_ex_name: str,
        buy_price: float, sell_price: float
    ) -> None:
        """
        Execute an arbitrage trade between two exchanges.
        """
        trade_id = str(uuid.uuid4())[:12]
        
        # Calculate quantity based on configured trade amount and buy price
        qty = round(self.cfg.TRADE_AMOUNT / buy_price, 6)

        buy_plugin = self.registry.get(buy_ex_name)
        sell_plugin = self.registry.get(sell_ex_name)
        
        buy_symbol = buy_plugin.build_symbol(token)
        sell_symbol = sell_plugin.build_symbol(token)

        print(f"[executor] Executing {trade_id}: BUY {qty} {token} on {buy_ex_name} @ {buy_price}, "
              f"SELL {qty} {token} on {sell_ex_name} @ {sell_price}")

        # Create order records
        orders = await OrderTracker.create_trade_legs(
            trade_id=trade_id,
            buy_exchange=buy_ex_name, buy_symbol=buy_symbol, qty=qty, buy_price=buy_price,
            sell_exchange=sell_ex_name, sell_symbol=sell_symbol, sell_price=sell_price,
            is_mock=self.cfg.MOCK_MODE
        )
        buy_order, sell_order = orders[0], orders[1]

        # Execute simultaneously
        results = await asyncio.gather(
            self._place_order(buy_plugin, "buy", buy_symbol, qty, buy_price),
            self._place_order(sell_plugin, "sell", sell_symbol, qty, sell_price),
            return_exceptions=True
        )

        # Handle buy result
        if isinstance(results[0], Exception):
            await OrderTracker.update_failed(buy_order, str(results[0]))
        else:
            await OrderTracker.update_fill(
                buy_order,
                results[0].get("filled", 0),
                results[0].get("price", buy_price),
                results[0].get("fee", 0)
            )

        # Handle sell result
        if isinstance(results[1], Exception):
            await OrderTracker.update_failed(sell_order, str(results[1]))
        else:
            await OrderTracker.update_fill(
                sell_order,
                results[1].get("filled", 0),
                results[1].get("price", sell_price),
                results[1].get("fee", 0)
            )

        # Compute PnL if both succeeded
        if buy_order.filled_qty > 0 and sell_order.filled_qty > 0:
            net_pnl = await OrderTracker.compute_trade_pnl(buy_order, sell_order)
            print(f"[executor] Trade {trade_id} completed. Net PnL: {net_pnl:.4f}")

    async def _place_order(
        self, plugin, side: str, symbol: str, qty: float, price: float
    ) -> dict:
        """Place order via plugin, or mock it if in MOCK_MODE."""
        if self.cfg.MOCK_MODE:
            if side == "buy":
                return await self.mock.simulate_buy(qty, price)
            else:
                return await self.mock.simulate_sell(qty, price)
        else:
            # LIVE MODE
            # Currently scaffolded — avoid trading real funds during restructure
            print(f"!!! LIVE TRADE PREVENTED !!! Would have placed {side} on {plugin.name}")
            raise NotImplementedError("Live execution is scaffolded and disabled for safety.")
