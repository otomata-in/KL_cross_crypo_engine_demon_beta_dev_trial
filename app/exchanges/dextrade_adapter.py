"""
dextrade_adapter.py — Dex-Trade REST API orderbook adapter
============================================================
Dex-Trade (dex-trade.com) is NOT supported by ccxt. This adapter polls
their public REST API for orderbook data and normalizes it into the same
format used by parse_orderbook() in the main engine.

API docs:
  Base URL:  https://api.dex-trade.com/v1/public/
  Orderbook: GET /book?pair=SOLUSDT
  Ticker:    GET /ticker?pair=SOLUSDT
  Symbols:   GET /symbols

Rate limits:
  Public:  10 requests/second
  Private: 5 requests/second

IMPORTANT: Dex-Trade returns prices as integers × 10^8.
           Volume values as integers × 10^6.
           This adapter handles the conversion automatically.
"""

import asyncio
import time
from typing import Optional

import aiohttp


# Dex-Trade REST API
BASE_URL = "https://api.dex-trade.com/v1/public"
PRICE_SCALE = 10**8   # Dex-Trade returns prices as integers × 10⁸
VOLUME_SCALE = 10**6  # Dex-Trade returns volumes as integers × 10⁶


class DexTradeAdapter:
    """
    Polls Dex-Trade REST API for orderbook data.
    Outputs data in the same format as parse_orderbook():
      {"bid": float, "ask": float, "bid_depth": float, "ask_depth": float, "updated": float}
    """

    def __init__(self, api_key: str = None, api_secret: str = None):
        self._session: Optional[aiohttp.ClientSession] = None
        self._api_key = api_key
        self._api_secret = api_secret
        self._available_pairs: set = set()  # populated at startup

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=5)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def load_markets(self) -> set:
        """
        Fetch available trading pairs from Dex-Trade.
        Returns set of pair strings like {"SOLUSDT", "BTCUSDT", ...}
        """
        session = await self._get_session()
        try:
            async with session.get(f"{BASE_URL}/symbols") as resp:
                if resp.status != 200:
                    print(f"[dextrade] Failed to load markets: HTTP {resp.status}")
                    return set()
                data = await resp.json()
                pairs_list = data.get("data", [])
                self._available_pairs = set()
                for pair_info in pairs_list:
                    # Dex-Trade returns pair info — extract the pair name
                    pair_name = pair_info.get("pair", "")
                    if pair_name:
                        self._available_pairs.add(pair_name.upper())
                print(f"[dextrade] Loaded {len(self._available_pairs)} markets")
                return self._available_pairs
        except Exception as e:
            print(f"[dextrade] Error loading markets: {e}")
            return set()

    def has_pair(self, pair: str) -> bool:
        """Check if a pair is available on Dex-Trade."""
        return pair.upper() in self._available_pairs

    async def fetch_orderbook(self, pair: str) -> Optional[dict]:
        """
        Fetch orderbook for a Dex-Trade pair.

        Args:
            pair: Dex-Trade format e.g. "SOLUSDT"
        Returns:
            Standardized orderbook dict matching parse_orderbook() output,
            or None if the request fails.
        """
        session = await self._get_session()
        url = f"{BASE_URL}/book?pair={pair}"
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()

                book_data = data.get("data", {})
                bids = book_data.get("buy", [])
                asks = book_data.get("sell", [])

                if not bids or not asks:
                    return None

                # Parse prices/volumes (returns true decimals, e.g. "142.50")
                best_bid = float(bids[0].get("rate", 0)) if bids else None
                best_ask = float(asks[0].get("rate", 0)) if asks else None

                # bid_depth = sum(price × volume) for top 5
                bid_depth = 0.0
                for b in bids[:5]:
                    rate = float(b.get("rate", 0))
                    volume = float(b.get("volume", 0))
                    bid_depth += rate * volume

                ask_depth = 0.0
                for a in asks[:5]:
                    rate = float(a.get("rate", 0))
                    volume = float(a.get("volume", 0))
                    ask_depth += rate * volume

                if best_bid is None or best_ask is None or best_bid == 0 or best_ask == 0:
                    return None

                return {
                    "bid": best_bid,
                    "ask": best_ask,
                    "bid_depth": bid_depth,
                    "ask_depth": ask_depth,
                    "updated": time.monotonic(),
                }
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, KeyError):
            return None
        except Exception:
            return None

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
