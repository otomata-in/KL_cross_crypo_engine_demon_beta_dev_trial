"""
app/execution/mock_exchange.py — Simulated Exchange
=====================================================
Simulates order execution against real orderbook prices.
"""

import asyncio
import random
import time
import uuid
from typing import Dict, Any


class MockExchange:
    """
    Paper trading simulator.
    Applies configurable fill rate, slippage, and latency.
    """

    def __init__(self, name: str, fill_rate: float = 0.97, slippage_pct: float = 0.15, latency_ms: float = 45.0):
        self.name = name
        self.fill_rate = fill_rate
        self.slippage_pct = slippage_pct
        self.latency_ms = latency_ms

    async def simulate_buy(self, qty: float, limit_price: float) -> Dict[str, Any]:
        """Simulate an IOC limit buy."""
        await self._simulate_latency()

        rate = self._get_fill_rate()
        filled_qty = round(qty * rate, 6)
        exec_price = limit_price * (1 + self.slippage_pct / 100)
        cost = filled_qty * exec_price
        fee = cost * 0.001

        return {
            "id": str(uuid.uuid4())[:12],
            "side": "buy",
            "qty": qty,
            "filled": filled_qty,
            "price": exec_price,
            "fee": fee,
            "timestamp": time.time(),
        }

    async def simulate_sell(self, qty: float, limit_price: float) -> Dict[str, Any]:
        """Simulate an IOC limit sell."""
        await self._simulate_latency()

        rate = self._get_fill_rate()
        filled_qty = round(qty * rate, 6)
        exec_price = limit_price * (1 - self.slippage_pct / 100)
        proceeds = filled_qty * exec_price
        fee = proceeds * 0.001

        return {
            "id": str(uuid.uuid4())[:12],
            "side": "sell",
            "qty": qty,
            "filled": filled_qty,
            "price": exec_price,
            "fee": fee,
            "timestamp": time.time(),
        }

    def _get_fill_rate(self) -> float:
        r = random.random()
        if r < 0.03:          # 3% chance of full IOC miss
            return 0.0
        if r < 0.10:          # 7% chance of partial fill (85–99%)
            return random.uniform(0.85, 0.99)
        return self.fill_rate

    async def _simulate_latency(self) -> None:
        jitter = random.uniform(-10, 20)
        await asyncio.sleep(max(0, self.latency_ms + jitter) / 1000)
