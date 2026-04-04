"""
engine/scanner.py — Real-time Orderbook Mirror
WebSocket primary feed with sequence validation and REST fallback.
Works in both MOCK_MODE and live mode — always uses real price feeds.
"""
import asyncio
import time
from typing import Optional
import ccxt.async_support as ccxt
import structlog

from config import cfg

log = structlog.get_logger(__name__)


class OrderbookCache:
    """Thread-safe orderbook snapshot with staleness tracking."""

    def __init__(self, exchange_id: str) -> None:
        self.exchange_id = exchange_id
        self.bids:       list          = []
        self.asks:       list          = []
        self.last_tick:  float         = 0.0
        self.last_seq:   int           = 0
        self.seq_gaps:   int           = 0

    def update(self, bids: list, asks: list, seq: Optional[int] = None) -> bool:
        """
        Update snapshot. Returns False (skip) if sequence gap detected.
        Caller must resubscribe on False return.
        """
        if seq is not None and self.last_seq > 0:
            if seq != self.last_seq + 1:
                self.seq_gaps += 1
                log.warning("seq_gap_detected",
                            exchange=self.exchange_id,
                            expected=self.last_seq + 1,
                            received=seq,
                            total_gaps=self.seq_gaps)
                return False  # stale / corrupted — skip this message

        if seq is not None:
            self.last_seq = seq
        self.bids      = bids
        self.asks      = asks
        self.last_tick = time.monotonic()
        return True

    @property
    def is_stale(self) -> bool:
        if self.last_tick == 0:
            return True
        return (time.monotonic() - self.last_tick) > cfg.STALE_FEED_SECONDS

    @property
    def best_bid(self) -> Optional[float]:
        return float(self.bids[0][0]) if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        return float(self.asks[0][0]) if self.asks else None


class Scanner:
    """
    Maintains live orderbook mirrors for Binance and MEXC.
    Always uses real price data regardless of MOCK_MODE.
    """

    def __init__(self) -> None:
        self.binance = ccxt.binance({
            "apiKey":  cfg.API_KEY_BINANCE,
            "secret":  cfg.API_SECRET_BINANCE,
            "options": {"defaultType": "spot"},
        })
        self.mexc = ccxt.mexc({
            "apiKey": cfg.API_KEY_BACKPACK,
            "secret": cfg.API_SECRET_BACKPACK,
        })
        self.books: dict[str, OrderbookCache] = {
            "binance": OrderbookCache("binance"),
            "mexc":    OrderbookCache("mexc"),
        }
        self._wss_healthy = {"binance": False, "mexc": False}
        self._running     = False

    async def start(self) -> None:
        self._running = True
        await asyncio.gather(
            self._supervise("binance", self.binance),
            self._supervise("mexc",    self.mexc),
        )

    async def stop(self) -> None:
        self._running = False
        await self.binance.close()
        await self.mexc.close()

    def get_spread(self) -> Optional[dict]:
        """
        Returns best spread opportunity if feeds are live and spread is valid.
        Returns None if feeds are stale or spread fails sanity bounds.
        """
        bb = self.books["binance"]
        mb = self.books["mexc"]

        # Staleness check
        if bb.is_stale or mb.is_stale:
            log.warning("stale_feed",
                        binance_stale=bb.is_stale,
                        mexc_stale=mb.is_stale)
            return None

        if any(v is None for v in [bb.best_bid, bb.best_ask, mb.best_bid, mb.best_ask]):
            return None

        # Compute both directions
        spread_a = ((mb.best_bid - bb.best_ask) / bb.best_ask) * 100  # buy Binance sell MEXC
        spread_b = ((bb.best_bid - mb.best_ask) / mb.best_ask) * 100  # buy MEXC sell Binance

        best_spread = max(spread_a, spread_b)
        direction   = "BUY_BINANCE" if spread_a >= spread_b else "BUY_MEXC"

        # Sanity bound — reject corrupted ticks
        if best_spread > cfg.MAX_VALID_SPREAD:
            log.warning("bad_tick_rejected",
                        spread=round(best_spread, 4),
                        max_allowed=cfg.MAX_VALID_SPREAD)
            return None

        return {
            "spread_pct":  round(best_spread, 4),
            "direction":   direction,
            "binance_bid": bb.best_bid,
            "binance_ask": bb.best_ask,
            "mexc_bid":    mb.best_bid,
            "mexc_ask":    mb.best_ask,
            "timestamp":   time.time(),
        }

    # ── Internal ─────────────────────────────────────────────────

    async def _supervise(self, name: str, exchange) -> None:
        """Supervisor: runs WSS, detects drops, activates REST fallback."""
        while self._running:
            try:
                log.info("wss_connecting", exchange=name)
                await self._wss_feed(name, exchange)
            except Exception as exc:
                log.error("wss_dropped", exchange=name, error=str(exc))
                self._wss_healthy[name] = False
                from utils.notifier import notify
                await notify(f"WSS dropped [{name}] — REST fallback active")
                await self._rest_fallback(name, exchange)
            await asyncio.sleep(1)

    async def _wss_feed(self, name: str, exchange) -> None:
        """WebSocket feed. Validates sequence numbers. Raises on gap or drop."""
        self._wss_healthy[name] = True
        while self._running:
            ob  = await exchange.watch_order_book(cfg.SYMBOL, limit=cfg.ORDER_BOOK_LEVELS)
            seq = ob.get("nonce") or ob.get("sequence") or ob.get("lastUpdateId")
            ok  = self.books[name].update(
                bids=ob["bids"],
                asks=ob["asks"],
                seq=int(seq) if seq else None,
            )
            if not ok:
                raise RuntimeError(f"Sequence gap on {name} — resubscribing")

    async def _rest_fallback(self, name: str, exchange) -> None:
        """Poll REST at 500ms until stable enough to retry WSS."""
        log.info("rest_fallback_active", exchange=name)
        ok_count = 0
        while self._running and not self._wss_healthy[name]:
            try:
                ob = await exchange.fetch_order_book(cfg.SYMBOL, limit=cfg.ORDER_BOOK_LEVELS)
                self.books[name].update(bids=ob["bids"], asks=ob["asks"])
                ok_count += 1
                if ok_count >= 10:
                    log.info("rest_stable_retrying_wss", exchange=name)
                    return
            except Exception as exc:
                log.error("rest_error", exchange=name, error=str(exc))
                ok_count = 0
            await asyncio.sleep(cfg.REST_POLL_INTERVAL)
