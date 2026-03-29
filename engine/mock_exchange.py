"""
engine/mock_exchange.py — Simulated Exchange for Paper Trading
Uses real price feeds but simulates order execution with realistic
fill rates, slippage, and latency. No real API calls are made.
"""
import asyncio
import random
import time
import uuid
from typing import Optional
import structlog

from config import cfg

log = structlog.get_logger(__name__)


class MockExchange:
    """
    Simulates exchange order execution against real orderbook prices.
    Applies configurable fill rate, slippage, and latency so paper
    trading results reflect realistic conditions — not best-case.
    """

    def __init__(self, name: str, orderbook_cache) -> None:
        self.name           = name
        self._book          = orderbook_cache
        self._virtual_usdt  = cfg.STARTING_CAPITAL / 2   # split capital
        self._virtual_base  = 0.0                         # PIPPIN balance
        self._order_history: list[dict] = []

    # ── Balances ─────────────────────────────────────────────────

    @property
    def usdt_balance(self) -> float:
        return round(self._virtual_usdt, 4)

    @property
    def base_balance(self) -> float:
        return round(self._virtual_base, 6)

    def credit_usdt(self, amount: float) -> None:
        """Called by rebalancer to simulate inbound transfer."""
        self._virtual_usdt += amount
        log.info("mock_transfer_received",
                 exchange=self.name,
                 amount=amount,
                 new_balance=self.usdt_balance)

    def debit_base(self, amount: float) -> None:
        """Called by rebalancer to simulate outbound PIPPIN transfer."""
        self._virtual_base -= amount

    # ── Order simulation ─────────────────────────────────────────

    async def place_ioc_buy(self, qty: float, limit_price: float) -> dict:
        """
        Simulate an IOC market buy.
        Applies slippage to the price, partial fill to qty.
        """
        await self._simulate_latency()

        fill_rate    = self._get_fill_rate()
        filled_qty   = round(qty * fill_rate, 6)
        exec_price   = limit_price * (1 + cfg.MOCK_SLIPPAGE_PCT / 100)
        cost_usdt    = filled_qty * exec_price
        fee          = cost_usdt * 0.001   # 0.1% fee

        if filled_qty > 0:
            if cost_usdt + fee > self._virtual_usdt:
                # Insufficient virtual balance — fill what we can
                affordable   = self._virtual_usdt / (exec_price * 1.001)
                filled_qty   = round(affordable * 0.99, 6)
                cost_usdt    = filled_qty * exec_price
                fee          = cost_usdt * 0.001

            self._virtual_usdt -= (cost_usdt + fee)
            self._virtual_base += filled_qty

        result = self._build_order_result(
            side="buy",
            qty=qty,
            filled=filled_qty,
            price=exec_price,
            fee=fee,
        )
        self._order_history.append(result)

        log.info("mock_buy_executed",
                 exchange=self.name,
                 qty=qty,
                 filled=filled_qty,
                 price=round(exec_price, 6),
                 fee=round(fee, 4),
                 usdt_balance=self.usdt_balance)
        return result

    async def place_ioc_sell(self, qty: float, limit_price: float) -> dict:
        """
        Simulate an IOC market sell.
        Applies slippage to the price (sells at slightly below ask).
        """
        await self._simulate_latency()

        fill_rate   = self._get_fill_rate()
        filled_qty  = round(min(qty * fill_rate, self._virtual_base), 6)
        exec_price  = limit_price * (1 - cfg.MOCK_SLIPPAGE_PCT / 100)
        proceeds    = filled_qty * exec_price
        fee         = proceeds * 0.001

        if filled_qty > 0:
            self._virtual_base -= filled_qty
            self._virtual_usdt += (proceeds - fee)

        result = self._build_order_result(
            side="sell",
            qty=qty,
            filled=filled_qty,
            price=exec_price,
            fee=fee,
        )
        self._order_history.append(result)

        log.info("mock_sell_executed",
                 exchange=self.name,
                 qty=qty,
                 filled=filled_qty,
                 price=round(exec_price, 6),
                 fee=round(fee, 4),
                 usdt_balance=self.usdt_balance)
        return result

    async def place_market_buy(self, qty: float) -> dict:
        """Emergency hedge — market buy at current ask."""
        ask = self._book.best_ask or 0.0
        return await self.place_ioc_buy(qty, ask)

    async def place_market_sell(self, qty: float) -> dict:
        """Emergency hedge — market sell at current bid."""
        bid = self._book.best_bid or 0.0
        return await self.place_ioc_sell(qty, bid)

    # ── Stats ─────────────────────────────────────────────────────

    def total_virtual_value(self, mid_price: float) -> float:
        """Total portfolio value in USDT at current mid price."""
        return self._virtual_usdt + (self._virtual_base * mid_price)

    def order_count(self) -> int:
        return len(self._order_history)

    # ── Internal helpers ──────────────────────────────────────────

    @staticmethod
    def _get_fill_rate() -> float:
        """
        Randomise fill rate around MOCK_FILL_RATE.
        Occasionally simulate a partial fill or full IOC miss.
        """
        r = random.random()
        if r < 0.03:          # 3% chance of full IOC miss
            return 0.0
        if r < 0.10:          # 7% chance of partial fill (85–99%)
            return random.uniform(0.85, 0.99)
        return cfg.MOCK_FILL_RATE

    @staticmethod
    async def _simulate_latency() -> None:
        """Simulate network round-trip latency with jitter."""
        jitter = random.uniform(-10, 20)  # ±10–20ms jitter
        await asyncio.sleep(max(0, cfg.MOCK_LATENCY_MS + jitter) / 1000)

    @staticmethod
    def _build_order_result(
        side: str,
        qty: float,
        filled: float,
        price: float,
        fee: float,
    ) -> dict:
        return {
            "id":        str(uuid.uuid4())[:12],
            "side":      side,
            "qty":       qty,
            "filled":    filled,
            "price":     round(price, 8),
            "fee":       round(fee, 6),
            "timestamp": time.time(),
            "mock":      True,
        }
