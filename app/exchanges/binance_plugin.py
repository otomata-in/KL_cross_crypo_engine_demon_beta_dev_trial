"""
app/exchanges/binance_plugin.py — Binance Exchange Plugin
==========================================================
ccxt.pro WebSocket feed for Binance spot orderbooks.
"""

import time
from typing import Optional

import ccxt.pro as ccxt

from app.config import ExchangeConfig
from app.exchanges.base import ExchangePlugin


class BinancePlugin(ExchangePlugin):
    """Binance exchange via ccxt.pro WebSocket."""

    def __init__(self, config: ExchangeConfig):
        super().__init__(config)
        self._exchange: Optional[ccxt.binance] = None
        self._available_tokens: set = set()

    async def connect(self) -> None:
        ccxt_config = {"options": self.config.options.copy()}
        if self.config.api_key:
            ccxt_config["apiKey"] = self.config.api_key
        if self.config.api_secret:
            ccxt_config["secret"] = self.config.api_secret
        self._exchange = ccxt.binance(ccxt_config)

    async def close(self) -> None:
        if self._exchange:
            try:
                await self._exchange.close()
            except Exception:
                pass

    async def load_markets(self) -> set:
        if not self._exchange:
            await self.connect()
        await self._exchange.load_markets()
        return set(self._exchange.markets.keys())

    def has_pair(self, token: str) -> bool:
        symbol = self.build_symbol(token)
        return self._exchange and symbol in self._exchange.markets

    def build_symbol(self, token: str) -> str:
        return f"{token}/{self.config.quote}"

    async def watch_orderbook(self, token: str, symbol: str) -> Optional[dict]:
        if not self._exchange:
            return None
        ob_limit = self.config.ob_limit or 10
        ob = await self._exchange.watch_order_book(symbol, limit=ob_limit)
        return self._parse_orderbook(ob)

    async def place_buy(self, symbol: str, qty: float, price: float, **params) -> dict:
        if not self._exchange:
            raise RuntimeError("Binance not connected")
        return await self._exchange.create_order(
            symbol, "limit", "buy", qty, price,
            params={"timeInForce": "IOC", **params}
        )

    async def place_sell(self, symbol: str, qty: float, price: float, **params) -> dict:
        if not self._exchange:
            raise RuntimeError("Binance not connected")
        return await self._exchange.create_order(
            symbol, "limit", "sell", qty, price,
            params={"timeInForce": "IOC", **params}
        )

    async def get_balance(self, asset: str) -> float:
        if not self._exchange:
            return 0.0
        bal = await self._exchange.fetch_balance()
        return float(bal.get(asset, {}).get("free", 0))

    @property
    def exchange_obj(self):
        """Expose underlying ccxt exchange for advanced use (e.g. USDT/USDC ticker)."""
        return self._exchange

    @staticmethod
    def _parse_orderbook(ob: dict) -> dict:
        bids = ob.get("bids", [])
        asks = ob.get("asks", [])
        return {
            "bid": float(bids[0][0]) if bids else None,
            "ask": float(asks[0][0]) if asks else None,
            "bid_depth": sum(float(b[0]) * float(b[1]) for b in bids[:5]) if bids else 0,
            "ask_depth": sum(float(a[0]) * float(a[1]) for a in asks[:5]) if asks else 0,
            "updated": time.monotonic(),
        }
