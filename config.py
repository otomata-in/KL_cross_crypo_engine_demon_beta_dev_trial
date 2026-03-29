"""
config.py — PAAL-V2 Configuration
All values validated at startup via Pydantic.
The bot refuses to start if any constraint fails.
"""
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── MODE ──────────────────────────────────────────────────────
    # True  → paper trading: real feeds, simulated orders, recorded PnL
    # False → live trading:  real orders with real money
    MOCK_MODE: bool = True

    # ── Exchange credentials ───────────────────────────────────────
    API_KEY_BINANCE:    str = ""
    API_SECRET_BINANCE: str = ""
    API_KEY_MEXC:       str = ""
    API_SECRET_MEXC:    str = ""

    # ── Asset ──────────────────────────────────────────────────────
    SYMBOL:      str = "PIPPIN/USDT"
    BASE_ASSET:  str = "PIPPIN"
    QUOTE_ASSET: str = "USDT"

    # ── Capital & sizing ───────────────────────────────────────────
    TRADE_AMOUNT:        float = 100.0
    STARTING_CAPITAL:    float = 500.0
    KILL_SWITCH_BALANCE: float = 450.0

    # ── Thresholds ─────────────────────────────────────────────────
    TRIGGER_THRESHOLD:   float = 1.8
    FRICTION_BUDGET:     float = 0.4
    SLIPPAGE_BUDGET:     float = 0.2
    MAX_VALID_SPREAD:    float = 5.0
    MIN_HEDGE_THRESHOLD: float = 1.0

    # ── Risk controls ──────────────────────────────────────────────
    DAILY_LOSS_CAP:    float = 30.0
    CONSEC_LOSS_MAX:   int   = 3
    PAUSE_MINUTES:     int   = 15

    # ── Depth / liquidity ──────────────────────────────────────────
    MIN_DEPTH_USD:     float = 200.0
    ORDER_BOOK_LEVELS: int   = 5

    # ── Latency / timing ───────────────────────────────────────────
    STALE_FEED_SECONDS: float = 2.0
    REST_POLL_INTERVAL: float = 0.5
    FEE_REFRESH_SECS:   int   = 300

    # ── Rebalancer ─────────────────────────────────────────────────
    REBALANCE_TRIGGER_USD:    float = 20.0
    REBALANCE_AMOUNT_USD:     float = 200.0
    REBALANCE_TX_TIMEOUT_SEC: int   = 300

    # ── Mock-mode simulation parameters ────────────────────────────
    # These make paper trading realistic rather than optimistic
    MOCK_FILL_RATE:    float = 0.97   # 97% of qty assumed filled (3% IOC miss)
    MOCK_SLIPPAGE_PCT: float = 0.15   # simulated slippage on fills
    MOCK_LATENCY_MS:   float = 45.0   # simulated round-trip execution latency

    # ── Telegram ───────────────────────────────────────────────────
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID:   str = ""

    # ── Logging ────────────────────────────────────────────────────
    LOG_LEVEL:    str = "INFO"
    LOG_FILE:     str = "logs/paal_v2.jsonl"
    TRADES_FILE:  str = "logs/trades.csv"
    METRICS_PORT: int = 9090

    # ── Validators ─────────────────────────────────────────────────

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
    def cross_field_checks(self) -> "Config":
        if self.KILL_SWITCH_BALANCE >= self.STARTING_CAPITAL:
            raise ValueError(
                f"KILL_SWITCH_BALANCE ({self.KILL_SWITCH_BALANCE}) must be "
                f"less than STARTING_CAPITAL ({self.STARTING_CAPITAL})"
            )
        if self.TRIGGER_THRESHOLD <= self.FRICTION_BUDGET:
            raise ValueError(
                f"TRIGGER_THRESHOLD ({self.TRIGGER_THRESHOLD}%) must exceed "
                f"FRICTION_BUDGET ({self.FRICTION_BUDGET}%)"
            )
        if self.TRADE_AMOUNT * 2 > self.STARTING_CAPITAL:
            raise ValueError(
                f"TRADE_AMOUNT x2 ({self.TRADE_AMOUNT * 2}) exceeds "
                f"STARTING_CAPITAL ({self.STARTING_CAPITAL})"
            )
        return self


# Singleton — import cfg everywhere
cfg = Config()
