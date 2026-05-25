"""
app/exchanges/registry.py — Exchange Plugin Registry
======================================================
Loads enabled exchange plugins based on configuration.
"""

from typing import Dict, List, Tuple

from app.config import get_config
from app.exchanges.base import ExchangePlugin
from app.exchanges.binance_plugin import BinancePlugin
from app.exchanges.backpack_plugin import BackpackPlugin
from app.exchanges.bybit_plugin import BybitPlugin
from app.exchanges.dextrade_plugin import DexTradePlugin


class ExchangeRegistry:
    """Registry of active exchange plugins."""

    def __init__(self):
        self.plugins: Dict[str, ExchangePlugin] = {}

    def load_from_config(self) -> None:
        """Instantiate enabled plugins based on app config."""
        cfg = get_config()
        self.plugins.clear()

        # Plugin mapping
        plugin_classes = {
            "binance": BinancePlugin,
            "backpack": BackpackPlugin,
            "bybit": BybitPlugin,
            "dextrade": DexTradePlugin,
        }

        for name, ex_cfg in cfg.exchanges.items():
            if not ex_cfg.enabled:
                continue

            if name in plugin_classes:
                self.plugins[name] = plugin_classes[name](ex_cfg)
            else:
                print(f"[registry] Warning: No plugin class found for '{name}'")

    def get(self, name: str) -> ExchangePlugin:
        """Get an exchange plugin by name."""
        if name not in self.plugins:
            raise KeyError(f"Exchange '{name}' not found or disabled")
        return self.plugins[name]

    def list_enabled(self) -> List[str]:
        """List names of enabled exchanges."""
        return list(self.plugins.keys())

    def get_pairs(self) -> List[Tuple[str, str]]:
        """Get all possible combinations of enabled exchanges (for arbitrage)."""
        from itertools import combinations
        return list(combinations(self.list_enabled(), 2))

    async def initialize_all(self) -> None:
        """Connect all plugins and load their markets."""
        import asyncio
        tasks = [plugin.connect() for plugin in self.plugins.values()]
        await asyncio.gather(*tasks, return_exceptions=True)

        tasks = [plugin.load_markets() for plugin in self.plugins.values()]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def close_all(self) -> None:
        """Gracefully close all plugin connections."""
        import asyncio
        tasks = [plugin.close() for plugin in self.plugins.values()]
        await asyncio.gather(*tasks, return_exceptions=True)
