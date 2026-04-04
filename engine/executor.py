"""
engine/executor.py — Order Dispatcher (Mock + Live)
Routes to MockExchange or real exchange based on cfg.MOCK_MODE.
Handles: partial fills, IOC misses, delta hedging, PnL calculation.
Every trade — real or mock — goes through identical logic and logging.
"""
import asyncio
import uuid
import time
from typing import Optional
import structlog

from config import cfg
from engine.state import sm, TradeState
from engine.mock_exchange import MockExchange

log = structlog.get_logger(__name__)


class Executor:

    def __init__(self, scanner) -> None:
        self._scanner = scanner

        if cfg.MOCK_MODE:
            # Paper trading: simulated fills against real prices
            self._buy_ex  = MockExchange("binance", scanner.books["binance"])
            self._sell_ex = MockExchange("mexc",    scanner.books["mexc"])
            self._buy_ex_alt  = MockExchange("mexc",    scanner.books["mexc"])
            self._sell_ex_alt = MockExchange("binance", scanner.books["binance"])
            log.info("executor_mode", mode="MOCK — paper trading active")
        else:
            # Live trading: real ccxt exchanges
            import ccxt.async_support as ccxt
            self._binance = ccxt.binance({
                "apiKey":  cfg.API_KEY_BINANCE,
                "secret":  cfg.API_SECRET_BINANCE,
                "options": {"defaultType": "spot"},
            })
            self._mexc = ccxt.mexc({
                "apiKey": cfg.API_KEY_BACKPACK,
                "secret": cfg.API_SECRET_BACKPACK,
            })
            log.info("executor_mode", mode="LIVE — real money")

    # ── Main entry ───────────────────────────────────────────────

    async def execute(self, signal: dict) -> Optional[dict]:
        """
        Execute one arbitrage cycle.
        Identical flow for mock and live — only the order placement differs.
        """
        if not sm.can_trade():
            return None

        trade_id  = str(uuid.uuid4())[:12]
        direction = signal["direction"]

        # Assign buy/sell legs based on signal direction
        if direction == "BUY_BINANCE":
            buy_name,  sell_name  = "binance", "mexc"
            buy_price, sell_price = signal["binance_ask"], signal["mexc_bid"]
        else:
            buy_name,  sell_name  = "mexc", "binance"
            buy_price, sell_price = signal["mexc_ask"], signal["binance_bid"]

        qty = round(cfg.TRADE_AMOUNT / buy_price, 6)

        await sm.transition(TradeState.LEG1_OPEN, trade_id=trade_id)
        t_start = time.monotonic()

        # ── Fire both legs simultaneously ────────────────────────
        results = await asyncio.gather(
            self._place_buy(buy_name,   qty, buy_price,  trade_id),
            self._place_sell(sell_name, qty, sell_price, trade_id),
            return_exceptions=True,
        )

        latency_ms = round((time.monotonic() - t_start) * 1000, 1)
        await sm.transition(TradeState.LEG2_OPEN)

        buy_result  = results[0]
        sell_result = results[1]

        # ── Handle hard exceptions on either leg ─────────────────
        if isinstance(buy_result, Exception):
            log.error("buy_leg_failed", error=str(buy_result), trade_id=trade_id)
            if not isinstance(sell_result, Exception):
                sell_filled = float(sell_result.get("filled", 0))
                if sell_filled > 0:
                    await sm.transition(TradeState.HEDGING)
                    await self._hedge_buy(sell_name, sell_filled, signal)
            await sm.transition(TradeState.FLAT)
            await sm.transition(TradeState.IDLE)
            return None

        if isinstance(sell_result, Exception):
            log.error("sell_leg_failed", error=str(sell_result), trade_id=trade_id)
            buy_filled = float(buy_result.get("filled", 0))
            if buy_filled > 0:
                await sm.transition(TradeState.HEDGING)
                await self._hedge_sell(buy_name, buy_filled, signal)
            await sm.transition(TradeState.FLAT)
            await sm.transition(TradeState.IDLE)
            return None

        buy_filled  = float(buy_result.get("filled",  0))
        sell_filled = float(sell_result.get("filled", 0))

        # ── Reconcile fills and compute PnL ──────────────────────
        trade_record = await self._reconcile(
            trade_id=trade_id,
            direction=direction,
            buy_name=buy_name,
            sell_name=sell_name,
            buy_filled=buy_filled,
            sell_filled=sell_filled,
            buy_price=buy_price,
            sell_price=sell_price,
            buy_fee=float(buy_result.get("fee", 0)),
            sell_fee=float(sell_result.get("fee", 0)),
            spread_pct=signal["spread_pct"],
            latency_ms=latency_ms,
        )

        await sm.transition(TradeState.FLAT)
        await sm.transition(TradeState.IDLE)

        return trade_record

    # ── Order placement (routes mock vs live) ────────────────────

    async def _place_buy(self, exchange_name: str, qty: float,
                         price: float, trade_id: str) -> dict:
        log.info("placing_buy",
                 exchange=exchange_name,
                 qty=qty,
                 price=price,
                 trade_id=trade_id,
                 mock=cfg.MOCK_MODE)

        if cfg.MOCK_MODE:
            ex = (self._buy_ex if exchange_name == "binance"
                  else self._buy_ex_alt)
            return await ex.place_ioc_buy(qty, price)
        else:
            ex = (self._binance if exchange_name == "binance"
                  else self._mexc)
            return await ex.create_order(
                cfg.SYMBOL, "limit", "buy", qty, price,
                params={"timeInForce": "IOC"}
            )

    async def _place_sell(self, exchange_name: str, qty: float,
                          price: float, trade_id: str) -> dict:
        log.info("placing_sell",
                 exchange=exchange_name,
                 qty=qty,
                 price=price,
                 trade_id=trade_id,
                 mock=cfg.MOCK_MODE)

        if cfg.MOCK_MODE:
            ex = (self._sell_ex if exchange_name == "mexc"
                  else self._sell_ex_alt)
            return await ex.place_ioc_sell(qty, price)
        else:
            ex = (self._mexc if exchange_name == "mexc"
                  else self._binance)
            return await ex.create_order(
                cfg.SYMBOL, "limit", "sell", qty, price,
                params={"timeInForce": "IOC"}
            )

    async def _hedge_buy(self, exchange_name: str, qty: float, signal: dict) -> None:
        """Buy back qty to neutralise an orphaned sell position."""
        log.warning("emergency_hedge_buy",
                    exchange=exchange_name, qty=qty, mock=cfg.MOCK_MODE)
        if cfg.MOCK_MODE:
            price = signal.get(f"{exchange_name}_ask", signal["binance_ask"])
            ex = (self._sell_ex if exchange_name == "mexc" else self._sell_ex_alt)
            await ex.place_market_buy(qty)
        else:
            ex = self._mexc if exchange_name == "mexc" else self._binance
            await ex.create_market_buy_order(cfg.SYMBOL, qty)

    async def _hedge_sell(self, exchange_name: str, qty: float, signal: dict) -> None:
        """Sell qty to neutralise an orphaned buy position."""
        log.warning("emergency_hedge_sell",
                    exchange=exchange_name, qty=qty, mock=cfg.MOCK_MODE)
        if cfg.MOCK_MODE:
            ex = (self._buy_ex if exchange_name == "binance" else self._buy_ex_alt)
            await ex.place_market_sell(qty)
        else:
            ex = self._binance if exchange_name == "binance" else self._mexc
            await ex.create_market_sell_order(cfg.SYMBOL, qty)

    # ── Reconciliation & PnL ─────────────────────────────────────

    async def _reconcile(
        self, trade_id, direction,
        buy_name, sell_name,
        buy_filled, sell_filled,
        buy_price, sell_price,
        buy_fee, sell_fee,
        spread_pct, latency_ms,
    ) -> dict:
        """
        Handles all fill scenarios. Hedges delta if mismatched.
        Computes net PnL. Returns trade record for logging.
        """
        delta        = buy_filled - sell_filled
        delta_usd    = abs(delta) * buy_price

        # ── Full IOC miss on buy ──────────────────────────────────
        if buy_filled == 0 and sell_filled > 0:
            log.warning("ioc_miss_buy", trade_id=trade_id, sell_filled=sell_filled)
            await sm.transition(TradeState.HEDGING)
            await self._hedge_buy(sell_name, sell_filled, {
                f"{sell_name}_ask": sell_price,
                "binance_ask": sell_price,
            })
            net_pnl = -(sell_filled * sell_price * 0.001 * 2)  # fees lost
            ioc_miss = True

        # ── Full IOC miss on sell ─────────────────────────────────
        elif sell_filled == 0 and buy_filled > 0:
            log.warning("ioc_miss_sell", trade_id=trade_id, buy_filled=buy_filled)
            await sm.transition(TradeState.HEDGING)
            await self._hedge_sell(buy_name, buy_filled, {
                "binance_ask": buy_price,
            })
            net_pnl = -(buy_filled * buy_price * 0.001 * 2)
            ioc_miss = True

        # ── Double miss ───────────────────────────────────────────
        elif buy_filled == 0 and sell_filled == 0:
            net_pnl  = 0.0
            ioc_miss = True

        else:
            ioc_miss = False
            # ── Partial delta hedge ───────────────────────────────
            if delta_usd > cfg.MIN_HEDGE_THRESHOLD:
                await sm.transition(TradeState.HEDGING)
                if delta > 0:
                    await self._hedge_sell(buy_name,  delta,        {"binance_ask": buy_price})
                else:
                    await self._hedge_buy(sell_name, abs(delta),    {f"{sell_name}_ask": sell_price})

            # ── PnL calculation ───────────────────────────────────
            settled_qty  = min(buy_filled, sell_filled)
            gross_profit = settled_qty * (sell_price - buy_price)
            total_fees   = buy_fee + sell_fee
            rebal_share  = 1.00 / 5   # amortise $1 rebalance over 5 trades
            net_pnl      = gross_profit - total_fees - rebal_share

        from utils.notifier import notify

        # ── Build trade record ────────────────────────────────────
        record = {
            "trade_id":    trade_id,
            "mock":        cfg.MOCK_MODE,           # ← MOCK flag on every record
            "direction":   direction,
            "spread_pct":  spread_pct,
            "buy_exchange":  buy_name,
            "sell_exchange": sell_name,
            "buy_price":   buy_price,
            "sell_price":  sell_price,
            "buy_filled":  buy_filled,
            "sell_filled": sell_filled,
            "delta":       round(delta, 6),
            "buy_fee":     round(buy_fee,  6),
            "sell_fee":    round(sell_fee, 6),
            "net_pnl":     round(net_pnl,  4),
            "latency_ms":  latency_ms,
            "ioc_miss":    ioc_miss,
            "timestamp":   time.time(),
        }

        # Log and notify
        mode_tag = "[MOCK]" if cfg.MOCK_MODE else "[LIVE]"
        pnl_sign = "+" if net_pnl >= 0 else ""
        log.info("trade_completed", **record)

        msg = (
            f"{mode_tag} Trade {trade_id}\n"
            f"  Direction : {direction}\n"
            f"  Spread    : {spread_pct}%\n"
            f"  Filled    : buy={buy_filled:.4f}  sell={sell_filled:.4f}\n"
            f"  Net PnL   : {pnl_sign}{net_pnl:.4f} USDT\n"
            f"  Latency   : {latency_ms}ms"
        )
        await notify(msg)

        # Write to trade log
        from utils.logger import trade_logger
        await trade_logger.write(record)

        return record
