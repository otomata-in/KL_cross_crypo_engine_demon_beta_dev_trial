"""
utils/notifier.py — Telegram + Console Alerts
All notifications are tagged [MOCK] or [LIVE] automatically.
Falls back to console if Telegram is not configured.
"""
import asyncio
import aiohttp
import structlog

from config import cfg

log = structlog.get_logger(__name__)

_MODE_TAG = lambda: "[MOCK]" if cfg.MOCK_MODE else "[LIVE]"


async def notify(message: str, urgent: bool = False) -> None:
    """
    Send a Telegram message (and log to console).
    Prepends mode tag automatically.
    """
    tagged = f"{_MODE_TAG()} {message}"

    # Always log to console
    log.info("notify", message=tagged, urgent=urgent)

    if not cfg.TELEGRAM_BOT_TOKEN or not cfg.TELEGRAM_CHAT_ID:
        return  # Telegram not configured — console only

    url     = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":    cfg.TELEGRAM_CHAT_ID,
        "text":       tagged,
        "parse_mode": "HTML",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    log.warning("telegram_send_failed", status=resp.status)
    except Exception as exc:
        log.warning("telegram_error", error=str(exc))


async def notify_startup() -> None:
    mode     = "PAPER TRADING (mock)" if cfg.MOCK_MODE else "LIVE TRADING — REAL MONEY"
    capital  = cfg.STARTING_CAPITAL
    trigger  = cfg.TRIGGER_THRESHOLD
    daily_cap = cfg.DAILY_LOSS_CAP

    msg = (
        f"PAAL-V2 started\n"
        f"Mode     : {mode}\n"
        f"Capital  : ${capital}\n"
        f"Trigger  : {trigger}%\n"
        f"Daily cap: -${daily_cap}\n"
        f"Symbol   : {cfg.SYMBOL}"
    )
    await notify(msg)


async def notify_shutdown(reason: str) -> None:
    await notify(f"PAAL-V2 SHUTDOWN\nReason: {reason}", urgent=True)


async def notify_daily_summary(summary: dict) -> None:
    mode_str = "Mock" if cfg.MOCK_MODE else "Live"
    pnl_sign = "+" if summary["net_pnl"] >= 0 else ""
    msg = (
        f"Daily Summary ({mode_str})\n"
        f"  Trades   : {summary['trades']}\n"
        f"  Net PnL  : {pnl_sign}{summary['net_pnl']} USDT\n"
        f"  Win rate : {summary.get('win_rate', 0)}%\n"
        f"  IOC miss : {summary['ioc_misses']}\n"
        f"  Best     : +{summary.get('best_trade', 0)} USDT\n"
        f"  Worst    : {summary.get('worst_trade', 0)} USDT"
    )
    await notify(msg)
