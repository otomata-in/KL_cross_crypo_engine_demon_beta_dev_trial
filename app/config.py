"""
app/config.py — Unified Application Configuration
===================================================
Single source of truth for all settings: exchanges, tokens, DB, thresholds.
Validated at startup via Pydantic. The bot refuses to start if constraints fail.

Usage:
    from app.config import get_config
    cfg = get_config()
"""

import os
from typing import Optional, Dict, List
from pydantic import BaseModel, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ── Exchange Configuration ──────────────────────────────────────

class ExchangeConfig(BaseModel):
    """Configuration for a single exchange."""
    name:       str
    ccxt_id:    Optional[str] = None   # None = custom adapter (e.g. dextrade)
    label:      str                     # Short label for frontend (e.g. "BIN")
    quote:      str                     # Quote currency: "USDT" or "USDC"
    fee_taker:  float                   # Taker fee in % (e.g. 0.10)
    gas:        float = 0.0             # Network transfer fee in %
    ob_limit:   Optional[int] = 10     # Orderbook depth for WS subscription
    enabled:    bool = True
    options:    dict = {}               # ccxt constructor options
    api_key:    str = ""
    api_secret: str = ""


# ── Token Categories ────────────────────────────────────────────

DEFAULT_CATEGORIES: Dict[str, List[str]] = {
    "💎 Big Three":          ["SOL", "ETH", "BTC"],
    "🟣 Solana Core":        ["JUP", "PYTH", "JTO"],
    "⚡ High Velocity":      ["RENDER", "W", "DRIFT"],
    "🏗️ DePIN & Infra":      ["HNT", "HONEY", "IO"],
    "🏦 Ecosystem HiCaps":   ["KMNO", "TNSR", "CLOUD"],
    "🐕 Meme Liquidity":     ["WIF", "BONK", "MEW"],
    "⭐ Special Pair":        ["BP"],
    "🌐 Cross-Chain":        ["SUI", "SEI"],
}


# ── Main Application Config ────────────────────────────────────

