"""
app/models/opportunity.py — Opportunity Data Model
====================================================
Represents a detected arbitrage opportunity.
Maps to the `opportunities` hypertable in TimescaleDB.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Opportunity:
    """
    A single detected arbitrage opportunity between two exchanges.

    Fields match the TimescaleDB `opportunities` table columns exactly,
    ensuring seamless insert/read operations.
    """
    token:            str                       # e.g. "SOL"
    ex_buy:           str                       # Buy exchange name, e.g. "binance"
    ex_sell:          str                       # Sell exchange name, e.g. "backpack"
    direction:        str                       # e.g. "BuyBIN→SellBP"
    gross_spread_pct: float                     # Gross spread before fees (%)
    net_spread_pct:   float                     # Net spread after fees (%)
    pair_fees_pct:    float                     # Combined fees for this pair (%)
    buy_ask:          float                     # Buy price (normalized to USDT)
    sell_bid:         float                     # Sell price (normalized to USDT)
    usdt_usdc_rate:   float = 1.0               # USDT/USDC conversion rate at detection
    timestamp_utc:    Optional[str] = None      # ISO 8601 UTC timestamp

    def __post_init__(self):
        if self.timestamp_utc is None:
            self.timestamp_utc = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization and DB insert."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Opportunity":
        """Create from a dict (e.g. DB row or JSON payload)."""
        return cls(
            token=data["token"],
            ex_buy=data["ex_buy"],
            ex_sell=data["ex_sell"],
            direction=data["direction"],
            gross_spread_pct=float(data["gross_spread_pct"]),
            net_spread_pct=float(data["net_spread_pct"]),
            pair_fees_pct=float(data["pair_fees_pct"]),
            buy_ask=float(data["buy_ask"]),
            sell_bid=float(data["sell_bid"]),
            usdt_usdc_rate=float(data.get("usdt_usdc_rate", 1.0)),
            timestamp_utc=data.get("timestamp_utc"),
        )

    @classmethod
    def from_db_row(cls, row) -> "Opportunity":
        """Create from an asyncpg Record."""
        return cls(
            token=row["token"],
            ex_buy=row["ex_buy"],
            ex_sell=row["ex_sell"],
            direction=row["direction"],
            gross_spread_pct=float(row["gross_spread_pct"]),
            net_spread_pct=float(row["net_spread_pct"]),
            pair_fees_pct=float(row["pair_fees_pct"]),
            buy_ask=float(row["buy_ask"]),
            sell_bid=float(row["sell_bid"]),
            usdt_usdc_rate=float(row["usdt_usdc_rate"]),
            timestamp_utc=row["timestamp_utc"].isoformat()
            if hasattr(row["timestamp_utc"], "isoformat")
            else str(row["timestamp_utc"]),
        )


# ── DB column mapping ────────────────────────────────────────────

OPPORTUNITY_COLUMNS = [
    "timestamp_utc",
    "token",
    "ex_buy",
    "ex_sell",
    "direction",
    "gross_spread_pct",
    "net_spread_pct",
    "pair_fees_pct",
    "buy_ask",
    "sell_bid",
    "usdt_usdc_rate",
]

OPPORTUNITY_INSERT_SQL = """
    INSERT INTO opportunities (
        timestamp_utc, token, ex_buy, ex_sell, direction,
        gross_spread, net_spread, pair_fees,
        buy_ask, sell_bid, usdt_usdc_rate
    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
"""
