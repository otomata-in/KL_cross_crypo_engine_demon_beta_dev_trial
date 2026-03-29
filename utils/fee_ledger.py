"""
utils/fee_ledger.py — Dynamic Fee Tracker
Refreshes trading fees from both exchanges every FEE_REFRESH_SECS.
Prevents trading with stale hardcoded fee assumptions.
"""
import asyncio
import time
import structlog
import ccxt.async_support as ccxt

from config import cfg

log = structlog.get_logger(__name__)


class FeeLedger:

    def __init__(self) -> None:
        # Defaults — overwritten on first refresh
        self.binance_taker: float = 0.001   # 0.1%
        self.mexc_taker:    float = 0.001
        self._last_refresh: float = 0.0
        self._refreshing:   bool  = False

    @property
    def total_friction(self) -> float:
        """Combined fee + slippage as a percentage."""
        return (self.binance_taker + self.mexc_taker) * 100 + cfg.SLIPPAGE_BUDGET

    @property
    def min_trigger(self) -> float:
        """Minimum viable trigger: 4× total friction (safety buffer)."""
        return self.total_friction * 4.5

    async def refresh_loop(self) -> None:
        """Run as a background task — refreshes fees periodically."""
        while True:
            await self._refresh()
            await asyncio.sleep(cfg.FEE_REFRESH_SECS)

    async def _refresh(self) -> None:
        if self._refreshing:
            return
        self._refreshing = True
        try:
            binance = ccxt.binance({
                "apiKey": cfg.API_KEY_BINANCE,
                "secret": cfg.API_SECRET_BINANCE,
            })
            mexc = ccxt.mexc({
                "apiKey": cfg.API_KEY_MEXC,
                "secret": cfg.API_SECRET_MEXC,
            })
            try:
                b_fees = await binance.fetch_trading_fee(cfg.SYMBOL)
                m_fees = await mexc.fetch_trading_fee(cfg.SYMBOL)

                old_b = self.binance_taker
                old_m = self.mexc_taker

                self.binance_taker = float(b_fees.get("taker", 0.001))
                self.mexc_taker    = float(m_fees.get("taker", 0.001))
                self._last_refresh = time.monotonic()

                if abs(self.binance_taker - old_b) > 0.0002:
                    log.warning("binance_fee_changed",
                                old=old_b, new=self.binance_taker)
                if abs(self.mexc_taker - old_m) > 0.0002:
                    log.warning("mexc_fee_changed",
                                old=old_m, new=self.mexc_taker)

                log.info("fees_refreshed",
                         binance=self.binance_taker,
                         mexc=self.mexc_taker,
                         total_friction=round(self.total_friction, 4))
            finally:
                await binance.close()
                await mexc.close()

        except Exception as exc:
            log.warning("fee_refresh_failed", error=str(exc))
        finally:
            self._refreshing = False


fee_ledger = FeeLedger()