class AppConfig(BaseSettings):
    """
    Unified application configuration.
    Loads from .env file + environment variables.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # ── Mode ──────────────────────────────────────────────────
    MOCK_MODE: bool = True   # True = paper trading, False = live

    # ── Exchange API credentials ──────────────────────────────
    API_KEY_BINANCE:    str = ""
    API_SECRET_BINANCE: str = ""
    API_KEY_BACKPACK:       str = ""
    API_SECRET_BACKPACK:    str = ""
    API_KEY_BYBIT:     str = ""
    API_SECRET_BYBIT:  str = ""
    API_KEY_DEX:       str = ""
    API_SECRET_DEX:    str = ""

    # ── Database ──────────────────────────────────────────────
    DB_HOST:     str = "127.0.0.1"
    DB_PORT:     int = 5432
    DB_NAME:     str = "arb_bot"
    DB_USER:     str = "arb_user"
    DB_PASSWORD: str = ""
    DB_POOL_MIN: int = 2
    DB_POOL_MAX: int = 5

    # ── Monitor thresholds ────────────────────────────────────
    DEFAULT_THRESHOLD:   float = 0.001  # % net profit to highlight
    OPP_MIN_SPREAD:      float = 0.0    # Minimum spread to log
    WS_BROADCAST_INTERVAL: float = 0.1  # 100ms = 10fps
    WS_PORT:             int   = 8765

    # ── Trading parameters ────────────────────────────────────
    TRADE_AMOUNT:        float = 100.0
    STARTING_CAPITAL:    float = 500.0
    KILL_SWITCH_BALANCE: float = 450.0
    TRIGGER_THRESHOLD:   float = 1.8
    FRICTION_BUDGET:     float = 0.4
    SLIPPAGE_BUDGET:     float = 0.2
    MAX_VALID_SPREAD:    float = 5.0
    MIN_HEDGE_THRESHOLD: float = 1.0

    # ── Risk controls ─────────────────────────────────────────
    DAILY_LOSS_CAP:    float = 30.0
    CONSEC_LOSS_MAX:   int   = 3
    PAUSE_MINUTES:     int   = 15

    # ── Depth / liquidity ─────────────────────────────────────
    MIN_DEPTH_USD:     float = 200.0
    ORDER_BOOK_LEVELS: int   = 5

    # ── Latency / timing ──────────────────────────────────────
    STALE_FEED_SECONDS: float = 2.0
    REST_POLL_INTERVAL: float = 0.5
    FEE_REFRESH_SECS:   int   = 300

    # ── Mock-mode simulation ──────────────────────────────────
    MOCK_FILL_RATE:    float = 0.97
    MOCK_SLIPPAGE_PCT: float = 0.15
    MOCK_LATENCY_MS:   float = 45.0

    # ── Notifications ─────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID:   str = ""

    # ── Logging ───────────────────────────────────────────────
    LOG_LEVEL:    str = "INFO"
    LOG_FILE:     str = "logs/paal_v2.jsonl"
    TRADES_FILE:  str = "logs/trades.csv"

    # ── Validators ────────────────────────────────────────────

    @field_validator("TRIGGER_THRESHOLD")
    @classmethod
    def trigger_sane(cls, v: float) -> float:
        if v < 0.8:
            raise ValueError(
                f"TRIGGER_THRESHOLD={v}% is dangerously low. "
                f"Minimum 0.8%. Did you mean 1.8?"
            )
        return v

    @field_validator("TRADE_AMOUNT")
    @classmethod
    def trade_amount_sane(cls, v: float) -> float:
        if v < 10:
            raise ValueError("TRADE_AMOUNT below $10 — likely a config error")
        return v

    @model_validator(mode="after")
    def cross_field_checks(self) -> "AppConfig":
        if self.KILL_SWITCH_BALANCE >= self.STARTING_CAPITAL:
            raise ValueError(
                f"KILL_SWITCH_BALANCE ({self.KILL_SWITCH_BALANCE}) must be "
                f"less than STARTING_CAPITAL ({self.STARTING_CAPITAL})"
            )
        return self

    # ── Exchange registry builder ─────────────────────────────

    @property
    def exchanges(self) -> Dict[str, ExchangeConfig]:
        """
        Build the exchange registry from environment variables.
        Returns dict of {exchange_name: ExchangeConfig}.
        """
        return {
            "binance": ExchangeConfig(
                name="binance",
                ccxt_id="binance",
                label="BIN",
                quote="USDT",
                fee_taker=0.10,
                gas=0.00,
                ob_limit=10,
                enabled=True,
                options={"defaultType": "spot"},
                api_key=self.API_KEY_BINANCE,
                api_secret=self.API_SECRET_BINANCE,
            ),
            "backpack": ExchangeConfig(
                name="backpack",
                ccxt_id="backpack",
                label="BP",
                quote="USDC",
                fee_taker=0.10,
                gas=0.01,
                ob_limit=10,
                enabled=True,
                options={},
                api_key=self.API_KEY_BACKPACK,
                api_secret=self.API_SECRET_BACKPACK,
            ),
            "bybit": ExchangeConfig(
                name="bybit",
                ccxt_id="bybit",
                label="BYBIT",
                quote="USDT",
                fee_taker=0.10,
                gas=0.00,
                ob_limit=50,
                enabled=True,
                options={"defaultType": "spot"},
                api_key=self.API_KEY_BYBIT,
                api_secret=self.API_SECRET_BYBIT,
            ),
            "dextrade": ExchangeConfig(
                name="dextrade",
                ccxt_id=None,
                label="DEX",
                quote="USDT",
                fee_taker=0.20,
                gas=0.00,
                ob_limit=None,
                enabled=True,
                options={},
                api_key=self.API_KEY_DEX,
                api_secret=self.API_SECRET_DEX,
            ),
        }

    def get_categories(self) -> Dict[str, List[str]]:
        """Return token categories."""
        return DEFAULT_CATEGORIES

    def get_tokens(self) -> List[str]:
        """Flat list of all tokens from all categories."""
        return [t for group in DEFAULT_CATEGORIES.values() for t in group]

    def get_token_category_map(self) -> Dict[str, str]:
        """Map each token to its category name."""
        result = {}
        for cat, tokens in DEFAULT_CATEGORIES.items():
            for t in tokens:
                result[t] = cat
        return result


# ── Singleton accessor ───────────────────────────────────────────

_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Get or create the singleton AppConfig instance."""
    global _config
    if _config is None:
        _config = AppConfig()
    return _config
