"""
utils/rebalancer.py — Cross-Exchange Capital Rebalancer
Moves PIPPIN from MEXC → Binance via Solana when Binance USDT runs low.
In MOCK_MODE: simulates the transfer instantly without real blockchain calls.
"""
import asyncio
import time
import structlog
import ccxt.async_support as ccxt

from config import cfg
from engine.state import sm, TradeState
from utils.notifier import notify

log = structlog.get_logger(__name__)

MIN_SOL_FOR_GAS = 0.01  # minimum SOL needed to pay Solana tx fee


class Rebalancer:

    def __init__(self, mock_buy_ex=None, mock_sell_ex=None) -> None:
        """
        mock_buy_ex / mock_sell_ex: MockExchange instances
        (passed in from executor in MOCK_MODE so balances stay in sync)
        """
        self._mock_buy_ex  = mock_buy_ex
        self._mock_sell_ex = mock_sell_ex

    async def check_and_rebalance(self) -> None:
        """Call periodically. Triggers rebalance if Binance USDT is low."""
        if not sm.can_rebalance():
            return

        binance_usdt = await self._get_binance_usdt()
        if binance_usdt is None:
            return

        if binance_usdt < cfg.REBALANCE_TRIGGER_USD:
            log.info("rebalance_triggered",
                     binance_usdt=binance_usdt,
                     trigger=cfg.REBALANCE_TRIGGER_USD,
                     mock=cfg.MOCK_MODE)
            await self._rebalance()

    async def _rebalance(self) -> None:
        await sm.transition(TradeState.REBALANCING)
        await notify(f"Rebalance started — moving ${cfg.REBALANCE_AMOUNT_USD} PIPPIN → Binance")

        try:
            if cfg.MOCK_MODE:
                await self._mock_rebalance()
            else:
                await self._live_rebalance()
        except Exception as exc:
            log.error("rebalance_failed", error=str(exc))
            await notify(f"REBALANCE FAILED: {exc}", urgent=True)
        finally:
            await sm.transition(TradeState.IDLE)

    # ── Mock rebalance ────────────────────────────────────────────

    async def _mock_rebalance(self) -> None:
        """
        Simulate rebalance: debit PIPPIN from MEXC mock wallet,
        credit equivalent USDT to Binance mock wallet after simulated delay.
        """
        log.info("mock_rebalance_start", amount_usd=cfg.REBALANCE_AMOUNT_USD)

        # Simulate ~5s transfer time (vs 2min real)
        await asyncio.sleep(5)

        if self._mock_sell_ex:
            self._mock_sell_ex.credit_usdt(cfg.REBALANCE_AMOUNT_USD)
        if self._mock_buy_ex:
            self._mock_buy_ex.credit_usdt(cfg.REBALANCE_AMOUNT_USD)

        log.info("mock_rebalance_complete", amount_usd=cfg.REBALANCE_AMOUNT_USD)
        await notify(f"[MOCK] Rebalance complete — ${cfg.REBALANCE_AMOUNT_USD} transferred")

    # ── Live rebalance ────────────────────────────────────────────

    async def _live_rebalance(self) -> None:
        """
        Real rebalance:
        1. Check SOL gas balance
        2. Withdraw PIPPIN from MEXC → Binance Solana address
        3. Poll Solana RPC until finalized
        """
        # Check SOL balance for gas
        sol_ok = await self._check_sol_balance()
        if not sol_ok:
            raise RuntimeError(
                "Insufficient SOL for gas fees. Top up your Solana wallet."
            )

        mexc = ccxt.mexc({
            "apiKey": cfg.API_KEY_MEXC,
            "secret": cfg.API_SECRET_MEXC,
        })
        binance = ccxt.binance({
            "apiKey":  cfg.API_KEY_BINANCE,
            "secret":  cfg.API_SECRET_BINANCE,
        })

        try:
            # Get Binance PIPPIN deposit address (Solana network)
            deposit_info = await binance.fetch_deposit_address(
                cfg.BASE_ASSET, params={"network": "SOL"}
            )
            deposit_addr = deposit_info["address"]

            # Compute qty to withdraw (convert USD amount to PIPPIN)
            ticker = await mexc.fetch_ticker(cfg.SYMBOL)
            mid    = (ticker["bid"] + ticker["ask"]) / 2
            qty    = round(cfg.REBALANCE_AMOUNT_USD / mid, 2)

            log.info("live_rebalance_withdrawing",
                     qty=qty,
                     address=deposit_addr[:12] + "...",
                     network="SOL")

            # Initiate withdrawal from MEXC
            withdrawal = await mexc.withdraw(
                cfg.BASE_ASSET,
                qty,
                deposit_addr,
                params={"network": "SOL"},
            )
            tx_hash = withdrawal.get("txid") or withdrawal.get("id")
            await notify(f"Withdrawal submitted — tx: {str(tx_hash)[:16]}...")

            # Wait for on-chain confirmation
            confirmed = await self._wait_for_confirmation(tx_hash)
            if not confirmed:
                raise RuntimeError(f"Tx {tx_hash} not confirmed within timeout")

            await notify(f"Rebalance confirmed on-chain — {qty} PIPPIN transferred")

        finally:
            await mexc.close()
            await binance.close()

    async def _wait_for_confirmation(self, tx_hash: str) -> bool:
        """Poll Solana RPC every 5s until finalized or timeout."""
        import aiohttp
        rpc_url  = "https://api.mainnet-beta.solana.com"
        deadline = time.monotonic() + cfg.REBALANCE_TX_TIMEOUT_SEC

        while time.monotonic() < deadline:
            try:
                async with aiohttp.ClientSession() as session:
                    payload = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "getTransaction",
                        "params": [tx_hash, {"commitment": "finalized"}],
                    }
                    async with session.post(rpc_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        data = await resp.json()
                        result = data.get("result")
                        if result and result.get("meta"):
                            log.info("tx_finalized", tx=tx_hash[:16])
                            return True
            except Exception as exc:
                log.warning("rpc_poll_error", error=str(exc))

            await asyncio.sleep(5)

        log.error("tx_confirmation_timeout",
                  tx=tx_hash[:16],
                  timeout=cfg.REBALANCE_TX_TIMEOUT_SEC)
        await notify(
            f"REBALANCE TIMEOUT — tx {tx_hash[:16]} not confirmed "
            f"in {cfg.REBALANCE_TX_TIMEOUT_SEC}s. Manual check required.",
            urgent=True,
        )
        return False

    async def _get_binance_usdt(self) -> float | None:
        if cfg.MOCK_MODE:
            return (self._mock_sell_ex.usdt_balance
                    if self._mock_sell_ex else cfg.REBALANCE_TRIGGER_USD + 1)
        try:
            binance = ccxt.binance({
                "apiKey":  cfg.API_KEY_BINANCE,
                "secret":  cfg.API_SECRET_BINANCE,
            })
            bal = await binance.fetch_balance()
            await binance.close()
            return float(bal["USDT"]["free"])
        except Exception as exc:
            log.error("fetch_balance_failed", error=str(exc))
            return None

    async def _check_sol_balance(self) -> bool:
        """Returns True if SOL wallet has enough for gas."""
        try:
            import aiohttp
            # Placeholder — replace with your actual Solana wallet address
            sol_address = "YOUR_SOLANA_WALLET_ADDRESS"
            rpc_url     = "https://api.mainnet-beta.solana.com"
            async with aiohttp.ClientSession() as session:
                payload = {
                    "jsonrpc": "2.0", "id": 1,
                    "method": "getBalance",
                    "params": [sol_address],
                }
                async with session.post(rpc_url, json=payload) as resp:
                    data   = await resp.json()
                    lamports = data.get("result", {}).get("value", 0)
                    sol    = lamports / 1e9
                    log.info("sol_balance", sol=sol)
                    return sol >= MIN_SOL_FOR_GAS
        except Exception as exc:
            log.warning("sol_balance_check_failed", error=str(exc))
            return True  # Assume OK if RPC fails — don't block rebalance
