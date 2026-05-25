"""
app/exchanges/base.py — Abstract Exchange Plugin Interface
============================================================
Every exchange must implement this interface.
Adding a new exchange = create a new plugin file, no engine changes needed.
"""

from abc import ABC, abstractmethod
from typing import Optional, AsyncIterator, Dict, Any

from app.config import ExchangeConfig


class ExchangePlugin(ABC):
    """
    Abstract interface for exchange integrations.

    Subclasses handle the specifics of each exchange:
    - ccxt.pro WebSocket feeds (Binance, Backpack, Bybit)
    - REST polling (Dex-Trade)
    - Custom APIs (future exchanges)
    """

    def __init__(self, config: ExchangeConfig):
        self.config = config

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def label(self) -> str:
        return self.config.label

    @property
    def quote(self) -> str:
        return self.config.quote

    @property
    def fee_taker(self) -> float:
        return self.config.fee_taker

    @property
    def gas(self) -> float:
        return self.config.gas

    # ── Lifecycle ─────────────────────────────────────────────

    @abstractmethod
    async def connect(self) -> None:
        """Initialize the exchange connection (load markets, etc)."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close connections gracefully."""
        ...

    # ── Market data ───────────────────────────────────────────

    @abstractmethod
    async def load_markets(self) -> set:
        """
        Load available trading pairs.
        Returns set of token symbols available on this exchange.
        """
        ...

    @abstractmethod
    def has_pair(self, token: str) -> bool:
        """Check if a token/pair is available on this exchange."""
        ...

    @abstractmethod
    def build_symbol(self, token: str) -> str:
        """Build the exchange-specific symbol string for a token."""
        ...

    @abstractmethod
    async def watch_orderbook(self, token: str, symbol: str) -> Optional[dict]:
        """
        Fetch or stream a single orderbook update.
        Returns standardized dict: {bid, ask, bid_depth, ask_depth, updated}
        or None on error.

        For WebSocket exchanges: wraps watch_order_book()
        For REST exchanges: wraps fetch_orderbook()
        """
        ...

    # ── Trading (for execution module) ────────────────────────

    async def place_buy(
        self, symbol: str, qty: float, price: float, **params
    ) -> Dict[str, Any]:
        """Place a limit buy order. Override in subclass when execution is needed."""
        raise NotImplementedError(f"{self.name}: Trading not implemented")

    async def place_sell(
        self, symbol: str, qty: float, price: float, **params
    ) -> Dict[str, Any]:
        """Place a limit sell order. Override in subclass when execution is needed."""
        raise NotImplementedError(f"{self.name}: Trading not implemented")

    async def get_balance(self, asset: str) -> float:
        """Get available balance for an asset. Override when needed."""
        raise NotImplementedError(f"{self.name}: Balance check not implemented")

    # ── Helpers ───────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name} label={self.label}>"
