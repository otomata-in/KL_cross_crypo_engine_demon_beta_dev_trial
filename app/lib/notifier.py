"""
app/lib/notifier.py — Telegram + Console Alerts
=================================================
Send Telegram alerts for important bot events.
"""

import aiohttp
import structlog

from app.config import get_config

log = structlog.get_logger(__name__)


async def notify(message: str, urgent: bool = False) -> None:
    """
    Send a Telegram message (and log to console).
    Prepends mode tag automatically.
    """
    cfg = get_config()
    mode_tag = "[MOCK]" if cfg.MOCK_MODE else "[LIVE]"
    tagged = f"{mode_tag} {message}"

    # Always log to console
    log.info("notify", message=tagged, urgent=urgent)

    if not cfg.TELEGRAM_BOT_TOKEN or not cfg.TELEGRAM_CHAT_ID:
        return  # Telegram not configured — console only

    url = f"https://api.telegram.org/bot{cfg.TELEGRAM_BOT_TOKEN}/sendMessage"
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
