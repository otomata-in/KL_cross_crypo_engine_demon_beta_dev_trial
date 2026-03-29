"""
main.py — PAAL-V2 Orchestrator
Starts the event loop, wires all modules, handles graceful shutdown.
MOCK_MODE and LIVE mode are fully controlled by config.MOCK_MODE.
"""
import asyncio
import signal
import time
import sys
import logging
import structlog

from config import cfg
from engine.scanner  import Scanner
from engine.logic    import Logic, DailyLossCapHit, ConsecutiveLossPause
from engine.executor import Executor
from engine.state    import sm, TradeState
from utils.notifier  import notify, notify_startup, notify_shutdown, notify_daily_summary
from utils.fee_ledger  import fee_ledger
from utils.rebalancer  import Rebalancer
from utils.logger      import trade_logger

# ── Structlog setup ──────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(message)s")
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
)
log = structlog.get_logger(__name__)


class PAALV2:

    def __init__(self) -> None:
        self._scanner    = Scanner()
        self._logic      = Logic(self._scanner)
        self._executor   = Executor(self._scanner)
        self._rebalancer = Rebalancer(
            mock_buy_ex  = self._executor._buy_ex  if cfg.MOCK_MODE else None,
            mock_sell_ex = self._executor._sell_ex if cfg.MOCK_MODE else None,
        )
        self._running       = False
        self._total_capital = cfg.STARTING_CAPITAL
        self._last_summary  = time.monotonic()

    # ── Startup / shutdown ───────────────────────────────────────

    async def run(self) -> None:
        self._running = True

        mode = "MOCK (paper trading)" if cfg.MOCK_MODE else "LIVE (real money)"
        log.info("paal_v2_starting",
                 mode=mode,
                 symbol=cfg.SYMBOL,
                 capital=cfg.STARTING_CAPITAL,
                 trigger=cfg.TRIGGER_THRESHOLD)

        await notify_startup()

        # Register OS signal handlers for graceful shutdown
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(self._shutdown(str(s)))
            )

        # Start background tasks
        await asyncio.gather(
            self._scanner.start(),
            fee_ledger.refresh_loop(),
            self._main_loop(),
            self._rebalance_loop(),
            self._summary_loop(),
        )

    async def _shutdown(self, reason: str = "user request") -> None:
        if not self._running:
            return
        self._running = False
        log.info("shutdown_initiated", reason=reason)

        # If mid-trade, attempt emergency hedge
        state = sm.state
        if state in (TradeState.LEG1_OPEN, TradeState.LEG2_OPEN):
            log.warning("shutdown_mid_trade_hedging")
            await notify("SHUTDOWN mid-trade — emergency hedging", urgent=True)
            # Give executor 10s to hedge
            await asyncio.sleep(10)

        await self._scanner.stop()
        summary = trade_logger.daily_summary()
        await notify_daily_summary(summary)
        await notify_shutdown(reason)
        await sm.transition(TradeState.SHUTDOWN)
        log.info("shutdown_complete")
        sys.exit(0)

    # ── Main trading loop ─────────────────────────────────────────

    async def _main_loop(self) -> None:
        log.info("main_loop_started")
        while self._running:
            try:
                # Wait for scanner to warm up
                await asyncio.sleep(0.1)

                # Kill switch — check total capital
                if not await self._kill_switch_ok():
                    await self._shutdown("KILL_SWITCH_TRIGGERED")
                    return

                # Get spread from scanner
                spread = self._scanner.get_spread()

                # Evaluate through logic filters
                signal = self._logic.evaluate(spread)

                if signal is None:
                    continue

                # Execute trade (mock or live)
                result = await self._executor.execute(signal)

                if result and result.get("net_pnl") is not None:
                    try:
                        self._logic.session.record(result["net_pnl"])
                    except DailyLossCapHit as e:
                        log.error("daily_loss_cap", error=str(e))
                        await notify(str(e), urgent=True)
                        await self._shutdown("DAILY_LOSS_CAP")
                        return
                    except ConsecutiveLossPause as e:
                        log.warning("consec_pause", error=str(e))
                        await notify(str(e))
                        await sm.transition(TradeState.PAUSED)
                        await asyncio.sleep(cfg.PAUSE_MINUTES * 60)
                        await sm.transition(TradeState.IDLE)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                log.error("main_loop_error", error=str(exc))
                await notify(f"Main loop error: {exc}", urgent=True)
                await asyncio.sleep(1)

    # ── Rebalance loop ────────────────────────────────────────────

    async def _rebalance_loop(self) -> None:
        await asyncio.sleep(30)  # let scanner warm up first
        while self._running:
            try:
                await self._rebalancer.check_and_rebalance()
            except Exception as exc:
                log.error("rebalance_loop_error", error=str(exc))
            await asyncio.sleep(60)  # check every 60s

    # ── Summary loop (every hour) ─────────────────────────────────

    async def _summary_loop(self) -> None:
        while self._running:
            await asyncio.sleep(3600)
            summary = trade_logger.daily_summary()
            log.info("hourly_summary", **summary)
            await notify_daily_summary(summary)

    # ── Kill switch ───────────────────────────────────────────────

    async def _kill_switch_ok(self) -> bool:
        """
        In MOCK_MODE: uses virtual wallet balances.
        In LIVE mode: fetches real balances from both exchanges.
        """
        if cfg.MOCK_MODE:
            # Sum mock wallet values using last known mid price
            spread = self._scanner.get_spread()
            if spread is None:
                return True  # can't evaluate — don't kill
            mid = (spread["binance_bid"] + spread["binance_ask"]) / 2
            ex_b = self._executor._buy_ex
            ex_m = self._executor._sell_ex
            total = (ex_b.total_virtual_value(mid) +
                     ex_m.total_virtual_value(mid))
        else:
            try:
                import ccxt.async_support as ccxt
                binance = ccxt.binance({"apiKey": cfg.API_KEY_BINANCE, "secret": cfg.API_SECRET_BINANCE})
                mexc    = ccxt.mexc({"apiKey": cfg.API_KEY_MEXC, "secret": cfg.API_SECRET_MEXC})
                b_bal   = await binance.fetch_balance()
                m_bal   = await mexc.fetch_balance()
                await binance.close()
                await mexc.close()
                spread  = self._scanner.get_spread()
                mid     = (spread["binance_bid"] + spread["binance_ask"]) / 2 if spread else 0
                pippin_b = float(b_bal.get(cfg.BASE_ASSET, {}).get("free", 0))
                pippin_m = float(m_bal.get(cfg.BASE_ASSET, {}).get("free", 0))
                usdt_b   = float(b_bal["USDT"]["free"])
                usdt_m   = float(m_bal["USDT"]["free"])
                total    = usdt_b + usdt_m + (pippin_b + pippin_m) * mid
            except Exception as exc:
                log.error("kill_switch_balance_check_failed", error=str(exc))
                return True  # don't kill on check failure

        if total < cfg.KILL_SWITCH_BALANCE:
            log.error("kill_switch_triggered",
                      total=round(total, 2),
                      floor=cfg.KILL_SWITCH_BALANCE,
                      mock=cfg.MOCK_MODE)
            await notify(
                f"KILL SWITCH TRIGGERED\n"
                f"Total capital: ${total:.2f} < floor ${cfg.KILL_SWITCH_BALANCE}",
                urgent=True,
            )
            return False
        return True


# ── Entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        import uvloop
        uvloop.install()
        log.info("uvloop_installed")
    except ImportError:
        log.info("uvloop_not_available_using_default")

    bot = PAALV2()
    asyncio.run(bot.run())
