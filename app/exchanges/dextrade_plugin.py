"""
app/exchanges/dextrade_plugin.py — Dex-Trade Exchange Plugin
==============================================================
Wraps the DexTradeAdapter into the standard ExchangePlugin interface.
Uses REST polling since Dex-Trade does not support WebSocket.
"""

from typing import Optional, Dict, Any

from app.config import ExchangeConfig
from app.exchanges.base import ExchangePlugin


class DexTradePlugin(ExchangePlugin):
    """Dex-Trade exchange via REST polling."""

    def __init__(self, config: ExchangeConfig):
        super().__init__(config)
        # Import dynamically to avoid circular dependencies if needed
        from app.exchanges.dextrade_adapter import DexTradeAdapter
        self._adapter: Optional[DexTradeAdapter] = None

    async def connect(self) -> None:
        from app.exchanges.dextrade_adapter import DexTradeAdapter
        self._adapter = DexTradeAdapter(
            api_key=self.config.api_key,
            api_secret=self.config.api_secret,
        )

    async def close(self) -> None:
        if self._adapter:
            await self._adapter.close()

    async def load_markets(self) -> set:
        if not self._adapter:
            await self.connect()
        return await self._adapter.load_markets()

    def has_pair(self, token: str) -> bool:
        symbol = self.build_symbol(token)
        return self._adapter is not None and self._adapter.has_pair(symbol)

    def build_symbol(self, token: str) -> str:
        # Dex-Trade format: "SOLUSDT" (no slash)
        return f"{token}{self.config.quote}"

    async def watch_orderbook(self, token: str, symbol: str) -> Optional[dict]:
        """Poll REST API. Rate limits are handled externally in the transport layer."""
        if not self._adapter:
            return None
        return await self._adapter.fetch_orderbook(symbol)

    async def place_buy(self, symbol: str, qty: float, price: float, **params) -> Dict[str, Any]:
        raise NotImplementedError("Dex-Trade trading not yet implemented in REST adapter")

    async def place_sell(self, symbol: str, qty: float, price: float, **params) -> Dict[str, Any]:
        raise NotImplementedError("Dex-Trade trading not yet implemented in REST adapter")

    async def get_balance(self, asset: str) -> float:
        raise NotImplementedError("Dex-Trade balance check not yet implemented in REST adapter")
