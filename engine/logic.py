"""
engine/logic.py — Spread Evaluator & Risk Gate
All go/no-go decisions live here. Both mock and live mode pass through.
"""
import asyncio
from datetime import datetime, timezone
from typing import Optional
import structlog

from config import cfg

log = structlog.get_logger(__name__)


class Session:
    """Tracks intraday PnL, loss streaks, and pause state."""

    def __init__(self) -> None:
        self._pnl:          float            = 0.0
        self._consec:       int              = 0
        self._trade_count:  int              = 0
        self._date:         str              = self._today()
        self._paused_until: Optional[float]  = None  # monotonic timestamp

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _maybe_reset(self) -> None:
        if self._today() != self._date:
            log.info("daily_session_reset",
                     date=self._date,
                     total_pnl=round(self._pnl, 4),
                     trades=self._trade_count)
            self.__init__()

    def record(self, net_pnl: float) -> None:
        """Record trade result and check daily risk limits."""
        self._maybe_reset()
        self._pnl         += net_pnl
        self._trade_count += 1

        if net_pnl < 0:
            self._consec += 1
        else:
            self._consec = 0

        log.info("session_update",
                 net_pnl=round(net_pnl, 4),
                 session_pnl=round(self._pnl, 4),
                 trades=self._trade_count,
                 consec_losses=self._consec,
                 mock=cfg.MOCK_MODE)

        # Daily loss cap
        if self._pnl <= -cfg.DAILY_LOSS_CAP:
            raise DailyLossCapHit(
                f"Daily loss cap hit: -${abs(self._pnl):.2f} >= ${cfg.DAILY_LOSS_CAP}"
            )

        # Consecutive loss pause
        if self._consec >= cfg.CONSEC_LOSS_MAX:
            import time
            self._paused_until = time.monotonic() + (cfg.PAUSE_MINUTES * 60)
            log.warning("consecutive_loss_pause",
                        count=self._consec,
                        pause_minutes=cfg.PAUSE_MINUTES)
            raise ConsecutiveLossPause(
                f"{self._consec} consecutive losses — pausing {cfg.PAUSE_MINUTES} min"
            )

    def is_paused(self) -> bool:
        self._maybe_reset()
        if self._paused_until is None:
            return False
        import time
        if time.monotonic() >= self._paused_until:
            self._paused_until = None
            self._consec       = 0
            log.info("pause_lifted")
            return False
        return True

    def summary(self) -> dict:
        return {
            "date":        self._date,
            "pnl":         round(self._pnl, 4),
            "trades":      self._trade_count,
            "consec":      self._consec,
            "is_paused":   self.is_paused(),
            "mock":        cfg.MOCK_MODE,
        }


class DailyLossCapHit(Exception):
    pass

class ConsecutiveLossPause(Exception):
    pass


class Logic:
    """Evaluates whether a spread opportunity passes all filters."""

    def __init__(self, scanner) -> None:
        self._scanner = scanner
        self.session  = Session()

    def evaluate(self, spread: Optional[dict]) -> Optional[dict]:
        """
        Returns enriched signal dict if tradeable, else None.
        All checks identical in mock and live mode.
        """
        if spread is None:
            return None

        # Paused for cooling off?
        if self.session.is_paused():
            return None

        spread_pct = spread["spread_pct"]

        # Below trigger threshold?
        if spread_pct < cfg.TRIGGER_THRESHOLD:
            return None

        # Depth / liquidity check
        if not self._depth_ok(spread["direction"]):
            log.debug("depth_check_failed", spread=spread_pct)
            return None

        # Compute expected net profit
        friction    = cfg.FRICTION_BUDGET  # updated by fee_ledger if available
        gross       = cfg.TRADE_AMOUNT * spread_pct / 100
        net         = gross - (cfg.TRADE_AMOUNT * friction / 100) - 0.20  # rebal share
        if net <= 0:
            return None

        signal = {
            **spread,
            "threshold":   cfg.TRIGGER_THRESHOLD,
            "friction":    friction,
            "gross_profit": round(gross, 4),
            "expected_net": round(net,  4),
            "mock":         cfg.MOCK_MODE,
        }

        log.info("trade_signal_fired",
                 spread=spread_pct,
                 direction=spread["direction"],
                 expected_net=signal["expected_net"],
                 mock=cfg.MOCK_MODE)
        return signal

    def _depth_ok(self, direction: str) -> bool:
        books = self._scanner.books
        if direction == "BUY_BINANCE":
            asks = books["binance"].asks
            bids = books["mexc"].bids
        else:
            asks = books["mexc"].asks
            bids = books["binance"].bids
        return (self._usd_depth(asks) >= cfg.MIN_DEPTH_USD and
                self._usd_depth(bids) >= cfg.MIN_DEPTH_USD)

    @staticmethod
    def _usd_depth(levels: list) -> float:
        total = 0.0
        for price, qty in levels[:cfg.ORDER_BOOK_LEVELS]:
            total += float(price) * float(qty)
        return total
